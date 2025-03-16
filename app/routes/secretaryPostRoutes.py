from flask import request, jsonify
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
import re
import json
import base64
from config import Config
import openai
from email.mime.text import MIMEText
openai.api_key=Config.CHAT_API_KEY
from app.routes.secretaryGetRoutes import setup_routes_secretary_gets
from flask_caching import Cache
from app.utils.utils import get_user_from_db
def setup_routes_secretary_posts(app, mongo, cache):
    cache = Cache(app)
    functions = setup_routes_secretary_gets(app, mongo, cache)
    get_gmail_headers = functions["get_gmail_headers"]
    get_outlook_headers = functions["get_outlook_headers"]
    get_slack_headers = functions["get_slack_headers"]
    get_hubspot_headers = functions["get_hubspot_headers"]
    get_notion_headers = functions["get_notion_headers"]
    get_clickup_headers = functions["get_clickup_headers"]
    get_teams_headers = functions["get_teams_headers"]
    get_onedrive_headers = functions["get_onedrive_headers"]
    get_dropbox_headers = functions["get_dropbox_headers"]
    get_asana_headers = functions["get_asana_headers"]
    get_google_drive_headers = functions["get_google_drive_headers"]


    def interpretar_accion_email(texto):
        prompt = f"El usuario dijo: '{texto}'. Determina si quiere 'delete' (eliminar), 'spam' (mover a spam), 'schedule' (agendar cita), 'draft' (crear borrador) o 'send' (enviar correo). Si no está claro, responde 'unknown'."
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Eres un asistente que analiza intenciones en correos electrónicos."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content.strip().lower()

    def interpretar_accion_productividad(texto):
        prompt = f"El usuario dijo: '{texto}'. Determina si quiere 'mark_done' (marcar como completado), 'assign' (asignar a alguien más), 'comment' (comentar en la tarea), 'delete' (eliminar la tarea) o 'change_status' (cambiar estado). Si no está claro, responde 'unknown'."
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Eres un asistente que analiza intenciones en plataformas de productividad."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content.strip().lower()
    
    def interpretar_accion_hubspot(texto):
        prompt = f"El usuario dijo: '{texto}'. Determina si quiere 'update' (actualizar un negocio), 'create' (crear un negocio), 'comment' (comentar en un negocio), 'create_contact' (crear un contacto), 'delete_contact' (eliminar un contacto), 'create_company' (crear una empresa) o 'delete_company' (eliminar una empresa). Si no está claro, responde 'unknown'."
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Eres un asistente que analiza intenciones en plataformas CRM como HubSpot."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content.strip().lower()

    def interpretar_accion_archivos(texto):
        prompt = f"El usuario dijo: '{texto}'. Determina si quiere 'download' (descargar archivo), 'share' (compartir con alguien más), 'delete' (eliminar archivo), 'restore' (restaurar archivo), 'create_folder' (crear carpeta) o 'move' (mover archivo). Si no está claro, responde 'unknown'."
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Eres un asistente que analiza intenciones en plataformas de almacenamiento en la nube."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content.strip().lower()

    def interpretar_accion_mensajeria(texto):
        prompt = f"El usuario dijo: '{texto}'. Determina si quiere 'reply' (responder un mensaje), 'react' (reaccionar con emoji) o 'mention' (mencionar a alguien). Si no está claro, responde 'unknown'."
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": "Eres un asistente que analiza intenciones en plataformas de mensajería."},
                    {"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip().lower()

    @app.route("/accion-gmail", methods=["POST"])
    def ejecutar_accion_gmail():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        message_id = data.get("message_id")  # Opcional, para acciones como delete o spam

        if not email or not user_text:
            return jsonify({"error": "Faltan parámetros: email y action_text son requeridos"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("Gmail", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        action = interpretar_accion_email(user_text)

        # 1. Eliminar correos
        if action == "delete":
            if message_id:  # Si se proporciona un message_id específico
                response = requests.post(f"https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}/trash", headers=headers)
                return jsonify({"success": "Correo eliminado"}) if response.status_code == 204 else jsonify({"error": "Error al eliminar correo"}), response.status_code
            else:  # Eliminar todos los correos de un remitente
                match = re.search(r'todos los correos de (.+)', user_text, re.IGNORECASE)
                if not match:
                    return jsonify({"error": "Debe especificar un remitente (ej: 'todos los correos de juan')"}), 400
                sender = match.group(1)
                list_url = "https://www.googleapis.com/gmail/v1/users/me/messages"
                params = {"q": f"from:{sender}"}
                list_response = requests.get(list_url, headers=headers, params=params)
                messages = list_response.json().get("messages", [])
                if not messages:
                    return jsonify({"error": f"No se encontraron correos del remitente {sender}"}), 404
                delete_results = []
                for msg in messages:
                    delete_url = f"https://www.googleapis.com/gmail/v1/users/me/messages/{msg['id']}/trash"
                    delete_response = requests.post(delete_url, headers=headers)
                    delete_results.append(delete_response.status_code == 204)
                return jsonify({"success": f"Se han eliminado {len(delete_results)} correos del remitente {sender}"})

        # 2. Mover a spam
        elif action == "spam":
            if message_id:  # Si se proporciona un message_id específico
                response = requests.post(
                    f"https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}/modify",
                    headers=headers,
                    json={"addLabelIds": ["SPAM"], "removeLabelIds": ["INBOX"]}
                )
                return jsonify({"success": "Correo marcado como spam"}) if response.status_code == 200 else jsonify({"error": "Error al marcar como spam"}), response.status_code
            else:  # Mover todos los correos de un remitente a spam
                match = re.search(r'todos los correos de (.+)', user_text, re.IGNORECASE)
                if not match:
                    return jsonify({"error": "Debe especificar un remitente (ej: 'todos los correos de juan')"}), 400
                sender = match.group(1)
                list_url = "https://www.googleapis.com/gmail/v1/users/me/messages"
                params = {"q": f"from:{sender}"}
                list_response = requests.get(list_url, headers=headers, params=params)
                messages = list_response.json().get("messages", [])
                if not messages:
                    return jsonify({"error": f"No se encontraron correos del remitente {sender}"}), 404
                spam_results = []
                for msg in messages:
                    modify_url = f"https://www.googleapis.com/gmail/v1/users/me/messages/{msg['id']}/modify"
                    modify_response = requests.post(modify_url, headers=headers, json={"addLabelIds": ["SPAM"], "removeLabelIds": ["INBOX"]})
                    spam_results.append(modify_response.status_code == 200)
                return jsonify({"success": f"Se han movido {len(spam_results)} correos del remitente {sender} a spam"})

        # 3. Agendar cita
        elif action == "schedule":
            prompt = f"El usuario dijo: '{user_text}'. Devuelve un JSON con los campos 'date', 'time' y 'subject' que representen la fecha, hora y asunto de la cita agendada (el asunto ponlo con inicial mayúscula en la primera palabra). Si no se puede extraer la información, devuelve 'unknown'."
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Eres un asistente que ayuda a organizar citas en Google Calendar."},
                    {"role": "user", "content": prompt}
                ]
            )
            ia_response = response.choices[0].message.content.strip().lower()
            try:
                match = re.search(r'\{[^}]*\}', ia_response, re.DOTALL | re.MULTILINE)
                parsed_info = json.loads(match.group(0))
                if parsed_info == 'unknown':
                    return jsonify({"error": "No se pudo interpretar la consulta para agendar"}), 400

                date_str = parsed_info['date']
                time_str = parsed_info['time']
                subject = parsed_info['subject']

                months = {
                    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
                    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
                }
                day, month_name = date_str.split(" de ")
                month = months.get(month_name.lower())
                if not month:
                    return jsonify({"error": "Mes no válido en la consulta"}), 400

                current_year = datetime.now().year
                hour = int(re.search(r'\d+', time_str).group())
                if "pm" in time_str.lower() and hour != 12:
                    hour += 12
                if "am" in time_str.lower() and hour == 12:
                    hour = 0

                event_datetime = datetime(current_year, month, int(day), hour, 0, 0, tzinfo=ZoneInfo("UTC"))
                event = {
                    "summary": subject,
                    "start": {"dateTime": event_datetime.isoformat(), "timeZone": "UTC"},
                    "end": {"dateTime": (event_datetime.replace(hour=event_datetime.hour + 1)).isoformat(), "timeZone": "UTC"}
                }

                url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
                response = requests.post(url, json=event, headers=headers)
                return jsonify({"success": f"Cita agendada: {subject} el {date_str} a las {time_str}"})
            except Exception as e:
                return jsonify({"error": f"Error al procesar la cita: {str(e)}"}), 500

        # 4. Crear borrador
        elif action == "draft":
            match = re.search(r'crear\s*borrador\s*con\s*asunto:\s*(.*?)\s*y\s*cuerpo:\s*(.*)', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Formato inválido. Ejemplo: 'crear borrador con asunto: Hola y cuerpo: Saludos'"}), 400

            asunto = match.group(1).strip()
            cuerpo = match.group(2).strip()

            mensaje = MIMEText(cuerpo)
            mensaje["Subject"] = asunto
            mensaje_bytes = mensaje.as_bytes()
            mensaje_base64 = base64.urlsafe_b64encode(mensaje_bytes).decode()

            borrador = {"message": {"raw": mensaje_base64}}
            url = "https://www.googleapis.com/gmail/v1/users/me/drafts"
            response = requests.post(url, json=borrador, headers=headers)
            return jsonify({"success": f"Borrador creado con asunto '{asunto}'"}) if response.status_code == 200 else jsonify({"error": "Error al crear borrador"}), response.status_code

        # 5. Enviar correo
        elif action == "send":
            match = re.search(r'enviar\s*correo\s*a\s*([\w\.-@,\s]+)\s*con\s*asunto:\s*(.*?)\s*y\s*cuerpo:\s*(.*)', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Formato inválido. Ejemplo: 'enviar correo a pepe@gmail.com con asunto: Hola y cuerpo: Saludos'"}), 400

            destinatario = match.group(1).strip()
            asunto = match.group(2).strip()
            cuerpo = match.group(3).strip()

            mensaje = MIMEText(cuerpo)
            mensaje["To"] = destinatario
            mensaje["Subject"] = asunto
            mensaje["From"] = "me"
            mensaje_bytes = mensaje.as_bytes()
            mensaje_base64 = base64.urlsafe_b64encode(mensaje_bytes).decode()

            correo = {"raw": mensaje_base64}
            url = "https://www.googleapis.com/gmail/v1/users/me/messages/send"
            response = requests.post(url, json=correo, headers=headers)
            return jsonify({"success": f"Correo enviado a {destinatario}"}) if response.status_code == 200 else jsonify({"error": "Error al enviar correo"}), response.status_code

        # Acción no reconocida
        return jsonify({"error": "Acción no reconocida o no implementada"}), 400

    @app.route("/accion-outlook", methods=["POST"])
    def ejecutar_accion_outlook():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        message_id = data.get("message_id")

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("Outlook", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        action = interpretar_accion_email(user_text)
        headers = get_outlook_headers(token)

        if "delete" in action:
            response = requests.delete(f"https://graph.microsoft.com/v1.0/me/messages/{message_id}", headers=headers)
            return jsonify({"success": "Correo eliminado"}) if response.status_code == 204 else jsonify({"success": "Correo eliminado"})

        elif "reply" in action:
            reply_text = data.get("reply_text", "")
            response = requests.post(f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/reply",
                                    headers=headers, json={"comment": reply_text})
            return jsonify({"success": "Respuesta enviada"}) if response.status_code == 200 else jsonify({"error": "Error al responder correo"}), response.status_code

        elif "spam" in action:
            response = requests.post(f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/move",
                                    headers=headers, json={"destinationId": "JunkEmail"})
            return jsonify({"success": "Correo marcado como spam"}) if response.status_code == 200 else jsonify({"success": "Correo marcado como spam"})

        return jsonify({"error": "Acción no reconocida"}), 400

    @app.route("/accion-notion", methods=["POST"])
    def ejecutar_accion_notion():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        page_id = data.get("message_id")  # Usado como page_id en Notion

        if not email or not user_text:
            return jsonify({"error": "Faltan parámetros: email y action_text son requeridos"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("Notion", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"  # Versión requerida por la API de Notion
        }

        action = interpretar_accion_productividad(user_text)

        # Función auxiliar para buscar task_id por nombre (adaptada de post_to_notion)
        def get_task_id_notion(task_name):
            # Nota: Necesitas el ID de la base de datos de Notion donde están las tareas.
            # Esto debe configurarse en tu aplicación o pasarse como parámetro adicional.
            database_id = "YOUR_DATABASE_ID"  # ¡Reemplaza esto con el ID real de tu base de datos!
            url = f"https://api.notion.com/v1/databases/{database_id}/query"
            data = {
                "filter": {
                    "property": "Name",  # Asegúrate de que "Name" sea el nombre exacto de la propiedad en tu base de datos
                    "title": {"equals": task_name}  # Usamos "title" porque "Name" suele ser un título en Notion
                }
            }
            response = requests.post(url, headers=headers, json=data)
            if response.status_code == 200:
                results = response.json().get("results", [])
                if results:
                    return results[0]["id"]
            return None

        # 1. Marcar como completada
        if action == "mark_done":
            if not page_id:  # Si no se proporciona page_id, buscar por nombre
                match = re.search(r'marca como completada la tarea (.+)', user_text, re.IGNORECASE)
                if not match:
                    return jsonify({"error": "Debe especificar el nombre de la tarea (ej: 'marca como completada la tarea Reunion')"}), 400
                task_name = match.group(1).strip()
                page_id = get_task_id_notion(task_name)
                if not page_id:
                    return jsonify({"error": f"No se encontró la tarea '{task_name}' en Notion"}), 404

            # Actualizar el estado a "Completed" (ajusta "Completed" al nombre real en tu base de datos)
            response = requests.patch(
                f"https://api.notion.com/v1/pages/{page_id}",
                headers=headers,
                json={
                    "properties": {
                        "Status": {  # Asegúrate de que "Status" sea el nombre exacto de la propiedad en tu base de datos
                            "select": {"name": "Completed"}  # Cambia "Completed" por el valor real (ej: "Done", "Completada")
                        }
                    }
                }
            )
            return jsonify({"success": f"Tarea marcada como completada"}) if response.status_code == 200 else jsonify({"error": "Error al actualizar estado"}), response.status_code

        # 2. Eliminar (archivar)
        elif action == "delete":
            if not page_id:  # Si no se proporciona page_id, buscar por nombre
                match = re.search(r'elimina la tarea (.+)', user_text, re.IGNORECASE)
                if not match:
                    return jsonify({"error": "Debe especificar el nombre de la tarea (ej: 'elimina la tarea Reunion')"}), 400
                task_name = match.group(1).strip()
                page_id = get_task_id_notion(task_name)
                if not page_id:
                    return jsonify({"error": f"No se encontró la tarea '{task_name}' en Notion"}), 404

            # Archivar la página (Notion no permite eliminar directamente, solo archivar)
            response = requests.patch(
                f"https://api.notion.com/v1/pages/{page_id}",
                headers=headers,
                json={"archived": True}
            )
            return jsonify({"success": f"Tarea archivada"}) if response.status_code == 200 else jsonify({"error": "Error al archivar tarea"}), response.status_code

        # Acción no reconocida
        return jsonify({"error": "Acción no reconocida o no implementada"}), 400

    @app.route("/accion-drive", methods=["POST"])
    def ejecutar_accion_drive():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        file_id = data.get("file_id")  # Opcional, para acciones sobre un archivo/carpeta específico

        if not email or not user_text:
            return jsonify({"error": "Faltan parámetros: email y action_text son requeridos"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("Drive", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        action = interpretar_accion_archivos(user_text)

        # Función auxiliar para buscar file_id por nombre
        def get_file_id_by_name(name, is_folder=False):
            url = "https://www.googleapis.com/drive/v3/files"
            mime_type = "application/vnd.google-apps.folder" if is_folder else None
            params = {
                "q": f"name contains '{name}' trashed=false",
                "spaces": "drive",
                "fields": "files(id, name)"
            }
            if mime_type:
                params["q"] += f" mimeType='{mime_type}'"
            response = requests.get(url, headers=headers, params=params)
            files = response.json().get("files", [])
            if not files:
                return None
            if len(files) > 1:
                return None  # Si hay múltiples coincidencias, requerimos más especificidad
            return files[0]["id"]

        # 1. Eliminar archivo
        if action == "delete":
            if not file_id:  # Buscar por nombre si no se proporciona file_id
                match = re.search(r'(eliminar\s*archivo|archivo):\s*(.+)', user_text, re.IGNORECASE)
                if not match:
                    return jsonify({"error": "Debe especificar el nombre del archivo (ej: 'eliminar archivo: documento')"}), 400
                file_name = match.group(2).strip()
                file_id = get_file_id_by_name(file_name)
                if not file_id:
                    return jsonify({"error": f"No se encontró un archivo único con el nombre '{file_name}'"}), 404

            response = requests.patch(
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                headers=headers,
                json={"trashed": True}
            )
            return jsonify({"success": "Archivo movido a la papelera"}) if response.status_code == 200 else jsonify({"error": "Error al eliminar archivo"}), response.status_code

        # 2. Renombrar archivo
        elif action == "rename":
            if not file_id:
                return jsonify({"error": "Se requiere file_id para renombrar un archivo"}), 400
            new_name = data.get("new_name", "")
            if not new_name:
                return jsonify({"error": "Se requiere new_name para renombrar"}), 400
            response = requests.patch(
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                headers=headers,
                json={"name": new_name}
            )
            return jsonify({"success": "Archivo renombrado"}) if response.status_code == 200 else jsonify({"error": "Error al renombrar archivo"}), response.status_code

        # 3. Compartir archivo/carpeta
        elif action == "share":
            match = re.search(r'compartir\s*(archivo|carpeta)\s*[:\s]*(\S.*)\s*con\s*(.+)', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Formato inválido. Ejemplo: 'compartir archivo: doc con user@example.com'"}), 400
            file_type = match.group(1).strip()  # "archivo" o "carpeta"
            file_name = match.group(2).strip()
            recipients = match.group(3).strip()

            if not file_id:
                file_id = get_file_id_by_name(file_name, is_folder=(file_type == "carpeta"))
                if not file_id:
                    return jsonify({"error": f"No se encontró un {file_type} único con el nombre '{file_name}'"}), 404

            for recipient in recipients.split(','):
                email = recipient.strip()
                permission_url = f"https://www.googleapis.com/drive/v3/files/{file_id}/permissions"
                permission_data = {
                    "type": "user",
                    "role": "reader",  # Cambia a "writer" si deseas permisos de escritura
                    "emailAddress": email
                }
                response = requests.post(permission_url, headers=headers, json=permission_data)
                if response.status_code != 200:
                    return jsonify({"error": f"Error al compartir con {email}"}), response.status_code
            return jsonify({"success": f"{file_type.capitalize()} '{file_name}' compartido con {recipients}"})

        # 4. Mover archivo
        elif action == "move":
            match = re.search(r'archivo:(.+?) a carpeta:(.+)', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Formato inválido. Ejemplo: 'mover archivo: doc a carpeta: Trabajo'"}), 400
            file_name = match.group(1).strip()
            folder_name = match.group(2).strip()

            if not file_id:
                file_id = get_file_id_by_name(file_name)
                if not file_id:
                    return jsonify({"error": f"No se encontró un archivo único con el nombre '{file_name}'"}), 404

            folder_id = get_file_id_by_name(folder_name, is_folder=True)
            if not folder_id:
                return jsonify({"error": f"No se encontró una carpeta única con el nombre '{folder_name}'"}), 404

            response = requests.patch(
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                headers=headers,
                json={"addParents": folder_id}
            )
            return jsonify({"success": f"Archivo '{file_name}' movido a la carpeta '{folder_name}'"}) if response.status_code == 200 else jsonify({"error": "Error al mover archivo"}), response.status_code

        # 5. Crear carpeta
        elif action == "create_folder":
            match = re.search(r'crear\s*carpeta:\s*(.+)', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Formato inválido. Ejemplo: 'crear carpeta: Nueva'"}), 400
            folder_name = match.group(1).strip()
            metadata = {
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder"
            }
            response = requests.post("https://www.googleapis.com/drive/v3/files", headers=headers, json=metadata)
            return jsonify({"success": f"Carpeta '{folder_name}' creada"}) if response.status_code == 200 else jsonify({"error": "Error al crear carpeta"}), response.status_code

        # 6. Vaciar papelera
        elif action == "empty_trash":
            response = requests.delete("https://www.googleapis.com/drive/v3/files/trash", headers=headers)
            return jsonify({"success": "Papelera vaciada"}) if response.status_code == 204 else jsonify({"error": "Error al vaciar papelera"}), response.status_code

        # Acción no reconocida
        return jsonify({"error": "Acción no reconocida o no implementada"}), 400

    @app.route("/accion-slack", methods=["POST"])
    def ejecutar_accion_slack():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        message_ts = data.get("message_id")  # Timestamp del mensaje al que se responde o reacciona
        channel = data.get("channel")  # Canal donde ocurre la acción

        if not email or not user_text or not channel:
            return jsonify({"error": "Faltan parámetros: email, action_text y channel son requeridos"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("Slack", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        action = interpretar_accion_mensajeria(user_text)

        # 1. Responder a un mensaje
        if action == "reply":
            if not message_ts:
                return jsonify({"error": "Se requiere message_id (thread_ts) para responder"}), 400
            reply_text = data.get("reply_text", "")
            if not reply_text:
                return jsonify({"error": "Se requiere reply_text para responder"}), 400
            response = requests.post(
                "https://slack.com/api/chat.postMessage",
                headers=headers,
                json={
                    "channel": channel,
                    "thread_ts": message_ts,
                    "text": reply_text
                }
            )
            if response.status_code == 200 and response.json().get("ok"):
                return jsonify({"success": "Mensaje respondido"})
            return jsonify({"error": "Error al responder mensaje", "details": response.json().get("error")}), response.status_code

        # 2. Reaccionar a un mensaje
        elif action == "react":
            if not message_ts:
                return jsonify({"error": "Se requiere message_id (timestamp) para reaccionar"}), 400
            # Extraer el emoji del texto (ej: "reacciona con :smile:")
            match = re.search(r'reacci(ona|onar)\s*(con)?\s*:?(\w+):?', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Debe especificar un emoji (ej: 'reacciona con smile')"}), 400
            emoji = match.group(3).strip()
            
            response = requests.post(
                "https://slack.com/api/reactions.add",
                headers=headers,
                json={
                    "channel": channel,
                    "timestamp": message_ts,
                    "name": emoji
                }
            )
            if response.status_code == 200 and response.json().get("ok"):
                return jsonify({"success": f"Reacción '{emoji}' añadida"})
            return jsonify({"error": "Error al añadir reacción", "details": response.json().get("error")}), response.status_code

        # 3. Mencionar a alguien
        elif action == "mention":
            match = re.search(r'menciona[r]?\s*a\s+(.+)', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Debe especificar a quién mencionar (ej: 'menciona a Juan')"}), 400
            mention_target = match.group(1).strip()

            # Nota: Necesitamos convertir el nombre a un ID de usuario de Slack.
            # Esto requiere una llamada a users.list o una base de datos local de nombres a IDs.
            # Por simplicidad, asumiremos que mention_target es un nombre y lo convertimos a formato de mención básico.
            # Para una implementación real, busca el ID con users.list.
            mention_text = f"<@{mention_target}>"
            response = requests.post(
                "https://slack.com/api/chat.postMessage",
                headers=headers,
                json={
                    "channel": channel,
                    "text": f"Hola {mention_text}"
                }
            )
            if response.status_code == 200 and response.json().get("ok"):
                return jsonify({"success": f"Mención enviada a {mention_target}"})
            return jsonify({"error": "Error al enviar mención", "details": response.json().get("error")}), response.status_code

        # Acción no reconocida
        return jsonify({"error": "Acción no reconocida o no implementada"}), 400

    @app.route("/accion-asana", methods=["POST"])
    def ejecutar_accion_asana():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        task_id = data.get("message_id")  # Usado como task_id en Asana

        if not email or not user_text:
            return jsonify({"error": "Faltan parámetros: email y action_text son requeridos"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("Asana", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        action = interpretar_accion_productividad(user_text)

        # Función auxiliar para buscar task_id por nombre (adaptada de post_to_asana)
        def get_task_id_asana(name):
            url = "https://app.asana.com/api/1.0/tasks"
            params = {"opt_fields": "name,gid"}  # gid es el ID de la tarea en Asana
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                tasks = response.json().get('data', [])
                for task in tasks:
                    if task["name"].lower() == name.lower():
                        return task["gid"]
            return None

        # 1. Marcar como completada
        if action in ["mark_done", "complete"]:  # Soporta ambos términos
            if not task_id:  # Si no se proporciona task_id, buscar por nombre
                match = re.search(r'marca[r]?\s*como\s*completada\s*la\s*tarea\s*(.+)', user_text, re.IGNORECASE)
                if not match:
                    return jsonify({"error": "Debe especificar el nombre de la tarea (ej: 'marca como completada la tarea Reunion')"}), 400
                task_name = match.group(1).strip()
                task_id = get_task_id_asana(task_name)
                if not task_id:
                    return jsonify({"error": f"No se encontró la tarea '{task_name}' en Asana"}), 404

            response = requests.put(
                f"https://app.asana.com/api/1.0/tasks/{task_id}",
                headers=headers,
                json={"data": {"completed": True}}
            )
            return jsonify({"success": "Tarea completada"}) if response.status_code == 200 else jsonify({"error": "Error al completar tarea"}), response.status_code

        # 2. Eliminar tarea
        elif action == "delete":
            if not task_id:  # Si no se proporciona task_id, buscar por nombre
                match = re.search(r'elimina[r]?\s*la\s*tarea\s*(.+)', user_text, re.IGNORECASE)
                if not match:
                    return jsonify({"error": "Debe especificar el nombre de la tarea (ej: 'elimina la tarea Reunion')"}), 400
                task_name = match.group(1).strip()
                task_id = get_task_id_asana(task_name)
                if not task_id:
                    return jsonify({"error": f"No se encontró la tarea '{task_name}' en Asana"}), 404

            response = requests.delete(
                f"https://app.asana.com/api/1.0/tasks/{task_id}",
                headers=headers
            )
            return jsonify({"success": "Tarea eliminada"}) if response.status_code == 204 else jsonify({"error": "Error al eliminar tarea"}), response.status_code

        # Acción no reconocida
        return jsonify({"error": "Acción no reconocida o no implementada"}), 400

    @app.route("/accion-clickup", methods=["POST"])
    def ejecutar_accion_clickup():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        task_id = data.get("message_id")  # Usado como task_id en ClickUp

        if not email or not user_text:
            return jsonify({"error": "Faltan parámetros: email y action_text son requeridos"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("ClickUp", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        headers = {
            "Authorization": token,
            "Content-Type": "application/json"
        }

        action = interpretar_accion_productividad(user_text)

        # Función auxiliar para buscar task_id por nombre (adaptada de post_to_clickup)
        def get_task_id_clickup(task_name):
            # Nota: ClickUp requiere un list_id para buscar tareas. Esto debe configurarse o pasarse como parámetro.
            list_id = "YOUR_LIST_ID"  # ¡Reemplaza con el ID real de tu lista o pásalo en el JSON!
            url = f"https://api.clickup.com/api/v2/list/{list_id}/task"
            params = {"subtasks": True}  # Incluir subtareas si es necesario
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                tasks = response.json().get("tasks", [])
                for task in tasks:
                    if task["name"].lower() == task_name.lower():
                        return task["id"]
            return None

        # 1. Marcar como completada
        if action == "mark_done":
            if not task_id:  # Si no se proporciona task_id, buscar por nombre
                match = re.search(r'marca[r]?\s*como\s*completada\s*la\s*tarea\s*(.+)', user_text, re.IGNORECASE)
                if not match:
                    return jsonify({"error": "Debe especificar el nombre de la tarea (ej: 'marca como completada la tarea Reunion')"}), 400
                task_name = match.group(1).strip()
                task_id = get_task_id_clickup(task_name)
                if not task_id:
                    return jsonify({"error": f"No se encontró la tarea '{task_name}' en ClickUp"}), 404

            # Obtener los estados disponibles para la lista de la tarea
            task_response = requests.get(f"https://api.clickup.com/api/v2/task/{task_id}", headers=headers)
            if task_response.status_code != 200:
                return jsonify({"error": "Error al obtener detalles de la tarea"}), task_response.status_code
            task_data = task_response.json()
            list_id = task_data["list"]["id"]

            # Obtener los estados de la lista
            list_response = requests.get(f"https://api.clickup.com/api/v2/list/{list_id}", headers=headers)
            if list_response.status_code != 200:
                return jsonify({"error": "Error al obtener estados de la lista"}), list_response.status_code
            statuses = [status["status"] for status in list_response.json().get("statuses", [])]
            completed_status = next((s for s in statuses if s.lower() in ["complete", "done", "closed"]), statuses[-1] if statuses else "complete")

            response = requests.put(
                f"https://api.clickup.com/api/v2/task/{task_id}",
                headers=headers,
                json={"status": completed_status}
            )
            return jsonify({"success": "Tarea completada"}) if response.status_code == 200 else jsonify({"error": "Error al completar tarea"}), response.status_code

        # 2. Eliminar tarea
        elif action == "delete":
            if not task_id:  # Si no se proporciona task_id, buscar por nombre
                match = re.search(r'elimina[r]?\s*la\s*tarea\s*(.+)', user_text, re.IGNORECASE)
                if not match:
                    return jsonify({"error": "Debe especificar el nombre de la tarea (ej: 'elimina la tarea Reunion')"}), 400
                task_name = match.group(1).strip()
                task_id = get_task_id_clickup(task_name)
                if not task_id:
                    return jsonify({"error": f"No se encontró la tarea '{task_name}' en ClickUp"}), 404

            response = requests.delete(
                f"https://api.clickup.com/api/v2/task/{task_id}",
                headers=headers
            )
            return jsonify({"success": "Tarea eliminada"}) if response.status_code == 200 else jsonify({"error": "Error al eliminar tarea"}), response.status_code

        # 3. Cambiar estado
        elif action == "change_status":
            match = re.search(r'cambia[r]?\s*el\s*estado\s*a\s*(.+?)\s*la\s*tarea\s*(.+)', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Formato inválido. Ejemplo: 'cambia el estado a En Progreso la tarea Reunion'"}), 400
            new_status = match.group(1).strip()
            task_name = match.group(2).strip()

            if not task_id:
                task_id = get_task_id_clickup(task_name)
                if not task_id:
                    return jsonify({"error": f"No se encontró la tarea '{task_name}' en ClickUp"}), 404

            # Obtener los estados disponibles
            task_response = requests.get(f"https://api.clickup.com/api/v2/task/{task_id}", headers=headers)
            if task_response.status_code != 200:
                return jsonify({"error": "Error al obtener detalles de la tarea"}), task_response.status_code
            task_data = task_response.json()
            list_id = task_data["list"]["id"]

            list_response = requests.get(f"https://api.clickup.com/api/v2/list/{list_id}", headers=headers)
            if list_response.status_code != 200:
                return jsonify({"error": "Error al obtener estados de la lista"}), list_response.status_code
            statuses = [status["status"] for status in list_response.json().get("statuses", [])]
            valid_status = next((s for s in statuses if s.lower() == new_status.lower()), None)
            if not valid_status:
                return jsonify({"error": f"Estado '{new_status}' no válido. Estados disponibles: {', '.join(statuses)}"}), 400

            response = requests.put(
                f"https://api.clickup.com/api/v2/task/{task_id}",
                headers=headers,
                json={"status": valid_status}
            )
            return jsonify({"success": f"Estado cambiado a '{valid_status}'"}) if response.status_code == 200 else jsonify({"error": "Error al cambiar estado"}), response.status_code

        # Acción no reconocida
        return jsonify({"error": "Acción no reconocida o no implementada"}), 400

    @app.route("/accion-hubspot", methods=["POST"])
    def ejecutar_accion_hubspot():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        deal_id = data.get("deal_id")  # ID del negocio (opcional)
        contact_id = data.get("contact_id")  # ID del contacto (opcional)
        company_id = data.get("company_id")  # ID de la empresa (opcional)

        if not email or not user_text:
            return jsonify({"error": "Faltan parámetros: email y action_text son requeridos"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("HubSpot", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        action = interpretar_accion_hubspot(user_text)

        # Función auxiliar para buscar deal_id por nombre
        def get_deal_id_by_name(deal_name):
            url = "https://api.hubapi.com/crm/v3/objects/deals/search"
            payload = {
                "filterGroups": [{"filters": [{"propertyName": "dealname", "operator": "EQ", "value": deal_name}]}],
                "properties": ["dealname"],
                "limit": 1
            }
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                results = response.json().get("results", [])
                if results:
                    return results[0]["id"]
            return None

        # Función auxiliar para buscar contact_id por email
        def get_contact_id_by_email(email):
            url = "https://api.hubapi.com/crm/v3/objects/contacts/search"
            payload = {
                "filterGroups": [{"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}],
                "properties": ["email"],
                "limit": 1
            }
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                results = response.json().get("results", [])
                if results:
                    return results[0]["id"]
            return None

        # Función auxiliar para buscar company_id por nombre
        def get_company_id_by_name(company_name):
            url = "https://api.hubapi.com/crm/v3/objects/companies/search"
            payload = {
                "filterGroups": [{"filters": [{"propertyName": "name", "operator": "EQ", "value": company_name}]}],
                "properties": ["name"],
                "limit": 1
            }
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                results = response.json().get("results", [])
                if results:
                    return results[0]["id"]
            return None

        # 1. Actualizar negocio
        if action == "update":
            if not deal_id:
                match = re.search(r'actualiza[r]?\s*(el\s*negocio)?\s*(.+?)\s*a\s*(.+)', user_text, re.IGNORECASE)
                if not match:
                    return jsonify({"error": "Formato inválido. Ejemplo: 'actualizar el negocio Proyecto X a Cerrado'"}), 400
                deal_name = match.group(2).strip()
                new_stage = match.group(3).strip()
                deal_id = get_deal_id_by_name(deal_name)
                if not deal_id:
                    return jsonify({"error": f"No se encontró el negocio '{deal_name}'"}), 404
            else:
                new_stage = data.get("new_stage", "")
                if not new_stage:
                    match = re.search(r'actualiza[r]?\s*(el\s*negocio)?\s*a\s*(.+)', user_text, re.IGNORECASE)
                    if not match:
                        return jsonify({"error": "Debe especificar el nuevo estado"}), 400
                    new_stage = match.group(2).strip()

            response = requests.patch(
                f"https://api.hubapi.com/crm/v3/objects/deals/{deal_id}",
                headers=headers,
                json={"properties": {"dealstage": new_stage}}
            )
            return jsonify({"success": "Negocio actualizado"}) if response.status_code == 200 else jsonify({"error": "Error al actualizar negocio"}), response.status_code

        # 2. Crear negocio
        elif action == "create":
            match = re.search(r'crea[r]?\s*(un\s*negocio)?\s*(.+?)(?:\s*en\s*(.+))?', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Formato inválido. Ejemplo: 'crear negocio Proyecto X en En Progreso'"}), 400
            deal_name = match.group(2).strip()
            deal_stage = match.group(3).strip() if match.group(3) else "presentationscheduled"

            response = requests.post(
                "https://api.hubapi.com/crm/v3/objects/deals",
                headers=headers,
                json={
                    "properties": {
                        "dealname": deal_name,
                        "dealstage": deal_stage,
                        "amount": "0",
                        "pipeline": "default"
                    }
                }
            )
            if response.status_code == 201:
                new_deal_id = response.json().get("id")
                return jsonify({"success": f"Negocio '{deal_name}' creado", "deal_id": new_deal_id})
            return jsonify({"error": "Error al crear negocio"}), response.status_code

        # 3. Comentar en negocio
        elif action == "comment":
            if not deal_id:
                match = re.search(r'comenta[r]?\s*(en\s*el\s*negocio)?\s*(.+?)\s*:\s*(.+)', user_text, re.IGNORECASE)
                if not match:
                    return jsonify({"error": "Formato inválido. Ejemplo: 'comentar en el negocio Proyecto X: Reunión programada'"}), 400
                deal_name = match.group(2).strip()
                comment_text = match.group(3).strip()
                deal_id = get_deal_id_by_name(deal_name)
                if not deal_id:
                    return jsonify({"error": f"No se encontró el negocio '{deal_name}'"}), 404
            else:
                comment_text = data.get("comment_text", "")
                if not comment_text:
                    match = re.search(r'comenta[r]?:\s*(.+)', user_text, re.IGNORECASE)
                    if not match:
                        return jsonify({"error": "Debe especificar el comentario"}), 400
                    comment_text = match.group(1).strip()

            response = requests.post(
                "https://api.hubapi.com/crm/v3/objects/notes",
                headers=headers,
                json={
                    "properties": {
                        "hs_note_body": comment_text,
                        "hs_object_id": deal_id,
                        "hs_association_type": "deal"
                    },
                    "associations": [{"to": {"id": deal_id}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 20}]}]
                }
            )
            return jsonify({"success": "Comentario añadido al negocio"}) if response.status_code == 201 else jsonify({"error": "Error al añadir comentario"}), response.status_code

        # 4. Crear contacto
        elif action == "create_contact":
            match = re.search(r'crea[r]?\s*(un\s*contacto)?\s*(.+?)\s*con\s*email\s*(.+)', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Formato inválido. Ejemplo: 'crear contacto Juan con email juan@example.com'"}), 400
            contact_name = match.group(2).strip()
            contact_email = match.group(3).strip()

            response = requests.post(
                "https://api.hubapi.com/crm/v3/objects/contacts",
                headers=headers,
                json={
                    "properties": {
                        "firstname": contact_name.split()[0],  # Asume el primer nombre
                        "lastname": " ".join(contact_name.split()[1:]) if len(contact_name.split()) > 1 else "",
                        "email": contact_email
                    }
                }
            )
            if response.status_code == 201:
                new_contact_id = response.json().get("id")
                return jsonify({"success": f"Contacto '{contact_name}' creado", "contact_id": new_contact_id})
            return jsonify({"error": "Error al crear contacto"}), response.status_code

        # 5. Eliminar contacto
        elif action == "delete_contact":
            if not contact_id:
                match = re.search(r'elimina[r]?\s*(el\s*contacto)?\s*(?:email\s*)?(.+)', user_text, re.IGNORECASE)
                if not match:
                    return jsonify({"error": "Formato inválido. Ejemplo: 'eliminar contacto juan@example.com' o 'eliminar contacto Juan'"}), 400
                identifier = match.group(2).strip()
                if "@" in identifier:  # Si es un email
                    contact_id = get_contact_id_by_email(identifier)
                else:  # Si es un nombre, buscar por email no es viable sin más datos, asumimos ID o error
                    return jsonify({"error": "Proporcione un email o contact_id para eliminar un contacto"}), 400
                if not contact_id:
                    return jsonify({"error": f"No se encontró el contacto con email '{identifier}'"}), 404

            response = requests.delete(
                f"https://api.hubapi.com/crm/v3/objects/contacts/{contact_id}",
                headers=headers
            )
            return jsonify({"success": "Contacto eliminado"}) if response.status_code == 204 else jsonify({"error": "Error al eliminar contacto"}), response.status_code

        # 6. Crear empresa
        elif action == "create_company":
            match = re.search(r'crea[r]?\s*(una\s*empresa)?\s*(.+)', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Formato inválido. Ejemplo: 'crear empresa Acme Corp'"}), 400
            company_name = match.group(2).strip()

            response = requests.post(
                "https://api.hubapi.com/crm/v3/objects/companies",
                headers=headers,
                json={
                    "properties": {
                        "name": company_name,
                        "domain": f"{company_name.lower().replace(' ', '')}.com"  # Opcional, ajusta según necesidad
                    }
                }
            )
            if response.status_code == 201:
                new_company_id = response.json().get("id")
                return jsonify({"success": f"Empresa '{company_name}' creada", "company_id": new_company_id})
            return jsonify({"error": "Error al crear empresa"}), response.status_code

        # 7. Eliminar empresa
        elif action == "delete_company":
            if not company_id:
                match = re.search(r'elimina[r]?\s*(la\s*empresa)?\s*(.+)', user_text, re.IGNORECASE)
                if not match:
                    return jsonify({"error": "Formato inválido. Ejemplo: 'eliminar empresa Acme Corp'"}), 400
                company_name = match.group(2).strip()
                company_id = get_company_id_by_name(company_name)
                if not company_id:
                    return jsonify({"error": f"No se encontró la empresa '{company_name}'"}), 404

            response = requests.delete(
                f"https://api.hubapi.com/crm/v3/objects/companies/{company_id}",
                headers=headers
            )
            return jsonify({"success": "Empresa eliminada"}) if response.status_code == 204 else jsonify({"error": "Error al eliminar empresa"}), response.status_code

        # Acción no reconocida
        return jsonify({"error": "Acción no reconocida o no implementada"}), 400

    @app.route("/accion-dropbox", methods=["POST"])
    def ejecutar_accion_dropbox():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        file_path = data.get("file_path")  # Ruta del archivo o carpeta en Dropbox

        if not email or not user_text:
            return jsonify({"error": "Faltan parámetros: email y action_text son requeridos"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("Dropbox", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        action = interpretar_accion_archivos(user_text)

        # 1. Eliminar archivo o carpeta
        if action == "delete":
            if not file_path:
                match = re.search(r'(eliminar\s*(archivo|carpeta)\s*[:\s]*)(.+)', user_text, re.IGNORECASE)
                if not match:
                    return jsonify({"error": "Debe especificar la ruta del archivo o carpeta (ej: 'eliminar archivo: /doc.txt')"}), 400
                file_path = match.group(3).strip()
                if not file_path.startswith('/'):
                    file_path = f"/{file_path}"

            response = requests.post(
                "https://api.dropboxapi.com/2/files/delete_v2",
                headers=headers,
                json={"path": file_path}
            )
            return jsonify({"success": "Archivo o carpeta eliminado"}) if response.status_code == 200 else jsonify({"error": "Error al eliminar"}, response.status_code)

        # 2. Restaurar archivo
        elif action == "restore":
            if not file_path:
                match = re.search(r'restaurar\s*archivo\s*[:\s]*(.+)', user_text, re.IGNORECASE)
                if not match:
                    return jsonify({"error": "Debe especificar la ruta del archivo (ej: 'restaurar archivo: /doc.txt')"}), 400
                file_path = match.group(1).strip()
                if not file_path.startswith('/'):
                    file_path = f"/{file_path}"

            # Obtener revisiones del archivo para encontrar la más reciente
            response = requests.post(
                "https://api.dropboxapi.com/2/files/list_revisions",
                headers=headers,
                json={"path": file_path, "limit": 1}
            )
            if response.status_code != 200 or not response.json().get("entries"):
                return jsonify({"error": "No se encontraron revisiones para restaurar"}), response.status_code
            revision = response.json()["entries"][0]["rev"]

            # Restaurar a la última revisión
            response = requests.post(
                "https://api.dropboxapi.com/2/files/restore",
                headers=headers,
                json={"path": file_path, "rev": revision}
            )
            return jsonify({"success": "Archivo restaurado"}) if response.status_code == 200 else jsonify({"error": "Error al restaurar archivo"}, response.status_code)

        # 3. Crear carpeta
        elif action == "create_folder":
            if not file_path:
                match = re.search(r'crear\s*carpeta\s*[:\s]*(.+)', user_text, re.IGNORECASE)
                if not match:
                    return jsonify({"error": "Debe especificar la ruta de la carpeta (ej: 'crear carpeta: /nueva')"}), 400
                file_path = match.group(1).strip()
                if not file_path.startswith('/'):
                    file_path = f"/{file_path}"

            response = requests.post(
                "https://api.dropboxapi.com/2/files/create_folder_v2",
                headers=headers,
                json={"path": file_path, "autorename": True}
            )
            return jsonify({"success": "Carpeta creada"}) if response.status_code == 200 else jsonify({"error": "Error al crear carpeta"}, response.status_code)

        # 4. Mover archivo
        elif action == "move":
            if not file_path:
                match = re.search(r'archivo\s*[:\s]*(.+?)\s*a\s*carpeta\s*[:\s]*(.+)', user_text, re.IGNORECASE)
                if not match:
                    return jsonify({"error": "Formato inválido. Ejemplo: 'mover archivo: /doc.txt a carpeta: /nueva'"}), 400
                file_path = match.group(1).strip()
                if not file_path.startswith('/'):
                    file_path = f"/{file_path}"
                dest_folder = match.group(2).strip()
                if not dest_folder.startswith('/'):
                    dest_folder = f"/{dest_folder}"
            else:
                dest_folder = data.get("dest_folder", "")
                if not dest_folder:
                    return jsonify({"error": "Debe especificar la carpeta de destino en dest_folder o en el texto"}), 400
                if not dest_folder.startswith('/'):
                    dest_folder = f"/{dest_folder}"

            response = requests.post(
                "https://api.dropboxapi.com/2/files/move_v2",
                headers=headers,
                json={
                    "from_path": file_path,
                    "to_path": f"{dest_folder}/{file_path.split('/')[-1]}",
                    "autorename": True
                }
            )
            return jsonify({"success": "Archivo movido"}) if response.status_code == 200 else jsonify({"error": "Error al mover archivo"}, response.status_code)

        # Acción no reconocida
        return jsonify({"error": "Acción no reconocida o no implementada"}), 400

    @app.route("/accion-onedrive", methods=["POST"])
    def ejecutar_accion_onedrive():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        file_id = data.get("file_id")  # ID del archivo o carpeta en OneDrive

        if not email or not user_text:
            return jsonify({"error": "Faltan parámetros: email y action_text son requeridos"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("OneDrive", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        action = interpretar_accion_archivos(user_text)

        # Función auxiliar para buscar file_id por nombre
        def get_file_id_by_name(file_name, is_folder=False):
            url = "https://graph.microsoft.com/v1.0/me/drive/root/search(q='{file_name}')"
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                items = response.json().get("value", [])
                for item in items:
                    if item["name"].lower() == file_name.lower() and ("folder" in item) == is_folder:
                        return item["id"]
            return None

        # 1. Eliminar archivo o carpeta
        if action == "delete":
            if not file_id:
                match = re.search(r'(eliminar\s*(archivo|carpeta)\s*[:\s]*)(.+)', user_text, re.IGNORECASE)
                if not match:
                    return jsonify({"error": "Debe especificar el nombre del archivo o carpeta (ej: 'eliminar archivo: doc.txt')"}), 400
                file_name = match.group(3).strip()
                is_folder = match.group(2).lower() == "carpeta"
                file_id = get_file_id_by_name(file_name, is_folder)
                if not file_id:
                    return jsonify({"error": f"No se encontró el {'carpeta' if is_folder else 'archivo'} '{file_name}'"}), 404

            response = requests.delete(
                f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}",
                headers=headers
            )
            return jsonify({"success": "Archivo o carpeta eliminado"}) if response.status_code == 204 else jsonify({"error": "Error al eliminar"}, response.status_code)

        # 2. Crear carpeta
        elif action == "create_folder":
            match = re.search(r'crear\s*carpeta\s*[:\s]*(.+)', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Debe especificar el nombre de la carpeta (ej: 'crear carpeta: Nueva')"}), 400
            folder_name = match.group(1).strip()

            response = requests.post(
                "https://graph.microsoft.com/v1.0/me/drive/root/children",
                headers=headers,
                json={
                    "name": folder_name,
                    "folder": {},
                    "@microsoft.graph.conflictBehavior": "rename"  # Evita conflictos renombrando
                }
            )
            return jsonify({"success": "Carpeta creada"}) if response.status_code == 201 else jsonify({"error": "Error al crear carpeta"}, response.status_code)

        # 3. Mover archivo
        elif action == "move":
            if not file_id:
                match = re.search(r'archivo\s*[:\s]*(.+?)\s*a\s*carpeta\s*[:\s]*(.+)', user_text, re.IGNORECASE)
                if not match:
                    return jsonify({"error": "Formato inválido. Ejemplo: 'mover archivo: doc.txt a carpeta: Nueva'"}), 400
                file_name = match.group(1).strip()
                dest_folder_name = match.group(2).strip()
                file_id = get_file_id_by_name(file_name)
                if not file_id:
                    return jsonify({"error": f"No se encontró el archivo '{file_name}'"}), 404
            else:
                dest_folder_name = data.get("dest_folder", "")
                if not dest_folder_name:
                    return jsonify({"error": "Debe especificar la carpeta de destino en dest_folder o en el texto"}), 400

            dest_folder_id = get_file_id_by_name(dest_folder_name, is_folder=True)
            if not dest_folder_id:
                return jsonify({"error": f"No se encontró la carpeta '{dest_folder_name}'"}), 404

            response = requests.patch(
                f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}",
                headers=headers,
                json={"parentReference": {"id": dest_folder_id}}
            )
            return jsonify({"success": "Archivo movido"}) if response.status_code == 200 else jsonify({"error": "Error al mover archivo"}, response.status_code)

        # 4. Restaurar archivo
        elif action == "restore":
            if not file_id:
                match = re.search(r'restaurar\s*archivo\s*[:\s]*(.+)', user_text, re.IGNORECASE)
                if not match:
                    return jsonify({"error": "Debe especificar el nombre del archivo (ej: 'restaurar archivo: doc.txt')"}), 400
                file_name = match.group(1).strip()
                # Buscar en la papelera (requiere acceso a elementos eliminados)
                url = "https://graph.microsoft.com/v1.0/me/drive/special/recyclebin/children"
                response = requests.get(url, headers=headers)
                if response.status_code == 200:
                    items = response.json().get("value", [])
                    for item in items:
                        if item["name"].lower() == file_name.lower() and "folder" not in item:
                            file_id = item["id"]
                            break
                if not file_id:
                    return jsonify({"error": f"No se encontró el archivo '{file_name}' en la papelera"}), 404

            # Restaurar desde la papelera moviéndolo de vuelta a la raíz (o carpeta original si se conoce)
            response = requests.patch(
                f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}",
                headers=headers,
                json={"parentReference": {"id": "root"}}
            )
            return jsonify({"success": "Archivo restaurado"}) if response.status_code == 200 else jsonify({"error": "Error al restaurar archivo"}, response.status_code)

        # Acción no reconocida
        return jsonify({"error": "Acción no reconocida o no implementada"}), 400

    @app.route("/accion-teams", methods=["POST"])
    def ejecutar_accion_teams():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        message_id = data.get("message_id")
        channel_id = data.get("channel_id")

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("Teams", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        action = interpretar_accion_mensajeria(user_text)
        headers = get_teams_headers(token)

        if "reply" in action:
            reply_text = data.get("reply_text", "")
            response = requests.post(f"https://graph.microsoft.com/v1.0/teams/{channel_id}/messages/{message_id}/replies",
                                    headers=headers, json={"body": {"content": reply_text}})
            return jsonify({"success": "Mensaje respondido"}) if response.status_code == 201 else jsonify({"error": "Error al responder"}), response.status_code

        return jsonify({"error": "Acción no reconocida"}), 400
