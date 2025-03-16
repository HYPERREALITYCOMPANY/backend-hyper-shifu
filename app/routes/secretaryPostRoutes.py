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

        if action == "delete":
            response = requests.post(f"https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}/trash", headers=headers)
            return jsonify({"success": "¡Listo! El correo está en la papelera."}) if response.status_code == 204 else jsonify({"error": "Uy, no pude eliminar el correo, ¿lo intentamos de nuevo?"}), response.status_code

        elif action == "spam":
            response = requests.post(
                f"https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}/modify",
                headers=headers,
                json={"addLabelIds": ["SPAM"], "removeLabelIds": ["INBOX"]}
            )
            return jsonify({"success": "¡Hecho! Ese correo ya está en spam."}) if response.status_code == 200 else jsonify({"error": "No pude moverlo a spam, ¿probamos otra vez?"}), response.status_code

        elif action == "reply" or action == "send":
            reply_text = data.get("reply_text", "")
            if not reply_text:
                match = re.search(r'responde(?: con)?:\s*(.+)', user_text, re.IGNORECASE)
                if not match:
                    return jsonify({"error": "Dime qué responder con 'reply_text' o en el texto (ej: 'responde: Hola')"}), 400
                reply_text = match.group(1).strip()

            msg_response = requests.get(f"https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}", headers=headers)
            if msg_response.status_code != 200:
                return jsonify({"error": "No pude encontrar el correo original, ¿revisamos?"}), msg_response.status_code
            msg_data = msg_response.json()
            headers_list = msg_data.get("payload", {}).get("headers", [])
            subject = next((h["value"] for h in headers_list if h["name"] == "Subject"), "(Sin asunto)")
            to = next((h["value"] for h in headers_list if h["name"] == "From"), "me")

            mensaje = MIMEText(reply_text)
            mensaje["To"] = to
            mensaje["Subject"] = f"Re: {subject}"
            mensaje["From"] = "me"
            mensaje_bytes = mensaje.as_bytes()
            mensaje_base64 = base64.urlsafe_b64encode(mensaje_bytes).decode()

            response = requests.post(
                f"https://www.googleapis.com/gmail/v1/users/me/messages/send",
                headers=headers,
                json={"raw": mensaje_base64, "threadId": msg_data.get("threadId")}
            )
            return jsonify({"success": f"¡Enviado! Respondí con: '{reply_text}'."}) if response.status_code == 200 else jsonify({"error": "No pude enviar la respuesta, ¿lo intentamos otra vez?"}), response.status_code

        return jsonify({"error": "No entendí, ¿quieres 'elimina', 'responde' o 'spam'?"}), 400

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
            return jsonify({"success": "¡Listo! El correo está eliminado."}) if response.status_code == 204 else jsonify({"success": "¡Hecho! Correo eliminado (Outlook a veces no dice mucho)."})

        elif action == "reply" or action == "send":
            reply_text = data.get("reply_text", "")
            if not reply_text:
                match = re.search(r'responde(?: con)?:\s*(.+)', user_text, re.IGNORECASE)
                if not match:
                    return jsonify({"error": "Dime qué responder con 'reply_text' o en el texto (ej: 'responde: Hola')"}), 400
                reply_text = match.group(1).strip()

            response = requests.post(
                f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/reply",
                headers=headers,
                json={"comment": reply_text}
            )
            return jsonify({"success": f"¡Respondido! Dije: '{reply_text}'."}) if response.status_code == 201 else jsonify({"error": "No pude responder, ¿lo intentamos de nuevo?"}), response.status_code

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
        page_id = data.get("message_id")  # Puede ser página o fila

        if not email or not user_text or not page_id:
            return jsonify({"error": "Me faltan datos: tu email, qué hacer y el ID, ¿me los das?"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "No te encontré, ¿estás registrado?"}), 404

        token = user.get("integrations", {}).get("Notion", {}).get("token")
        if not token:
            return jsonify({"error": "No tengo acceso a tu Notion, ¿revisamos?"}), 400

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}
        action = interpretar_accion_productividad(user_text)

        if action == "mark_done":
            response = requests.patch(
                f"https://api.notion.com/v1/pages/{page_id}",
                headers=headers,
                json={"properties": {"Status": {"select": {"name": "Completed"}}}}  # Ajusta "Status" según tu DB
            )
            return jsonify({"success": "¡Listo! La tarea está marcada como hecha."}) if response.status_code == 200 else jsonify({"error": "No pude marcarla, ¿intentamos otra vez?"}), response.status_code

        elif action == "delete":
            response = requests.patch(
                f"https://api.notion.com/v1/pages/{page_id}",
                headers=headers,
                json={"archived": True}
            )
            return jsonify({"success": "¡Hecho! La página o fila está archivada."}) if response.status_code == 200 else jsonify({"error": "No pude archivarla, ¿probamos de nuevo?"}), response.status_code

        elif action == "edit":
            new_title = data.get("new_title", "")
            if not new_title:
                match = re.search(r'edita(?: con)?:\s*(.+)', user_text, re.IGNORECASE)
                if not match:
                    return jsonify({"error": "Dime el nuevo título con 'new_title' o en el texto (ej: 'edita: Nuevo título')"}), 400
                new_title = match.group(1).strip()

            response = requests.patch(
                f"https://api.notion.com/v1/pages/{page_id}",
                headers=headers,
                json={"properties": {"title": {"title": [{"text": {"content": new_title}}]}}}
            )
            return jsonify({"success": f"¡Listo! Cambié el título a '{new_title}'."}) if response.status_code == 200 else jsonify({"error": "No pude editarla, ¿lo intentamos otra vez?"}), response.status_code

        return jsonify({"error": "No entendí, ¿quieres 'marca como hecha', 'elimina' o 'edita'?"}), 400

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

        if not email or not user_text or not task_id:
            return jsonify({"error": "Me faltan datos: tu email, qué hacer y el ID, ¿me los das?"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "No te encontré, ¿estás registrado?"}), 404

        token = user.get("integrations", {}).get("Asana", {}).get("token")
        if not token:
            return jsonify({"error": "No tengo acceso a tu Asana, ¿revisamos?"}), 400

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        action = interpretar_accion_productividad(user_text)

        if action == "mark_done":
            response = requests.put(
                f"https://app.asana.com/api/1.0/tasks/{task_id}",
                headers=headers,
                json={"data": {"completed": True}}
            )
            return jsonify({"success": "¡Listo! La tarea está marcada como hecha."}) if response.status_code == 200 else jsonify({"error": "No pude marcarla, ¿lo intentamos otra vez?"}), response.status_code

        elif action == "delete":
            response = requests.delete(
                f"https://app.asana.com/api/1.0/tasks/{task_id}",
                headers=headers
            )
            return jsonify({"success": "¡Hecho! La tarea está eliminada."}) if response.status_code == 204 else jsonify({"error": "No pude eliminarla, ¿probamos de nuevo?"}), response.status_code

        elif action == "assign":
            match = re.search(r'asigna(?: a)?:\s*(.+)', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Dime a quién asignarla (ej: 'asigna: juan@example.com')"}), 400
            assignee = match.group(1).strip()

            response = requests.put(
                f"https://app.asana.com/api/1.0/tasks/{task_id}",
                headers=headers,
                json={"data": {"assignee": assignee}}
            )
            return jsonify({"success": f"¡Listo! Asigné la tarea a '{assignee}'."}) if response.status_code == 200 else jsonify({"error": "No pude asignarla, ¿lo intentamos otra vez?"}), response.status_code

        return jsonify({"error": "No entendí, ¿quieres 'marca como hecha', 'elimina' o 'asigna'?"}), 400

    @app.route("/accion-clickup", methods=["POST"])
    def ejecutar_accion_clickup():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        task_id = data.get("message_id")

        if not email or not user_text or not task_id:
            return jsonify({"error": "Me faltan datos: tu email, qué hacer y el ID, ¿me los das?"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "No te encontré, ¿estás registrado?"}), 404

        token = user.get("integrations", {}).get("ClickUp", {}).get("token")
        if not token:
            return jsonify({"error": "No tengo acceso a tu ClickUp, ¿revisamos?"}), 400

        headers = {"Authorization": token, "Content-Type": "application/json"}
        action = interpretar_accion_productividad(user_text)

        if action == "mark_done":
            task_response = requests.get(f"https://api.clickup.com/api/v2/task/{task_id}", headers=headers)
            if task_response.status_code != 200:
                return jsonify({"error": "No encontré la tarea, ¿revisamos el ID?"}), task_response.status_code
            list_id = task_response.json()["list"]["id"]
            list_response = requests.get(f"https://api.clickup.com/api/v2/list/{list_id}", headers=headers)
            statuses = [status["status"] for status in list_response.json().get("statuses", [])]
            completed_status = next((s for s in statuses if s.lower() in ["complete", "done"]), "done")

            response = requests.put(
                f"https://api.clickup.com/api/v2/task/{task_id}",
                headers=headers,
                json={"status": completed_status}
            )
            return jsonify({"success": "¡Listo! La tarea está marcada como hecha."}) if response.status_code == 200 else jsonify({"error": "No pude marcarla, ¿lo intentamos otra vez?"}), response.status_code

        elif action == "delete":
            response = requests.delete(
                f"https://api.clickup.com/api/v2/task/{task_id}",
                headers=headers
            )
            return jsonify({"success": "¡Hecho! La tarea está eliminada."}) if response.status_code == 200 else jsonify({"error": "No pude eliminarla, ¿probamos de nuevo?"}), response.status_code

        elif action == "change_status":
            match = re.search(r'cambia(?: a)?:\s*(.+)', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Dime a qué estado cambiarla (ej: 'cambia: En Progreso')"}), 400
            new_status = match.group(1).strip()

            task_response = requests.get(f"https://api.clickup.com/api/v2/task/{task_id}", headers=headers)
            list_id = task_response.json()["list"]["id"]
            list_response = requests.get(f"https://api.clickup.com/api/v2/list/{list_id}", headers=headers)
            statuses = [status["status"] for status in list_response.json().get("statuses", [])]
            valid_status = next((s for s in statuses if s.lower() == new_status.lower()), None)
            if not valid_status:
                return jsonify({"error": f"Ese estado no existe. Opciones: {', '.join(statuses)}"}), 400

            response = requests.put(
                f"https://api.clickup.com/api/v2/task/{task_id}",
                headers=headers,
                json={"status": valid_status}
            )
            return jsonify({"success": f"¡Listo! Cambié el estado a '{valid_status}'."}) if response.status_code == 200 else jsonify({"error": "No pude cambiarlo, ¿lo intentamos otra vez?"}), response.status_code

        return jsonify({"error": "No entendí, ¿quieres 'marca como lista', 'elimina' o 'cambia estado'?"}), 400

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

        if not email or not user_text or not file_path:
            return jsonify({"error": "Me faltan datos: tu email, qué hacer y la ruta, ¿me los das?"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "No te encontré, ¿estás registrado?"}), 404

        token = user.get("integrations", {}).get("Dropbox", {}).get("token")
        if not token:
            return jsonify({"error": "No tengo acceso a tu Dropbox, ¿revisamos?"}), 400

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        action = interpretar_accion_archivos(user_text)

        if action == "delete":
            response = requests.post(
                "https://api.dropboxapi.com/2/files/delete_v2",
                headers=headers,
                json={"path": file_path}
            )
            return jsonify({"success": "¡Listo! El archivo está eliminado."}) if response.status_code == 200 else jsonify({"error": "No pude eliminarlo, ¿lo intentamos otra vez?"}), response.status_code

        elif action == "move":
            match = re.search(r'mueve(?: a)?:\s*(.+)', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Dime a qué carpeta moverlo (ej: 'mueve: /nueva')"}), 400
            dest_folder = match.group(1).strip()
            if not dest_folder.startswith('/'):
                dest_folder = f"/{dest_folder}"

            response = requests.post(
                "https://api.dropboxapi.com/2/files/move_v2",
                headers=headers,
                json={"from_path": file_path, "to_path": f"{dest_folder}/{file_path.split('/')[-1]}", "autorename": True}
            )
            return jsonify({"success": f"¡Hecho! Moví el archivo a '{dest_folder}'."}) if response.status_code == 200 else jsonify({"error": "No pude moverlo, ¿probamos de nuevo?"}), response.status_code

        elif action == "restore":
            response = requests.post(
                "https://api.dropboxapi.com/2/files/list_revisions",
                headers=headers,
                json={"path": file_path, "limit": 1}
            )
            if response.status_code != 200 or not response.json().get("entries"):
                return jsonify({"error": "No encontré versiones para restaurar."}), response.status_code
            revision = response.json()["entries"][0]["rev"]

            response = requests.post(
                "https://api.dropboxapi.com/2/files/restore",
                headers=headers,
                json={"path": file_path, "rev": revision}
            )
            return jsonify({"success": "¡Listo! El archivo está restaurado."}) if response.status_code == 200 else jsonify({"error": "No pude restaurarlo, ¿lo intentamos otra vez?"}), response.status_code

        return jsonify({"error": "No entendí, ¿quieres 'elimina', 'mueve' o 'restaura'?"}), 400

    @app.route("/accion-onedrive", methods=["POST"])
    def ejecutar_accion_onedrive():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        file_id = data.get("file_id")

        if not email or not user_text or not file_id:
            return jsonify({"error": "Me faltan datos: tu email, qué hacer y el ID, ¿me los das?"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "No te encontré, ¿estás registrado?"}), 404

        token = user.get("integrations", {}).get("OneDrive", {}).get("token")
        if not token:
            return jsonify({"error": "No tengo acceso a tu OneDrive, ¿revisamos?"}), 400

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        action = interpretar_accion_archivos(user_text)

        if action == "delete":
            response = requests.delete(
                f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}",
                headers=headers
            )
            return jsonify({"success": "¡Listo! El archivo está eliminado."}) if response.status_code == 204 else jsonify({"error": "No pude eliminarlo, ¿lo intentamos otra vez?"}), response.status_code

        elif action == "move":
            match = re.search(r'mueve(?: a)?:\s*(.+)', user_text, re.IGNORECASE)
            if not match:
                return jsonify({"error": "Dime a qué carpeta moverlo (ej: 'mueve: Trabajo')"}), 400
            dest_folder_name = match.group(1).strip()
            dest_folder_id = get_file_id_by_name(dest_folder_name, is_folder=True, headers=headers)
            if not dest_folder_id:
                return jsonify({"error": f"No encontré la carpeta '{dest_folder_name}'"}), 404

            response = requests.patch(
                f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}",
                headers=headers,
                json={"parentReference": {"id": dest_folder_id}}
            )
            return jsonify({"success": f"¡Hecho! Moví el archivo a '{dest_folder_name}'."}) if response.status_code == 200 else jsonify({"error": "No pude moverlo, ¿probamos de nuevo?"}), response.status_code

        elif action == "rename":
            new_name = data.get("new_name", "")
            if not new_name:
                match = re.search(r'renombra(?: a)?:\s*(.+)', user_text, re.IGNORECASE)
                if not match:
                    return jsonify({"error": "Dime el nuevo nombre (ej: 'renombra: Nuevo archivo')"}), 400
                new_name = match.group(1).strip()

            response = requests.patch(
                f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}",
                headers=headers,
                json={"name": new_name}
            )
            return jsonify({"success": f"¡Listo! Ahora se llama '{new_name}'."}) if response.status_code == 200 else jsonify({"error": "No pude renombrarlo, ¿lo intentamos otra vez?"}), response.status_code

        return jsonify({"error": "No entendí, ¿quieres 'elimina', 'mueve' o 'renombra'?"}), 400

    def get_file_id_by_name(file_name, is_folder=False, headers=None):
        url = f"https://graph.microsoft.com/v1.0/me/drive/root/search(q='{file_name}')"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            items = response.json().get("value", [])
            for item in items:
                if item["name"].lower() == file_name.lower() and ("folder" in item) == is_folder:
                    return item["id"]
        return None

