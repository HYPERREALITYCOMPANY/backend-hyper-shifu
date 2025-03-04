from flask import request, jsonify
import requests
from config import Config
import openai
openai.api_key=Config.CHAT_API_KEY
from app.routes.secretaryGetRoutes import setup_routes_secretary_gets
def setup_routes_secretary_posts(app, mongo):
    functions = setup_routes_secretary_gets(app, mongo)
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
        prompt = f"El usuario dijo: '{texto}'. Determina si quiere 'delete' (eliminar), 'reply' (responder) o 'spam' (mover a spam). Si no está claro, responde 'unknown'."
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": "Eres un asistente que analiza intenciones en correos electrónicos."},
                    {"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip().lower()

    def interpretar_accion_productividad(texto):
        prompt = f"El usuario dijo: '{texto}'. Determina si quiere 'mark_done' (marcar como completado), 'assign' (asignar a alguien más) o 'comment' (comentar en la tarea) o 'delete' (eliminar la tarea). Si no está claro, responde 'unknown'."
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": "Eres un asistente que analiza intenciones en plataformas de productividad."},
                    {"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip().lower()
    
    def interpretar_accion_hubspot(texto):
        prompt = f"El usuario dijo: '{texto}'. Determina si quiere 'follow_up' (hacer seguimiento a un cliente), 'close_deal' (cerrar un trato) o 'update_info' (actualizar la información de un cliente). Si no está claro, responde 'unknown'."
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": "Eres un asistente que analiza intenciones en un CRM de ventas."},
                    {"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip().lower()

    def interpretar_accion_archivos(texto):
        prompt = f"El usuario dijo: '{texto}'. Determina si quiere 'download' (descargar archivo), 'share' (compartir con alguien más) o 'delete' (eliminar archivo). Si no está claro, responde 'unknown'."
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": "Eres un asistente que analiza intenciones en plataformas de almacenamiento en la nube."},
                    {"role": "user", "content": prompt}]
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

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("Gmail", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        action = interpretar_accion_email(user_text)
        headers = get_gmail_headers(token)

        if "delete" in action:
            response = requests.post(f"https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}/trash", headers=headers)
            return jsonify({"success": "Correo eliminado"}) if response.status_code == 204 else jsonify({"success": "Correo eliminado"})

        elif "reply" in action:
            reply_text = data.get("reply_text", "")
            response = requests.post("https://www.googleapis.com/gmail/v1/users/me/messages/send", headers=headers, json={"raw": reply_text})
            return jsonify({"success": "Respuesta enviada"}) if response.status_code == 200 else jsonify({"error": "Error al responder correo"}), response.status_code

        elif "spam" in action:
            response = requests.post(f"https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}/modify",
                                    headers=headers, json={"addLabelIds": ["SPAM"], "removeLabelIds": ["INBOX"]})
            return jsonify({"success": "Correo marcado como spam"}) if response.status_code == 200 else jsonify({"error": "Error al marcar correo como spam"}), response.status_code

        return jsonify({"error": "Acción no reconocida"}), 400

    @app.route("/accion-outlook", methods=["POST"])
    def ejecutar_accion_outlook():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        message_id = data.get("message_id")

        user = mongo.database.usuarios.find_one({'correo': email})
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
            response = requests.patch(f"https://api.notion.com/v1/pages/{page_id}",
                                    headers=headers,
                                    json={"properties": {"status": {"select": {"name": "Listo"}}}})
            return jsonify({"success": "Página marcada como completada"}) if response.status_code == 200 else jsonify({"error": "Error al actualizar estado"}), response.status_code

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

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("Slack", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        action = interpretar_accion_mensajeria(user_text)
        headers = get_slack_headers(token)

        if "reply" in action:
            reply_text = data.get("reply_text", "")
            response = requests.post("https://slack.com/api/chat.postMessage",
                                    headers=headers, json={"channel": channel, "thread_ts": message_ts, "text": reply_text})
            return jsonify({"success": "Mensaje respondido"}) if response.status_code == 200 else jsonify({"error": "Error al responder"}), response.status_code

        return jsonify({"error": "Acción no reconocida"}), 400


    @app.route("/accion-asana", methods=["POST"])
    def ejecutar_accion_asana():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        task_id = data.get("message_id")

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("Asana", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        action = interpretar_accion_productividad(user_text)
        headers = get_asana_headers(token)

        if "complete" in action:
            # Realizar la solicitud PUT para marcar la tarea como completada
            response = requests.put(f"https://app.asana.com/api/1.0/tasks/{task_id}", headers=headers, json={"data": {"completed": True}})
            if response.status_code == 200:
                return jsonify({"success": "Tarea completada"})
            else:
                return jsonify({"error": "Error al completar tarea"}), response.status_code

        elif "delete" in action:
            # Realizar la solicitud DELETE para eliminar la tarea
            response = requests.delete(f"https://app.asana.com/api/1.0/tasks/{task_id}", headers=headers)
            if response.status_code == 204:
                return jsonify({"success": "Tarea eliminada"})
            else:
                return jsonify({"success": "Tarea eliminada"})

        return jsonify({"error": "Acción no reconocida"}), 400

    @app.route("/accion-clickup", methods=["POST"])
    def ejecutar_accion_clickup():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        task_id = data.get("message_id")

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("ClickUp", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        action = interpretar_accion_productividad(user_text)
        headers = {
            "Authorization": token,
            "Content-Type": "application/json"
        }
    
        if "mark_done" in action:
            response = requests.put(f"https://api.clickup.com/api/v2/task/{task_id}", headers=headers, json={"status": "complete"})
            return jsonify({"success": "Tarea completada"}) if response.status_code == 200 else jsonify({"error": "Error al completar tarea"}), response.status_code

        elif "delete" in action:
            response = requests.delete(f"https://api.clickup.com/api/v2/task/{task_id}", headers=headers)
            return jsonify({"success": "Tarea eliminada"}) if response.status_code == 204 else jsonify({"success": "Tarea eliminada"})

        return jsonify({"error": "Acción no reconocida"}), 400

    @app.route("/accion-hubspot", methods=["POST"])
    def ejecutar_accion_hubspot():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        deal_id = data.get("deal_id")

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("HubSpot", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        action = interpretar_accion_hubspot(user_text)
        headers = get_hubspot_headers(token)

        if "update" in action:
            new_stage = data.get("new_stage", "")
            response = requests.patch(f"https://api.hubapi.com/crm/v3/objects/deals/{deal_id}", headers=headers, json={"properties": {"dealstage": new_stage}})
            return jsonify({"success": "Negocio actualizado"}) if response.status_code == 200 else jsonify({"error": "Error al actualizar negocio"}), response.status_code

        return jsonify({"error": "Acción no reconocida"}), 400

    @app.route("/accion-dropbox", methods=["POST"])
    def ejecutar_accion_dropbox():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        file_path = data.get("file_path")

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("Dropbox", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        action = interpretar_accion_archivos(user_text)
        headers = get_dropbox_headers(token)

        if "delete" in action:
            response = requests.post("https://api.dropboxapi.com/2/files/delete_v2", headers=headers, json={"path": file_path})
            return jsonify({"success": "Archivo eliminado"}) if response.status_code == 200 else jsonify({"error": "Error al eliminar archivo"}), response.status_code

        return jsonify({"error": "Acción no reconocida"}), 400

    @app.route("/accion-onedrive", methods=["POST"])
    def ejecutar_accion_onedrive():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        file_id = data.get("file_id")

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("OneDrive", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        action = interpretar_accion_archivos(user_text)
        headers = get_onedrive_headers(token)

        if "delete" in action:
            response = requests.delete(f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}", headers=headers)
            return jsonify({"success": "Archivo eliminado"}) if response.status_code == 204 else jsonify({"error": "Error al eliminar archivo"}), response.status_code

        return jsonify({"error": "Acción no reconocida"}), 400

    @app.route("/accion-teams", methods=["POST"])
    def ejecutar_accion_teams():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        message_id = data.get("message_id")
        channel_id = data.get("channel_id")

        user = mongo.database.usuarios.find_one({'correo': email})
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
