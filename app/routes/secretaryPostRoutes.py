from flask import request, jsonify
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import re
import time
import json
import base64
from config import Config
import openai
from email.mime.text import MIMEText
openai.api_key=Config.CHAT_API_KEY
from app.routes.secretaryGetRoutes import setup_routes_secretary_gets
from flask_caching import Cache
from app.utils.utils import get_user_from_db
def setup_routes_secretary_posts(app, mongo, cache, refresh_functions):
    cache = Cache(app)
    functions = setup_routes_secretary_gets(app, mongo, cache, refresh_functions)
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

    get_refresh_tokens_from_db = refresh_functions["get_refresh_tokens_from_db"]
    refresh_tokens_func = refresh_functions["refresh_tokens"]

    def should_refresh_tokens(email):
        """Determina si se deben refrescar los tokens basado en el tiempo desde el último refresco."""
        last_refresh_key = f"last_refresh_{email}"
        last_refresh = cache.get(last_refresh_key)
        current_time = datetime.utcnow()

        if last_refresh is None:
            print(f"[INFO] No hay registro de último refresco para {email}, forzando refresco")
            return True

        last_refresh_time = datetime.fromtimestamp(last_refresh)
        refresh_interval = timedelta(minutes=30)  # Mantengo 30 min como en el original
        time_since_last_refresh = current_time - last_refresh_time

        if time_since_last_refresh >= refresh_interval:
            print(f"[INFO] Han pasado {time_since_last_refresh} desde el último refresco para {email}, refrescando")
            return True
        
        print(f"[INFO] Tokens de {email} aún vigentes, faltan {refresh_interval - time_since_last_refresh} para refrescar")
        return False

    def get_user_with_refreshed_tokens(email):
        """Obtiene el usuario y refresca tokens solo si es necesario, aprovechando la caché optimizada."""
        try:
            # Intentamos obtener el usuario de la caché
            user = cache.get(email)
            if not user:
                print(f"[INFO] Usuario {email} no está en caché, consultando DB")
                user = get_user_from_db(email, cache, mongo)
                if not user:
                    print(f"[ERROR] Usuario {email} no encontrado en DB")
                    return None
                cache.set(email, user, timeout=1800)  # 30 min de caché

            # Verificamos si necesitamos refrescar tokens
            if not should_refresh_tokens(email):
                print(f"[INFO] Tokens de {email} no necesitan refresco, devolviendo usuario cacheado")
                return user

            # Obtenemos los refresh tokens (cacheados o desde DB)
            refresh_tokens_dict = get_refresh_tokens_from_db(email)
            if not refresh_tokens_dict:
                print(f"[INFO] No hay refresh tokens para {email}, marcando tiempo y devolviendo usuario")
                cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
                return user

            # Filtramos los tokens que realmente necesitamos refrescar
            integrations = user.get("integrations", {})
            tokens_to_refresh = {
                service: refresh_tokens_dict[service]
                for service in integrations
                if service in refresh_tokens_dict and integrations[service].get("refresh_token") not in (None, "n/a")
            }

            if not tokens_to_refresh:
                print(f"[INFO] No hay tokens válidos para refrescar para {email}, marcando tiempo")
                cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
                return user

            # Refrescamos los tokens
            print(f"[INFO] Refrescando tokens para {email}: {list(tokens_to_refresh.keys())}")
            refreshed_tokens, errors = refresh_tokens_func(tokens_to_refresh, email)

            if refreshed_tokens:
                # Como save_access_token_to_db invalida la caché, recargamos el usuario
                print(f"[INFO] Tokens refrescados para {email}: {list(refreshed_tokens.keys())}")
                user = get_user_from_db(email, cache, mongo)  # Recarga desde DB o caché actualizada
                if not user:
                    print(f"[ERROR] No se pudo recargar usuario {email} tras refresco")
                    return None
                cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
                return user
            
            if errors:
                print(f"[WARNING] Errores al refrescar tokens para {email}: {errors}")
                # Devolvemos el usuario actual aunque haya errores, para no bloquear el flujo
                cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
                return user

            # Si no hay tokens refrescados ni errores, marcamos el tiempo y devolvemos el usuario
            print(f"[INFO] No se refrescaron tokens para {email}, marcando tiempo")
            cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
            return user

        except Exception as e:
            print(f"[ERROR] Error en get_user_with_refreshed_tokens para {email}: {e}")
            return None
        
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

        user = get_user_with_refreshed_tokens(email)
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

        user = get_user_with_refreshed_tokens(email)
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

        user = get_user_with_refreshed_tokens(email)
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

    @app.route("/accion-slack", methods=["POST"])
    def ejecutar_accion_slack():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        message_ts = data.get("message_id")
        channel = data.get("channel")

        if not email or not user_text or not channel:
            return jsonify({"error": "Me faltan datos: email, qué hacer y el canal, ¿me los das?"}), 400

        user = get_user_with_refreshed_tokens(email)
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
        message_id = data.get("message_id")  # Es el file_id
        print("user_text:", user_text)
        print("message_id (file_id):", message_id)

        # Validaciones iniciales
        if not email or not user_text:
            return jsonify({"error": "Me faltan datos: tu email y qué hacer, ¿me los das?"}), 400

        user = get_user_with_refreshed_tokens(email)
        if not user:
            return jsonify({"error": "No te encontré, ¿estás registrado?"}), 404

        token = user.get("integrations", {}).get("Drive", {}).get("token")
        print("Token:", token)
        if not token:
            return jsonify({"error": "No tengo acceso a tu Drive, ¿revisamos?"}), 400

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        action = interpretar_accion_archivos(user_text)
        print("action:", action)

        if not action:
            return jsonify({"error": "No entendí, ¿quieres 'eliminar', 'mover', 'crear carpeta' o 'compartir'?"}), 400

        if action in ["delete", "move"] and not message_id:
            return jsonify({"error": "Necesito el ID del archivo para esta acción"}), 400

        # Eliminar archivo
        if "delete" in action:
            metadata_response = requests.get(
                f"https://www.googleapis.com/drive/v3/files/{message_id}",
                headers=headers,
                params={"fields": "name,permissions,ownedByMe,trashed"}
            )
            if metadata_response.status_code != 200:
                print("Metadata error:", metadata_response.text)
                return jsonify({"error": "No pude verificar el archivo", "details": metadata_response.text}), metadata_response.status_code
            
            file_data = metadata_response.json()
            print("File data:", file_data)
            file_name = file_data.get("name", "archivo")
            owned_by_me = file_data.get("ownedByMe", False)
            permissions = file_data.get("permissions", [])
            is_trashed = file_data.get("trashed", False)
            
            if is_trashed:
                return jsonify({"message": f"⚠️ El archivo '{file_name}' ya está en la papelera."})
            
            can_delete = owned_by_me or any(p.get("role") in ["owner", "writer"] for p in permissions)
            if not can_delete:
                return jsonify({"error": f"No tienes permiso para eliminar el archivo '{file_name}'"}), 403

            trash_url = f"https://www.googleapis.com/drive/v3/files/{message_id}"
            trash_data = {"trashed": True}
            response = requests.patch(trash_url, headers=headers, json=trash_data)
            if response.status_code == 200:
                return jsonify({"success": f"🗑️ El archivo '{file_name}' ha sido movido a la papelera de Google Drive con éxito! 🚀"})
            print("Delete error details:", response.text)
            return jsonify({"error": "No pude eliminar el archivo", "details": response.text}), response.status_code

        # Mover archivo (corregido y adaptado de post_to_googledrive)
        if "move" in action:
            match = re.search(r'(?:carpeta\s+(.+))', user_text, re.IGNORECASE)
            print("Match object:", match)
            if not match:
                return jsonify({"error": "Dime a qué carpeta moverlo (ej: 'mueve el archivo a la carpeta Trabajo')"}), 400
            folder_name = match.group(1).strip()
            print("Folder name to move to:", folder_name)

            # Buscar la carpeta en Google Drive
            search_url = "https://www.googleapis.com/drive/v3/files"
            params = {
                "q": f"name contains \"{folder_name}\" and mimeType = \"application/vnd.google-apps.folder\" and trashed=false",
                "fields": "files(id, name)"
            }
            response = requests.get(search_url, headers=headers, params=params)
            print("Search status code:", response.status_code)
            print("Search response:", response.text)
            
            if response.status_code != 200 or not response.json().get('files'):
                return jsonify({"message": f"⚠️ No se encontró una carpeta con el nombre '{folder_name}'. ¿Podrías verificar y especificar el nombre correcto?"})
            
            folders = response.json().get('files', [])
            if len(folders) > 1:
                options = "\n".join([f"{i + 1}. {folder['name']}" for i, folder in enumerate(folders)])
                return jsonify({"message": f"⚠️ Se encontraron varias carpetas con el nombre '{folder_name}'. Por favor, elige una:\n{options}"})
            
            folder_id = folders[0]['id']
            print("Folder ID:", folder_id)

            # Obtener info del archivo antes de mover (para conocer los padres actuales)
            file_info = requests.get(
                f"https://www.googleapis.com/drive/v3/files/{message_id}",
                headers=headers,
                params={"fields": "parents,name"}
            )
            if file_info.status_code != 200:
                return jsonify({"error": "No pude obtener info del archivo", "details": file_info.text}), 500
            
            file_data = file_info.json()
            current_parents = file_data.get("parents", [])
            file_name = file_data.get("name", "archivo")
            print("Current parents (before):", current_parents)
            print("File name:", file_name)

            # Mover el archivo: agregar nuevo padre y eliminar los anteriores
            file_url = f"https://www.googleapis.com/drive/v3/files/{message_id}"
            move_data = {
                "addParents": folder_id,
                "removeParents": ",".join(current_parents) if current_parents else None
            }
            print("Move file data:", move_data)
            
            # Asegurarse de que el Content-Type esté correctamente configurado
            headers_with_content = headers.copy()
            headers_with_content["Content-Type"] = "application/json"
            
            move_response = requests.patch(
                file_url,
                headers=headers_with_content,
                json=move_data,
                params={"fields": "id,name,parents"}
            )
            print("Move status code:", move_response.status_code)
            print("Move response:", move_response.text)

            if move_response.status_code == 200:
                return jsonify({"success": f"🎉 El archivo '{file_name}' ha sido movido a la carpeta '{folder_name}' en Google Drive con éxito! 🚀"})
            return jsonify({"error": "No pude mover el archivo", "details": move_response.text}), move_response.status_code

        # Crear carpeta
        if action == "create_folder":
            match = re.search(r'crear\s*carpeta:\s*(.+)', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Dime el nombre de la carpeta (ej: 'crear carpeta: Nueva')"}), 400
            folder_name = match.group(1).strip()
            response = requests.post(
                "https://www.googleapis.com/drive/v3/files",
                headers=headers,
                json={"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
            )
            if response.status_code == 200:
                return jsonify({"message": f"🎉 ¡La carpeta '{folder_name}' ha sido creada con éxito en Drive! 📂"})
            return jsonify({"error": "No pude crear la carpeta", "details": response.text}), response.status_code

        # Compartir archivo
        if "share" in action:
            if not message_id:
                return jsonify({"error": "Necesito el ID del archivo para compartirlo"}), 400
            match = re.search(r'compartir\s*(?:el\s*)?archivo\s*(?:con)?\s*[:\s]*(.+)', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Dime con quién compartirlo (ej: 'compartir archivo con: user@example.com')"}), 400
            emails = [email.strip() for email in match.group(1).split(",")]
            for email in emails:
                response = requests.post(
                    f"https://www.googleapis.com/drive/v3/files/{message_id}/permissions",
                    headers=headers,
                    json={"type": "user", "role": "writer", "emailAddress": email}
                )
                if response.status_code != 200:
                    return jsonify({"error": f"No pude compartir con '{email}'", "details": response.text}), response.status_code
            return jsonify({"success": f"🎉 ¡Archivo compartido con {', '.join(emails)} con éxito! 🤝"})

        return jsonify({"error": "No entendí, ¿qué acción quieres realizar?"}), 400

    def get_file_id_by_name(name, is_folder=False, headers=None):
        url = "https://www.googleapis.com/drive/v3/files"
        mime_type = "application/vnd.google-apps.folder" if is_folder else None
        params = {"q": f"'me' in owners name contains '{name}' trashed=false", "fields": "files(id)"}
        if mime_type:
            params["q"] += f" mimeType='{mime_type}'"
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            return None
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

        user = get_user_with_refreshed_tokens(email)
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

        user = get_user_with_refreshed_tokens(email)
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

        user = get_user_with_refreshed_tokens(email)
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
        print("Hola papu")
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        file_id = data.get("message_id") 
        print("user_text:", user_text)
        print("file_id:", file_id)

        # Validaciones iniciales
        if not email or not user_text:
            return jsonify({"error": "Me faltan datos: tu email y qué hacer, ¿me los das?"}), 400

        user = get_user_with_refreshed_tokens(email)
        if not user:
            return jsonify({"error": "No te encontré, ¿estás registrado?"}), 404

        token = user.get("integrations", {}).get("Dropbox", {}).get("token")
        if not token:
            return jsonify({"error": "No tengo acceso a tu Dropbox, ¿revisamos?"}), 400

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        action = interpretar_accion_archivos(user_text)
        print(action)
        # Si no se reconoce la acción, devolvemos error
        if not action:
            return jsonify({"error": "No entendí, ¿quieres 'eliminar', 'mover', 'crear carpeta' o 'restaurar'?"}), 400

        # Para acciones que requieren un archivo (delete, move, restore), usamos el ID
        if action in ["delete", "move", "restore"] and not file_id:
            return jsonify({"error": "Necesito el ID del archivo para esta acción"}), 400

        # Obtener la ruta completa del archivo usando el ID
        metadata_response = requests.post(
            "https://api.dropboxapi.com/2/files/get_metadata",
            headers=headers,
            json={"path": file_id}
        )
        if metadata_response.status_code != 200:
            return jsonify({
                "error": "No pude obtener los metadatos del archivo", 
                "details": metadata_response.text
            }), 500
        file_path = metadata_response.json().get("path_display")
        print(file_path)
        
        if not file_path:
            return jsonify({"error": "No encontré la ruta del archivo"}), 404

        # Restaurar archivo
        if "restore" in action:
            # Buscar revisiones del archivo usando el path
            response = requests.post(
                "https://api.dropboxapi.com/2/files/list_revisions",
                headers=headers,
                json={"path": file_path, "limit": 1}
            )
            if response.status_code != 200 or not response.json().get("entries"):
                return jsonify({"message": f"⚠️ No encontré revisiones para el archivo"}), 404
            
            rev = response.json()["entries"][0]["rev"]
            restore_response = requests.post(
                "https://api.dropboxapi.com/2/files/restore",
                headers=headers,
                json={"path": file_path, "rev": rev}
            )
            if restore_response.status_code == 200:
                return jsonify({"message": f"🎉 ¡El archivo ha sido restaurado exitosamente! 🙌"})
            return jsonify({"error": "No pude restaurar el archivo", "details": restore_response.text}), restore_response.status_code

        # Eliminar archivo
        if "delete" in action:
            print("deletetetet")
            response = requests.post(
                "https://api.dropboxapi.com/2/files/delete_v2",
                headers=headers,
                json={"path": file_path}
            )
            if response.status_code == 200:
                return jsonify({"success": f"🎉 El archivo ha sido eliminado con éxito! 🗑️"})
            return jsonify({"error": "No pude eliminar el archivo", "details": response.text}), response.status_code
        
        # Mover archivo
        if "move" in action:
            # Ajustar la regex para capturar el nombre de la carpeta de manera más flexible
            match = re.search(r'(?:mueve|mover)\s*(?:el\s*)?archivo\s*(?:a\s*(?:la\s*)?carpeta)?\s*[:\s]*(.+)', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Dime a qué carpeta moverlo (ej: 'mueve el archivo a la carpeta Trabajo')"}), 400
            folder_name = match.group(1).strip()

            # Buscar la carpeta de destino por nombre
            folder_response = requests.post(
                "https://api.dropboxapi.com/2/files/search_v2",
                headers=headers,
                json={"query": folder_name, "options": {"max_results": 5, "file_status": "active"}}
            )
            if folder_response.status_code != 200:
                return jsonify({"error": "Error al buscar la carpeta", "details": folder_response.text}), 500
            folder_results = folder_response.json().get("matches", [])
            folder_match = next((r for r in folder_results if r['metadata']['metadata']['.tag'] == 'folder' and r['metadata']['metadata']['name'].lower() == folder_name.lower()), None)
            if not folder_match:
                return jsonify({"error": f"No encontré la carpeta '{folder_name}'"}), 404
            folder_path = folder_match['metadata']['metadata']['path_lower']

            # Usar file_path (ruta completa) en lugar de file_id
            file_name = file_path.split('/')[-1]  # Extraer el nombre del archivo de la ruta
            dest_path = f"{folder_path}/{file_name}"

            response = requests.post(
                "https://api.dropboxapi.com/2/files/move_v2",
                headers=headers,
                json={"from_path": file_path, "to_path": dest_path, "autorename": True}
            )
            if response.status_code == 200:
                return jsonify({"success": f"🎉 El archivo '{file_name}' ha sido movido a '{folder_name}' con éxito! 🚀"})
            return jsonify({"error": "No pude mover el archivo", "details": response.text}), response.status_code

        # Crear carpeta
        if action == "create_folder":
            match = re.search(r'crear\s*carpeta:\s*(.+)', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Dime el nombre de la carpeta (ej: 'crear carpeta: Nueva')"}), 400
            folder_name = match.group(1).strip()
            response = requests.post(
                "https://api.dropboxapi.com/2/files/create_folder_v2",
                headers=headers,
                json={"path": f"/{folder_name}", "autorename": False}
            )
            if response.status_code == 200:
                return jsonify({"message": f"🎉 ¡La carpeta '{folder_name}' ha sido creada con éxito en Dropbox! 📂"})
            return jsonify({"error": "No pude crear la carpeta", "details": response.text}), response.status_code

        return jsonify({"error": "No entendí, ¿qué acción quieres realizar?"}), 400

    @app.route("/accion-onedrive", methods=["POST"])
    def ejecutar_accion_onedrive():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        file_id = data.get("file_id")

        # Validaciones iniciales
        if not email or not user_text:
            return jsonify({"error": "Me faltan datos: tu email y qué hacer, ¿me los das?"}), 400

        user = get_user_with_refreshed_tokens(email)
        if not user:
            return jsonify({"error": "No te encontré, ¿estás registrado?"}), 404

        token = user.get("integrations", {}).get("OneDrive", {}).get("token")
        if not token:
            return jsonify({"error": "No tengo acceso a tu OneDrive, ¿revisamos?"}), 400

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        action = interpretar_accion_archivos(user_text)
        print(f"Action detected: {action}")
        print(f"User text: {user_text}")

        # Si no hay file_id y la acción lo requiere, buscar por nombre
        if not file_id and action in ["delete", "move"]:
            match = re.search(r'(eliminar|mover)\s*archivo[:\s]*(.+)', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Dime el nombre del archivo (ej: 'eliminar archivo: doc.txt')"}), 400
            file_name = match.group(2).strip()
            file_id = get_file_id_by_name(file_name, is_folder=False, headers=headers)
            if not file_id:
                return jsonify({"error": f"No encontré el archivo '{file_name}' en OneDrive"}), 404
            print(f"File ID found: {file_id}")

        # Acción: Eliminar archivo
        if action == "delete":
            if not file_id:
                return jsonify({"error": "Necesito el ID del archivo para eliminarlo"}), 400
            response = requests.delete(
                f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}",
                headers=headers
            )
            if response.status_code == 204:
                updated_user = mongo.database.usuarios.find_one({"correo": email})
                if updated_user:
                    cache.set(email, updated_user, timeout=1800)
                return jsonify({"success": f"🗑️ ¡Listo! El archivo ha sido eliminado de OneDrive con éxito."})
            return jsonify({"error": "No pude eliminar el archivo", "details": response.text}), response.status_code

        # Acción: Mover archivo
        elif action == "move":
            if not file_id:
                return jsonify({"error": "Necesito el ID del archivo para moverlo"}), 400
            match = re.search(r'mover\s*archivo[:\s]*.+?\s*a\s*carpeta[:\s]*(.+)', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Dime a qué carpeta moverlo (ej: 'mover archivo: doc.txt a carpeta: Trabajo')"}), 400
            folder_name = match.group(1).strip()
            folder_id = get_file_id_by_name(folder_name, is_folder=True, headers=headers)
            if not folder_id:
                return jsonify({"error": f"No encontré la carpeta '{folder_name}' en OneDrive"}), 404
            print(f"Folder ID found: {folder_id}")

            # Mover el archivo a la nueva carpeta
            response = requests.patch(
                f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}",
                headers=headers,
                json={"parentReference": {"id": folder_id}}
            )
            if response.status_code == 200:
                updated_user = mongo.database.usuarios.find_one({"correo": email})
                if updated_user:
                    cache.set(email, updated_user, timeout=1800)
                file_name = re.search(r'archivo[:\s]*(.+?)\s*a\s*carpeta', user_text, re.IGNORECASE).group(1).strip()
                return jsonify({"success": f"🎉 ¡Hecho! El archivo '{file_name}' ha sido movido a la carpeta '{folder_name}' en OneDrive."})
            return jsonify({"error": "No pude mover el archivo", "details": response.text}), response.status_code

        # Acción: Crear carpeta
        elif action == "create_folder":
            match = re.search(r'crear\s*carpeta[:\s]*(.+)', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Dime el nombre de la carpeta (ej: 'crear carpeta: Nueva')"}), 400
            folder_name = match.group(1).strip()
            response = requests.post(
                "https://graph.microsoft.com/v1.0/me/drive/root/children",
                headers=headers,
                json={"name": folder_name, "folder": {}, "@microsoft.graph.conflictBehavior": "rename"}
            )
            if response.status_code == 201:
                return jsonify({"success": f"📂 ¡Listo! La carpeta '{folder_name}' ha sido creada en OneDrive con éxito."})
            return jsonify({"error": "No pude crear la carpeta", "details": response.text}), response.status_code

        return jsonify({"error": "No entendí, ¿quieres 'eliminar', 'mover' o 'crear carpeta'?"}), 400

    def get_file_id_by_name(file_name, is_folder=False, headers=None):
        """Busca el ID de un archivo o carpeta por nombre en OneDrive."""
        try:
            url = f"https://graph.microsoft.com/v1.0/me/drive/root/search(q='{file_name}')"
            response = requests.get(url, headers=headers, timeout=10)
            print(f"Search response: {response.status_code} {response.text}")
            if response.status_code != 200:
                return None
            items = response.json().get("value", [])
            for item in items:
                is_folder_item = "folder" in item
                if item["name"].lower() == file_name.lower() and is_folder_item == is_folder:
                    return item["id"]
            return None
        except requests.RequestException as e:
            print(f"Error al buscar en OneDrive: {str(e)}")
            return None