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
<<<<<<< HEAD
from flask_caching import Cache
from app.utils.utils import get_user_from_db
def setup_routes_secretary_posts(app, mongo, cache):
    functions = setup_routes_secretary_gets(app, mongo, cache)
=======
def setup_routes_secretary_posts(app, mongo):
    functions = setup_routes_secretary_gets(app, mongo)
>>>>>>> 2ee3a3c5e48cf23453f0aefb56306d34c907b646
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
        prompt = f"El usuario dijo: '{texto}'. Determina si quiere 'eliminar' o 'delete' (eliminar), 'spam' (mover a spam), 'schedule' (agendar cita), 'draft' (crear borrador) o 'send' (enviar correo). Si no está claro, responde 'unknown'."
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
        message_id = data.get("message_id")

        if not email or not user_text or not message_id:
            return jsonify({"error": "Oye, necesito tu email, qué hacer y el ID del correo, ¿me los das?"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "No te encontré en el sistema, ¿seguro que estás registrado?"}), 404

        token = user.get("integrations", {}).get("Gmail", {}).get("token")
        if not token:
            return jsonify({"error": "No tengo acceso a tu Gmail, ¿revisamos la conexión?"}), 400

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        action = interpretar_accion_email(user_text)
        print(action)

        if action == "delete" or "eliminar":
            response = requests.post(f"https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}/trash", headers=headers)
            return jsonify({"success": "¡Listo! El correo está en la papelera."}) if response.status_code == 204 else jsonify({"success": "¡Listo! El correo está en la papelera."})

        elif action == "spam":
            response = requests.post(
                f"https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}/modify",
                headers=headers,
                json={"addLabelIds": ["SPAM"], "removeLabelIds": ["INBOX"]}
            )
            return jsonify({"success": "¡Hecho! Ese correo ya está en spam."}) if response.status_code == 200 else jsonify({"error": "No pude moverlo a spam, ¿probamos otra vez?"}), response.status_code

        return jsonify({"error": "No entendí, ¿quieres 'eliminar', 'responde' o 'spam'?"}), 400

    @app.route("/accion-outlook", methods=["POST"])
    def ejecutar_accion_outlook():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        message_id = data.get("message_id")

        if not email or not user_text or not message_id:
            return jsonify({"error": "Oye, necesito tu email, qué hacer y el ID del correo, ¿me los das?"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "No te encontré, ¿estás registrado?"}), 404

        token = user.get("integrations", {}).get("Outlook", {}).get("token")
        if not token:
            return jsonify({"error": "No tengo acceso a tu Outlook, ¿revisamos la conexión?"}), 400

        headers = get_outlook_headers(token)
        action = interpretar_accion_email(user_text)

        if action == "delete":
            response = requests.delete(f"https://graph.microsoft.com/v1.0/me/messages/{message_id}", headers=headers)
            return jsonify({"success": "¡Listo! El correo está eliminado."}) if response.status_code == 204 else jsonify({"success": "¡Hecho! Correo eliminado."})

        elif action == "spam":
            response = requests.post(
                f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/move",
                headers=headers,
                json={"destinationId": "JunkEmail"}
            )
            return jsonify({"success": "¡Hecho! El correo está en spam."}) if response.status_code == 201 else jsonify({"success": "¡Listo! Correo movido a spam (Outlook confirma raro)."})

        return jsonify({"error": "No entendí, ¿quieres 'elimina', 'responde' o 'spam'?"}), 400
    
    @app.route("/accion-notion", methods=["POST"])
    def ejecutar_accion_notion():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        page_id = data.get("message_id")

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("Notion", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        action = interpretar_accion_productividad(user_text)
        headers = get_notion_headers(token)

        if "mark_done" in action:
            # Actualizar la propiedad "Estado" (tipo status) a "Listo"
            payload = {
                "properties": {
                    "Estado": {  # Cambiado de "status" a "Estado"
                        "status": {  # Cambiado de "select" a "status"
                            "name": "Listo"  # Valor válido según tu captura
                        }
                    }
                }
            }
            response = requests.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=headers, json=payload)
            print("Notion PATCH response (mark_done):", response.status_code, response.text)

            if response.status_code == 200:
                return jsonify({"success": "Página marcada como completada"})
            else:
                error_detail = response.json().get("message", response.text)
                return jsonify({"error": "Error al actualizar estado", "details": error_detail}), response.status_code

        elif "delete" in action:
            response = requests.patch(f"https://api.notion.com/v1/pages/{page_id}",
                                    headers=headers, json={"archived": True})  # No puedes eliminar, solo archivar
            return jsonify({"success": "Página archivada"}) if response.status_code == 200 else jsonify({"error": "Error al archivar"}), response.status_code


        return jsonify({"error": "Acción no reconocida"}), 400

    @app.route("/accion-drive", methods=["POST"])
    def ejecutar_accion_drive():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        file_id = data.get("file_id")

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("Drive", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        action = interpretar_accion_archivos(user_text)
        headers = get_google_drive_headers(token)

        if "delete" in action:
            response = requests.delete(f"https://www.googleapis.com/drive/v3/files/{file_id}", headers=headers)
            return jsonify({"success": "Archivo eliminado"}) if response.status_code == 204 else jsonify({"error": "Error al eliminar archivo"}), response.status_code

        elif "rename" in action:
            new_name = data.get("new_name", "")
            response = requests.patch(f"https://www.googleapis.com/drive/v3/files/{file_id}",
                                    headers=headers, json={"name": new_name})
            return jsonify({"success": "Archivo renombrado"}) if response.status_code == 200 else jsonify({"error": "Error al renombrar archivo"}), response.status_code

        return jsonify({"error": "Acción no reconocida"}), 400

    @app.route("/accion-slack", methods=["POST"])
    def ejecutar_accion_slack():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        message_ts = data.get("message_id")
        channel = data.get("channel")

        if not email or not user_text or not channel:
            return jsonify({"error": "Me faltan datos: email, qué hacer y el canal, ¿me los das?"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "No te encontré, ¿estás registrado?"}), 404

        token = user.get("integrations", {}).get("Slack", {}).get("token")
        if not token:
            return jsonify({"error": "No tengo acceso a tu Slack, ¿revisamos?"}), 400

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        action = interpretar_accion_mensajeria(user_text)

        if action == "reply":
            if not message_ts:
                return jsonify({"error": "Necesito el ID del mensaje para responder, ¿me lo pasas?"}), 400
            reply_text = data.get("reply_text", "")
            if not reply_text:
                match = re.search(r'responde(?: con)?:\s*(.+)', user_text, re.IGNORECASE)
                if not match:
                    return jsonify({"error": "Dime qué responder (ej: 'responde: Hola')"}), 400
                reply_text = match.group(1).strip()

            response = requests.post(
                "https://slack.com/api/chat.postMessage",
                headers=headers,
                json={"channel": channel, "thread_ts": message_ts, "text": reply_text}
            )
            return jsonify({"success": f"¡Enviado! Respondí con: '{reply_text}'."}) if response.status_code == 200 and response.json().get("ok") else jsonify({"error": "No pude responder, ¿lo intentamos otra vez?"}), response.status_code

        elif action == "react":
            if not message_ts:
                return jsonify({"error": "Dime qué mensaje reaccionar con el ID, por favor."}), 400
            match = re.search(r'reacciona(?: con)?:?\s*:?(\w+):?', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Dime qué emoji usar (ej: 'reacciona: smile')"}), 400
            emoji = match.group(1).strip()

            response = requests.post(
                "https://slack.com/api/reactions.add",
                headers=headers,
                json={"channel": channel, "timestamp": message_ts, "name": emoji}
            )
            return jsonify({"success": f"¡Listo! Puse un '{emoji}' al mensaje."}) if response.status_code == 200 and response.json().get("ok") else jsonify({"error": "No pude reaccionar, ¿probamos de nuevo?"}), response.status_code

        elif action == "mention":
            match = re.search(r'menciona(?: a)?:\s*(.+)', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Dime a quién mencionar (ej: 'menciona: @juan')"}), 400
            mention_target = match.group(1).strip()
            if not mention_target.startswith('@'):
                mention_target = f"@{mention_target}"

            response = requests.post(
                "https://slack.com/api/chat.postMessage",
                headers=headers,
                json={"channel": channel, "text": f"Hola {mention_target}"}
            )
            return jsonify({"success": f"¡Hecho! Mencioné a {mention_target}."}) if response.status_code == 200 and response.json().get("ok") else jsonify({"error": "No pude mencionarlo, ¿lo intentamos otra vez?"}), response.status_code

        return jsonify({"error": "No entendí, ¿quieres 'responde', 'reacciona' o 'menciona'?"}), 400

    @app.route("/accion-drive", methods=["POST"])
    def ejecutar_accion_drive():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        file_id = data.get("file_id")

        if not email or not user_text or not file_id:
            return jsonify({"error": "Me faltan datos: tu email, qué hacer y el ID del archivo, ¿me los das?"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "No te encontré, ¿estás registrado?"}), 404

        token = user.get("integrations", {}).get("Drive", {}).get("token")
        if not token:
            return jsonify({"error": "No tengo acceso a tu Drive, ¿revisamos?"}), 400

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        action = interpretar_accion_archivos(user_text)

        if action == "delete":
            response = requests.patch(
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                headers=headers,
                json={"trashed": True}
            )
            return jsonify({"success": "¡Listo! El archivo está en la papelera."}) if response.status_code == 200 else jsonify({"error": "No pude eliminarlo, ¿lo intentamos otra vez?"}), response.status_code

        elif action == "move":
            match = re.search(r'mueve(?: a)?:\s*(.+)', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Dime a qué carpeta moverlo (ej: 'mueve: Trabajo')"}), 400
            folder_name = match.group(1).strip()
            folder_id = get_file_id_by_name(folder_name, is_folder=True, headers=headers)
            if not folder_id:
                return jsonify({"error": f"No encontré la carpeta '{folder_name}'"}), 404

            response = requests.patch(
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                headers=headers,
                json={"addParents": folder_id}
            )
            return jsonify({"success": f"¡Hecho! Moví el archivo a '{folder_name}'."}) if response.status_code == 200 else jsonify({"error": "No pude moverlo, ¿probamos de nuevo?"}), response.status_code

        elif action == "rename":
            new_name = data.get("new_name", "")
            if not new_name:
                match = re.search(r'renombra(?: a)?:\s*(.+)', user_text, re.IGNORECASE)
                if not match:
                    return jsonify({"error": "Dime el nuevo nombre (ej: 'renombra: Nuevo archivo')"}), 400
                new_name = match.group(1).strip()

            response = requests.patch(
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                headers=headers,
                json={"name": new_name}
            )
            return jsonify({"success": f"¡Listo! Ahora se llama '{new_name}'."}) if response.status_code == 200 else jsonify({"error": "No pude renombrarlo, ¿lo intentamos otra vez?"}), response.status_code

        return jsonify({"error": "No entendí, ¿quieres 'elimina', 'mueve' o 'renombra'?"}), 400

    def get_file_id_by_name(name, is_folder=False, headers=None):
        url = "https://www.googleapis.com/drive/v3/files"
        mime_type = "application/vnd.google-apps.folder" if is_folder else None
        params = {"q": f"name contains '{name}' trashed=false", "fields": "files(id)"}
        if mime_type:
            params["q"] += f" mimeType='{mime_type}'"
        response = requests.get(url, headers=headers, params=params)
        files = response.json().get("files", [])
        return files[0]["id"] if files else None

    @app.route("/accion-asana", methods=["POST"])
    def ejecutar_accion_asana():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        task_id = data.get("message_id")

        if not email or not user_text:
            return jsonify({"error": "Me faltan datos: tu email y qué hacer, ¿me los das?"}), 400
        if not task_id:
            print("No se proporcionó task_id, intentando buscar por nombre...")

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "No te encontré, ¿estás registrado?"}), 404

        token = user.get("integrations", {}).get("Asana", {}).get("token")
        if not token:
            return jsonify({"error": "No tengo acceso a tu Asana, ¿revisamos?"}), 400

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        action = interpretar_accion_productividad(user_text)
        print(f"Acción interpretada: {action} (tipo: {type(action)}, valor: '{action}')")

        # Obtener el task_id (directamente o por nombre)
        if not task_id:
            match = re.search(r'marca como completada la tarea (.+)|asigna(?: a)?:\s*(.+)|elimina la tarea (.+)', user_text, re.IGNORECASE)
            if match:
                task_name = next((g for g in match.groups() if g), None)
                if task_name:
                    task_id = get_task_id_asana(task_name, token)
                    if not task_id:
                        return jsonify({"error": f"No se encontró la tarea '{task_name}' en Asana"}), 404
                    print(f"Tarea '{task_name}' encontrada, task_id: {task_id}")
                else:
                    return jsonify({"error": "No se encontró una tarea válida en la consulta"}), 400
            else:
                return jsonify({"error": "No entendí, ¿quieres 'marca como hecha', 'elimina' o 'asigna' con un nombre de tarea?"}), 400
        else:
            # Validar la existencia de la tarea y obtener su nombre
            try:
                task_response = requests.get(f"https://app.asana.com/api/1.0/tasks/{task_id}", headers=headers, timeout=10)
                print("Task GET response:", task_response.status_code, task_response.text)
                if task_response.status_code != 200:
                    return jsonify({"error": "No encontré la tarea, ¿revisamos el ID?", "details": task_response.text}), task_response.status_code
            except requests.exceptions.RequestException as e:
                print(f"Error en Task GET: {str(e)}")
                return jsonify({"error": "Error al validar la tarea", "details": str(e)}), 500

            task_data = task_response.json().get("data", {})
            task_name = task_data.get("name", "la tarea")

        # Ejecutar la acción correspondiente
        if "mark_done" in action:
            try:
                payload = {"data": {"completed": True}}
                print(f"Intentando marcar como completado con payload: {payload}")
                response = requests.put(
                    f"https://app.asana.com/api/1.0/tasks/{task_id}",
                    headers=headers,
                    json=payload,
                    timeout=10
                )
                if response.status_code == 200:
                    return jsonify({"success": f"¡Listo! La tarea '{task_name}' está marcada como hecha."})
                else:
                    return jsonify({"error": "No pude marcarla, ¿lo intentamos otra vez?", "details": response.text}), response.status_code
            except requests.exceptions.RequestException as e:
                print(f"Error en mark_done PUT: {str(e)}")
                return jsonify({"error": "Error al marcar la tarea", "details": str(e)}), 500
            except Exception as e:
                print(f"Error inesperado en mark_done: {str(e)}")
                return jsonify({"error": "Error inesperado al marcar la tarea", "details": str(e)}), 500

        elif "delete" in action:
            try:
                response = requests.delete(
                    f"https://app.asana.com/api/1.0/tasks/{task_id}",
                    headers=headers,
                    timeout=10
                )
                print("Delete response:", response.status_code, response.text)
                if response.status_code == 204:
                    return jsonify({"success": f"¡Hecho! La tarea '{task_name}' está eliminada."})
                else:
                    return jsonify({"error": "No pude eliminarla, ¿probamos de nuevo?", "details": response.text}), response.status_code
            except requests.exceptions.RequestException as e:
                print(f"Error en delete: {str(e)}")
                return jsonify({"error": "Error al eliminar la tarea", "details": str(e)}), 500

        elif action == "assign":
            match = re.search(r'asigna(?: a)?:\s*(.+)', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Dime a quién asignarla (ej: 'asigna: juan@example.com')"}), 400
            assignee_email = match.group(1).strip()

            try:
                workspaces_response = requests.get("https://app.asana.com/api/1.0/workspaces", headers=headers, timeout=10)
                print("Workspaces response:", workspaces_response.status_code, workspaces_response.text)
                if workspaces_response.status_code != 200:
                    return jsonify({"error": "No se pudo obtener el workspace", "details": workspaces_response.text}), workspaces_response.status_code
            except requests.exceptions.RequestException as e:
                print(f"Error en Workspaces GET: {str(e)}")
                return jsonify({"error": "Error al obtener el workspace", "details": str(e)}), 500

            workspace_id = workspaces_response.json().get("data", [])[0]["gid"]

            try:
                users_response = requests.get(
                    f"https://app.asana.com/api/1.0/users?workspace={workspace_id}&opt_fields=email,gid",
                    headers=headers,
                    timeout=10
                )
                print("Users response:", users_response.status_code, users_response.text)
                if users_response.status_code != 200:
                    return jsonify({"error": "No se pudo buscar el usuario", "details": users_response.text}), users_response.status_code
            except requests.exceptions.RequestException as e:
                print(f"Error en Users GET: {str(e)}")
                return jsonify({"error": "Error al buscar el usuario", "details": str(e)}), 500

            users = users_response.json().get("data", [])
            assignee = next((user for user in users if user["email"] == assignee_email), None)
            if not assignee:
                return jsonify({"error": f"No encontré al usuario '{assignee_email}' en Asana"}), 404

            assignee_gid = assignee["gid"]

            try:
                response = requests.put(
                    f"https://app.asana.com/api/1.0/tasks/{task_id}",
                    headers=headers,
                    json={"data": {"assignee": assignee_gid}},
                    timeout=10
                )
                print("Assign PUT response:", response.status_code, response.text)
                if response.status_code == 200:
                    updated_user = mongo.database.usuarios.find_one({"correo": email})
                    if updated_user:
                        cache.set(email, updated_user, timeout=1800)
                        print(f"Cache updated for user {email} after assigning task")
                    return jsonify({"success": f"¡Listo! Asigné la tarea '{task_name}' a '{assignee_email}'."})
                else:
                    return jsonify({"error": "No pude asignarla, ¿lo intentamos otra vez?", "details": response.text}), response.status_code
            except requests.exceptions.RequestException as e:
                print(f"Error en assign PUT: {str(e)}")
                return jsonify({"error": "Error al asignar la tarea", "details": str(e)}), 500
            except Exception as e:
                print(f"Error inesperado en assign: {str(e)}")
                return jsonify({"error": "Error inesperado al asignar la tarea", "details": str(e)}), 500

        return jsonify({"error": "No entendí, ¿quieres 'marca como hecha', 'elimina' o 'asigna' con un nombre o ID de tarea?"}), 400

    def get_task_id_asana(task_name, asana_token):
        """Obtiene el task_id de una tarea por su nombre en Asana."""
        try:
            headers = {"Authorization": f"Bearer {asana_token}"}
            workspaces_response = requests.get("https://app.asana.com/api/1.0/workspaces", headers=headers, timeout=10)
            print(f"Workspaces GET response: {workspaces_response.status_code} {workspaces_response.text}")
            if workspaces_response.status_code != 200:
                return None

            workspace_id = workspaces_response.json().get("data", [])[0]["gid"]
            tasks_response = requests.get(
                f"https://app.asana.com/api/1.0/tasks?workspace={workspace_id}&opt_fields=gid,name",
                headers=headers,
                timeout=10
            )
            print(f"Tasks GET response: {tasks_response.status_code} {tasks_response.text}")
            if tasks_response.status_code != 200:
                return None

            tasks = tasks_response.json().get("data", [])
            for task in tasks:
                if task.get("name", "").lower() == task_name.lower():
                    return task["gid"]
            return None
        except requests.exceptions.RequestException as e:
            print(f"Error al buscar task_id: {str(e)}")
            return None
    
    @app.route("/accion-clickup", methods=["POST"])
    def ejecutar_accion_clickup():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        task_id = data.get("message_id")

        if not email or not user_text:
            return jsonify({"error": "Me faltan datos: tu email y qué hacer, ¿me los das?"}), 400
        if not task_id:
            print("No se proporcionó task_id, intentando buscar por nombre...")

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "No te encontré, ¿estás registrado?"}), 404

        token = user.get("integrations", {}).get("ClickUp", {}).get("token")
        if not token:
            return jsonify({"error": "No tengo acceso a tu ClickUp, ¿revisamos?"}), 400

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        print(f"Procesando acción para email: {email}, user_text: '{user_text}', task_id: {task_id}")
        action = interpretar_accion_productividad(user_text)
        # Obtener el task_id (directamente o por nombre)
        if not task_id:
            match = re.search(r'(marca como completada|cambia el estado a|elimina) la tarea (.+)', user_text, re.IGNORECASE)
            if match:
                action = match.group(1).lower()
                task_name = match.group(2)
                print(f"Acción detectada: {action}, nombre de tarea: {task_name}")
                task_id = get_task_id_clickup(task_name, token)
                if not task_id:
                    return jsonify({"error": f"No se encontró la tarea '{task_name}' en ClickUp"}), 404
                print(f"Tarea '{task_name}' encontrada, task_id: {task_id}")
            else:
                return jsonify({"error": "No se encontró una tarea válida en la consulta"}), 400
        else:
            # Validar la existencia de la tarea
            try:
                task_response = requests.get(f"https://api.clickup.com/api/v2/task/{task_id}", headers=headers, timeout=10)
                print("Task GET response:", task_response.status_code, task_response.text)
                if task_response.status_code != 200:
                    return jsonify({"error": "No encontré la tarea, ¿revisamos el ID?", "details": task_response.text}), task_response.status_code
            except requests.exceptions.RequestException as e:
                print(f"Error en Task GET: {str(e)}")
                return jsonify({"error": "Error al obtener la tarea", "details": str(e)}), 500

            task_data = task_response.json()
            task_name = task_data.get("name", "la tarea")
            print(f"Nombre de la tarea: {task_name}")

        # Acción según la consulta
        if "completa" or "completada" in action or "mark_done" in user_text.lower():  # Compatible con la lógica de post_to_clickup
            try:
                # Obtener los estados disponibles de la lista
                list_id = task_data.get("list", {}).get("id")
                if not list_id:
                    return jsonify({"error": "No se encontró el ID de la lista de la tarea"}), 400
                print(f"ID de la lista: {list_id}")

                list_response = requests.get(f"https://api.clickup.com/api/v2/list/{list_id}", headers=headers, timeout=10)
                print("List GET response:", list_response.status_code, list_response.text)
                if list_response.status_code != 200:
                    return jsonify({"error": "No pude obtener los estados de la lista", "details": list_response.text}), list_response.status_code

                list_data = list_response.json()
                print(list_data)
                statuses = [status["status"] for status in list_data.get("statuses", [])]
                print(f"Estados disponibles: {statuses}")

                # Buscar un estado que indique "completado"
                completed_status = next(
                    (s for s in statuses if any(keyword in s.lower() for keyword in ["complete", "done", "listo", "completado", "closed"])),
                    None
                )
                if not completed_status:
                    return jsonify({"error": f"No encontré un estado de completado. Opciones: {', '.join(statuses)}"}), 400
                print(f"Estado de completado encontrado: {completed_status}")

                # Actualizar el estado de la tarea
                data = {"status": completed_status}
                response = requests.put(f"https://api.clickup.com/api/v2/task/{task_id}", headers=headers, json=data, timeout=10)
                print("Mark done PUT response:", response.status_code, response.text)
                if response.status_code == 200:
                    # Actualizar la caché después de modificar la tarea
                    updated_user = mongo.database.usuarios.find_one({"correo": email})
                    if updated_user:
                        cache.set(email, updated_user, timeout=1800)
                        print(f"Cache updated for user {email} after marking task as done")
                    return jsonify({"success": f"¡Listo! La tarea '{task_name}' está marcada como completada ({completed_status})."})
                else:
                    return jsonify({"error": "No se pudo completar la tarea", "details": response.text}), response.status_code

            except requests.exceptions.RequestException as e:
                print(f"Error en mark_done: {str(e)}")
                return jsonify({"error": "Error al intentar marcar la tarea como completada", "details": str(e)}), 500
            except Exception as e:
                print(f"Error inesperado en mark_done: {str(e)}")
                return jsonify({"error": "Error inesperado al marcar la tarea", "details": str(e)}), 500

        elif "cambia el estado" in action:
            try:
                # Extraer el nuevo estado del query
                new_status_match = re.search(r'cambia el estado a (.+)', user_text, re.IGNORECASE)
                if not new_status_match:
                    return jsonify({"error": "No se proporcionó un nuevo estado"}), 400
                new_status = new_status_match.group(1).strip()
                print(f"Nuevo estado solicitado: {new_status}")

                # Obtener los estados disponibles de la lista
                list_id = task_data.get("list", {}).get("id")
                if not list_id:
                    return jsonify({"error": "No se encontró el ID de la lista de la tarea"}), 400

                list_response = requests.get(f"https://api.clickup.com/api/v2/list/{list_id}", headers=headers, timeout=10)
                print("List GET response:", list_response.status_code, list_response.text)
                if list_response.status_code != 200:
                    return jsonify({"error": "No pude obtener los estados de la lista", "details": list_response.text}), list_response.status_code

                list_data = list_response.json()
                statuses = [status["status"] for status in list_data.get("statuses", [])]
                valid_status = next((s for s in statuses if s.lower() == new_status.lower()), None)
                if not valid_status:
                    return jsonify({"error": f"Ese estado no existe. Opciones: {', '.join(statuses)}"}), 400

                # Actualizar el estado de la tarea
                data = {"status": valid_status}
                response = requests.put(f"https://api.clickup.com/api/v2/task/{task_id}", headers=headers, json=data, timeout=10)
                print("Change status PUT response:", response.status_code, response.text)
                if response.status_code == 200:
                    updated_user = mongo.database.usuarios.find_one({"correo": email})
                    if updated_user:
                        cache.set(email, updated_user, timeout=1800)
                        print(f"Cache updated for user {email} after changing task status")
                    return jsonify({"success": f"Estado de la tarea '{task_name}' cambiado a '{valid_status}'."})
                else:
                    return jsonify({"error": "No se pudo cambiar el estado de la tarea", "details": response.text}), response.status_code

            except requests.exceptions.RequestException as e:
                print(f"Error en change_status: {str(e)}")
                return jsonify({"error": "Error al intentar cambiar el estado de la tarea", "details": str(e)}), 500

        elif "elimina" in action:
            try:
                # Archivar la tarea (usar PUT en lugar de DELETE, como en tu versión anterior)
                data = {"archived": True}
                response = requests.put(f"https://api.clickup.com/api/v2/task/{task_id}", headers=headers, json=data, timeout=10)
                print("Delete PUT response:", response.status_code, response.text)
                if response.status_code == 200:
                    updated_user = mongo.database.usuarios.find_one({"correo": email})
                    if updated_user:
                        cache.set(email, updated_user, timeout=1800)
                        print(f"Cache updated for user {email} after deleting task")
                    return jsonify({"success": f"¡Hecho! La tarea '{task_name}' está archivada."})
                else:
                    return jsonify({"error": "No se pudo archivar la tarea", "details": response.text}), response.status_code
            except requests.exceptions.RequestException as e:
                print(f"Error en delete: {str(e)}")
                return jsonify({"error": "Error al intentar archivar la tarea", "details": str(e)}), 500

        return jsonify({"error": "No entendí, ¿quieres 'marca como completada', 'cambia el estado a' o 'elimina' la tarea?"}), 400

    def get_task_id_clickup(task_name, clickup_token):
        """Obtiene el task_id de una tarea por su nombre en ClickUp."""
        try:
            headers = {"Authorization": f"Bearer {clickup_token}"}
            # Obtener el team_id del usuario (necesario para buscar tareas)
            teams_response = requests.get("https://api.clickup.com/api/v2/team", headers=headers, timeout=10)
            print(f"Teams GET response: {teams_response.status_code} {teams_response.text}")
            if teams_response.status_code != 200:
                return None

            team_id = teams_response.json().get("teams", [])[0].get("id")
            if not team_id:
                print("No se encontró team_id")
                return None

            # Buscar tareas por nombre en el equipo
            tasks_response = requests.get(
                f"https://api.clickup.com/api/v2/team/{team_id}/task",
                headers=headers,
                params={"include_closed": False, "search": task_name},
                timeout=10
            )
            print(f"Tasks GET response: {tasks_response.status_code} {tasks_response.text}")
            if tasks_response.status_code != 200:
                return None

            tasks = tasks_response.json().get("tasks", [])
            for task in tasks:
                if task.get("name", "").lower() == task_name.lower():
                    return task["id"]
            return None
        except requests.exceptions.RequestException as e:
            print(f"Error al buscar task_id: {str(e)}")
            return None

    @app.route("/accion-hubspot", methods=["POST"])
    def ejecutar_accion_hubspot():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        deal_id = data.get("deal_id")

        if not email or not user_text or not deal_id:
            return jsonify({"error": "Me faltan datos: tu email, qué hacer y el ID del negocio, ¿me los das?"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "No te encontré, ¿estás registrado?"}), 404

        token = user.get("integrations", {}).get("HubSpot", {}).get("token")
        if not token:
            return jsonify({"error": "No tengo acceso a tu HubSpot, ¿revisamos?"}), 400

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        action = interpretar_accion_hubspot(user_text)

        if action in ["close", "cierra"]:
            response = requests.patch(
                f"https://api.hubapi.com/crm/v3/objects/deals/{deal_id}",
                headers=headers,
                json={"properties": {"dealstage": "closedwon"}}
            )
            return jsonify({"success": "¡Listo! El negocio está cerrado."}) if response.status_code == 200 else jsonify({"error": "No pude cerrarlo, ¿lo intentamos otra vez?"}), response.status_code

        elif action in ["follow", "sigue"]:
            response = requests.post(
                "https://api.hubapi.com/crm/v3/objects/notes",
                headers=headers,
                json={
                    "properties": {"hs_note_body": "Seguimiento pendiente", "hs_object_id": deal_id},
                    "associations": [{"to": {"id": deal_id}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 20}]}]
                }
            )
            return jsonify({"success": "¡Hecho! Añadí un seguimiento al negocio."}) if response.status_code == 201 else jsonify({"error": "No pude seguirlo, ¿probamos de nuevo?"}), response.status_code

        elif action == "update":
            match = re.search(r'actualiza(?: a)?:\s*(.+)', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Dime el nuevo estado (ej: 'actualiza: En Progreso')"}), 400
            new_stage = match.group(1).strip()

            response = requests.patch(
                f"https://api.hubapi.com/crm/v3/objects/deals/{deal_id}",
                headers=headers,
                json={"properties": {"dealstage": new_stage}}
            )
            return jsonify({"success": f"¡Listo! Actualicé el negocio a '{new_stage}'."}) if response.status_code == 200 else jsonify({"error": "No pude actualizarlo, ¿lo intentamos otra vez?"}), response.status_code

        return jsonify({"error": "No entendí, ¿quieres 'cierra', 'sigue' o 'actualiza'?"}), 400

    @app.route("/accion-dropbox", methods=["POST"])
    def ejecutar_accion_dropbox():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        file_path = data.get("file_path")

        if not email or not user_text:
            return jsonify({"error": "Me faltan datos: tu email y qué hacer, ¿me los das?"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "No te encontré, ¿estás registrado?"}), 404

        token = user.get("integrations", {}).get("Dropbox", {}).get("token")
        if not token:
            return jsonify({"error": "No tengo acceso a tu Dropbox, ¿revisamos?"}), 400

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        action = interpretar_accion_archivos(user_text)
        print(f"Acción interpretada para '{user_text}': {action}")

        # Si no se proporciona file_path, intentamos buscarlo por nombre
        if not file_path:
            print("No se proporcionó file_path, intentando buscar por nombre...")
            match_file = re.search(r'(eliminar\s*archivo|archivo|mover\s*archivo):\s*(.+?)(?:\s*a\s*carpeta:\s*(.+))?', user_text, re.IGNORECASE)
            if not match_file:
                return jsonify({"error": "No entendí el nombre del archivo. Usa algo como 'eliminar archivo: nombre' o 'mover archivo: nombre a carpeta: destino'"}), 400

            file_name = match_file.group(2).strip()
            if file_name == "n/a":
                return jsonify({"error": "¡Ups! No se especificó el nombre del archivo. Por favor, indícalo e inténtalo de nuevo."}), 400

            # Buscar el archivo en Dropbox
            url_search = "https://api.dropboxapi.com/2/files/search_v2"
            params = {
                "query": file_name,
                "options": {
                    "max_results": 10,
                    "file_status": "active"
                }
            }
            try:
                response = requests.post(url_search, headers=headers, json=params, timeout=10)
                print(f"Search response: {response.status_code} {response.text}")
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                print(f"Error al buscar archivo: {str(e)}")
                return jsonify({"error": "Error al buscar el archivo en Dropbox", "details": str(e)}), 500

            results = response.json().get('matches', [])
            if not results:
                return jsonify({"error": f"No encontré el archivo '{file_name}' en Dropbox. Revisa el nombre e intenta de nuevo."}), 404

            if len(results) > 1:
                file_list = [result['metadata']['metadata']['name'] for result in results]
                return jsonify({"error": f"Encontré varios archivos con nombres similares. Por favor, elige uno:\n{', '.join(file_list)}"}), 400

            file_path = results[0]['metadata']['metadata']['path_lower']
            print(f"Archivo encontrado: {file_path}")

        # Acción: Eliminar archivo
        if action == "delete":
            try:
                response = requests.post(
                    "https://api.dropboxapi.com/2/files/delete_v2",
                    headers=headers,
                    json={"path": file_path},
                    timeout=10
                )
                print(f"Delete response: {response.status_code} {response.text}")
                if response.status_code == 200:
                    # Actualizar la caché después de eliminar
                    updated_user = mongo.database.usuarios.find_one({"correo": email})
                    if updated_user:
                        cache.set(email, updated_user, timeout=1800)
                        print(f"Cache updated for user {email} after deleting file")
                    return jsonify({"success": f"¡Listo! El archivo '{file_path.split('/')[-1]}' ha sido eliminado de Dropbox con éxito."})
                else:
                    return jsonify({"error": "No pude eliminar el archivo, ¿lo intentamos otra vez?", "details": response.text}), response.status_code
            except requests.exceptions.RequestException as e:
                print(f"Error al eliminar archivo: {str(e)}")
                return jsonify({"error": "Error al intentar eliminar el archivo", "details": str(e)}), 500

        # Acción: Mover archivo
        elif action == "move":
            match_dest = re.search(r'(?:mover\s*archivo|mueve(?:\s*a)?):\s*.+?\s*(?:a\s*carpeta:|a):\s*(.+)', user_text, re.IGNORECASE)
            if not match_dest:
                return jsonify({"error": "Dime a qué carpeta moverlo (ej: 'mover archivo: nombre a carpeta: destino')"}), 400
            dest_folder = match_dest.group(1).strip()
            if not dest_folder.startswith('/'):
                dest_folder = f"/{dest_folder}"
            print(f"Carpeta de destino: {dest_folder}")

            try:
                response = requests.post(
                    "https://api.dropboxapi.com/2/files/move_v2",
                    headers=headers,
                    json={
                        "from_path": file_path,
                        "to_path": f"{dest_folder}/{file_path.split('/')[-1]}",
                        "autorename": True,
                        "allow_shared_folder": True,
                        "allow_ownership_transfer": False
                    },
                    timeout=10
                )
                print(f"Move response: {response.status_code} {response.text}")
                if response.status_code == 200:
                    # Actualizar la caché después de mover
                    updated_user = mongo.database.usuarios.find_one({"correo": email})
                    if updated_user:
                        cache.set(email, updated_user, timeout=1800)
                        print(f"Cache updated for user {email} after moving file")
                    return jsonify({"success": f"¡Hecho! El archivo '{file_path.split('/')[-1]}' ha sido movido a '{dest_folder}' con éxito."})
                else:
                    return jsonify({"error": "No pude mover el archivo, ¿probamos de nuevo?", "details": response.text}), response.status_code
            except requests.exceptions.RequestException as e:
                print(f"Error al mover archivo: {str(e)}")
                return jsonify({"error": "Error al intentar mover el archivo", "details": str(e)}), 500

        return jsonify({"error": "No entendí, ¿quieres 'eliminar' o 'mover' el archivo?"}), 400

    @app.route("/accion-onedrive", methods=["POST"])
    def ejecutar_accion_onedrive():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        file_id = data.get("file_id")

        if not email or not user_text:
            return jsonify({"error": "Me faltan datos: tu email y qué hacer, ¿me los das?"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "No te encontré, ¿estás registrado?"}), 404

        token = user.get("integrations", {}).get("OneDrive", {}).get("token")
        if not token:
            return jsonify({"error": "No tengo acceso a tu OneDrive, ¿revisamos?"}), 400

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        action = interpretar_accion_archivos(user_text)
        print(f"Acción interpretada para '{user_text}': {action}")

        # Si no se proporciona file_id, intentamos buscarlo por nombre
        if not file_id:
            print("No se proporcionó file_id, intentando buscar por nombre...")
            match_file = re.search(r'(eliminar\s*(archivo)?|mover\s*(archivo)?)[:\s]*([\w\.\-_]+)(?:\s*a\s*(carpeta)?:?\s*(.+))?', user_text, re.IGNORECASE)
            if not match_file:
                return jsonify({"error": "No entendí el nombre del archivo. Usa algo como 'eliminar archivo: nombre' o 'mover archivo: nombre a carpeta: destino'"}), 400

            file_name = match_file.group(4).strip()
            print(f"Nombre del archivo a buscar: {file_name}")

            # Buscar archivo en OneDrive
            search_url = f"https://graph.microsoft.com/v1.0/me/drive/root/search(q='{file_name}')"
            try:
                response = requests.get(search_url, headers=headers, timeout=10)
                print(f"Search response: {response.status_code} {response.text}")
                if response.status_code == 401:
                    return jsonify({"error": "No autorizado. Verifica el token de acceso."}), 401
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                print(f"Error al buscar archivo: {str(e)}")
                return jsonify({"error": "Error al buscar el archivo en OneDrive", "details": str(e)}), 500

            results = response.json().get('value', [])
            if not results:
                return jsonify({"error": f"No encontré el archivo '{file_name}' en OneDrive. Revisa el nombre e intenta de nuevo."}), 404

            for result in results:
                onedrive_file_name = result['name']
                if onedrive_file_name.lower().startswith(file_name.lower()) and "folder" not in result:  # Asegurarnos de que no sea una carpeta
                    file_id = result['id']
                    break

            if not file_id:
                return jsonify({"error": f"No encontré el archivo '{file_name}' en OneDrive. Revisa el nombre e intenta de nuevo."}), 404
            print(f"Archivo encontrado, file_id: {file_id}")

        # Acción: Eliminar archivo
        if action == "delete":
            try:
                response = requests.delete(
                    f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}",
                    headers=headers,
                    timeout=10
                )
                print(f"Delete response: {response.status_code} {response.text}")
                if response.status_code == 204:
                    # Actualizar la caché después de eliminar
                    updated_user = mongo.database.usuarios.find_one({"correo": email})
                    if updated_user:
                        cache.set(email, updated_user, timeout=1800)
                        print(f"Cache updated for user {email} after deleting file")
                    return jsonify({"success": f"¡Listo! El archivo ha sido eliminado de OneDrive con éxito."})
                else:
                    return jsonify({"error": "No pude eliminar el archivo, ¿lo intentamos otra vez?", "details": response.text}), response.status_code
            except requests.exceptions.RequestException as e:
                print(f"Error al eliminar archivo: {str(e)}")
                return jsonify({"error": "Error al intentar eliminar el archivo", "details": str(e)}), 500

        # Acción: Mover archivo
        elif action == "move":
            match_dest = re.search(r'(?:mover\s*(archivo)?|mueve(?:\s*a)?)[:\s]*[\w\.\-_]+\s*(?:a\s*(carpeta)?:?\s*(.+))', user_text, re.IGNORECASE)
            if not match_dest:
                return jsonify({"error": "Dime a qué carpeta moverlo (ej: 'mover archivo: nombre a carpeta: destino')"}), 400
            dest_folder_name = match_dest.group(3).strip()
            print(f"Carpeta de destino: {dest_folder_name}")

            # Buscar el ID de la carpeta de destino
            dest_folder_id = get_file_id_by_name(dest_folder_name, is_folder=True, headers=headers)
            if not dest_folder_id:
                return jsonify({"error": f"No encontré la carpeta '{dest_folder_name}' en OneDrive"}), 404
            print(f"ID de la carpeta de destino: {dest_folder_id}")

            try:
                response = requests.patch(
                    f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}",
                    headers=headers,
                    json={"parentReference": {"id": dest_folder_id}},
                    timeout=10
                )
                print(f"Move response: {response.status_code} {response.text}")
                if response.status_code == 200:
                    # Actualizar la caché después de mover
                    updated_user = mongo.database.usuarios.find_one({"correo": email})
                    if updated_user:
                        cache.set(email, updated_user, timeout=1800)
                        print(f"Cache updated for user {email} after moving file")
                    return jsonify({"success": f"¡Hecho! El archivo ha sido movido a '{dest_folder_name}' con éxito."})
                else:
                    return jsonify({"error": "No pude mover el archivo, ¿probamos de nuevo?", "details": response.text}), response.status_code
            except requests.exceptions.RequestException as e:
                print(f"Error al mover archivo: {str(e)}")
                return jsonify({"error": "Error al intentar mover el archivo", "details": str(e)}), 500

        return jsonify({"error": "No entendí, ¿quieres 'eliminar' o 'mover' el archivo?"}), 400

    def get_file_id_by_name(file_name, is_folder=False, headers=None):
        """Busca el ID de un archivo o carpeta por nombre en OneDrive."""
        try:
            url = f"https://graph.microsoft.com/v1.0/me/drive/root/search(q='{file_name}')"
            response = requests.get(url, headers=headers, timeout=10)
            print(f"Search folder response: {response.status_code} {response.text}")
            if response.status_code == 200:
                items = response.json().get("value", [])
                for item in items:
                    if item["name"].lower() == file_name.lower() and ("folder" in item) == is_folder:
                        return item["id"]
            return None
        except requests.exceptions.RequestException as e:
            print(f"Error al buscar en OneDrive: {str(e)}")
            return None

