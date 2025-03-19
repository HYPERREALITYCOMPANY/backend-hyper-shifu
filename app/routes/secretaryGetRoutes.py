from flask import Flask, request, jsonify
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from config import Config
import openai
from flask_caching import Cache
from app.utils.utils import get_user_from_db

openai.api_key = Config.CHAT_API_KEY

def setup_routes_secretary_gets(app, mongo, cache, refresh_functions):
    # Extraer las funciones de refresco
    get_refresh_tokens_from_db = refresh_functions["get_refresh_tokens_from_db"]
    refresh_tokens_func = refresh_functions["refresh_tokens"]

    def should_refresh_tokens(email):
        """Determina si se deben refrescar los tokens basado en el tiempo desde el último refresco."""
        last_refresh_key = f"last_refresh_{email}"
        last_refresh = cache.get(last_refresh_key)
        current_time = datetime.utcnow()

        if last_refresh is None:
            return True

        last_refresh_time = datetime.fromtimestamp(last_refresh)
        refresh_interval = timedelta(minutes=15)
        time_since_last_refresh = current_time - last_refresh_time

        if time_since_last_refresh >= refresh_interval:
            return True
        return False

    def get_user_with_refreshed_tokens(email):
        """Obtiene el usuario y refresca tokens solo si es necesario."""
        try:
            user = cache.get(email)
            if not user:
                user = get_user_from_db(email, cache, mongo)
                if not user:
                    return None
                cache.set(email, user, timeout=1800)

            if not should_refresh_tokens(email):
                return user

            integrations = user.get("integrations", {})
            refresh_tokens_dict = get_refresh_tokens_from_db(email)
            if not refresh_tokens_dict:
                cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
                return user

            tokens_to_refresh = {
                service: refresh_tokens_dict[service]
                for service, token_data in integrations.items()
                if service in refresh_tokens_dict and token_data.get("refresh_token") and token_data["refresh_token"] != "n/a"
            }

            if tokens_to_refresh:
                refreshed_tokens, errors = refresh_tokens_func(tokens_to_refresh, email)
                if refreshed_tokens:
                    updated_user = mongo.database.usuarios.find_one({"correo": email})
                    if updated_user:
                        cache.set(email, updated_user, timeout=1800)
                        cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
                        return updated_user
                    else:
                        print(f"[ERROR] No se pudo obtener usuario actualizado de la BD")
                elif errors:
                    print(f"[WARNING] Errores al refrescar tokens: {errors}")
            else:
                cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)

            return user
        except Exception as e:
            print(f"[ERROR] Error general en get_user_with_refreshed_tokens: {e}")
            return None

    # Funciones de headers
    def get_gmail_headers(token):
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    def get_outlook_headers(token):
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    def get_slack_headers(token):
        return {"Authorization": f"Bearer {token}"}

    def get_hubspot_headers(token):
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    def get_notion_headers(token):
        return {"Authorization": f"Bearer {token}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"}

    def get_clickup_headers(token):
        return {"Authorization": token, "Content-Type": "application/json"}

    def get_dropbox_headers(token):
        return {"Authorization": f"Bearer {token}"}

    def get_google_drive_headers(token):
        return {"Authorization": f"Bearer {token}"}

    def get_onedrive_headers(token):
        return {"Authorization": f"Bearer {token}"}

    def get_teams_headers(token):
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def get_asana_headers(token):
        return {"Authorization": f"Bearer {token}"}

    # Funciones de notificaciones individuales (sin verificar usuario)
    def fetch_gmail_notification(user):
        token = user.get("integrations", {}).get("Gmail", {}).get("token")
        if not token:
            return None
        headers = get_gmail_headers(token)
        response = requests.get(
            "https://www.googleapis.com/gmail/v1/users/me/messages",
            headers=headers,
            params={"maxResults": 1, "q": "in:inbox -from:me"}
        )
        if response.status_code != 200:
            return None
        messages = response.json().get("messages", [])
        if not messages:
            return None
        message_id = messages[0]["id"]
        response = requests.get(
            f"https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}?format=full",
            headers=headers
        )
        message = response.json()
        headers_list = message.get("payload", {}).get("headers", [])
        subject = next((h["value"] for h in headers_list if h["name"] == "Subject"), "(Sin asunto)")
        sender = next((h["value"] for h in headers_list if h["name"] == "From"), "(Desconocido)")
        return {
            "id": message_id,
            "from": "Gmail",
            "subject": f"Hola, te llegó un correo de {sender}",
            "snippet": f"Es sobre: {subject}."
        }

    def fetch_outlook_notification(user):
        token = user.get("integrations", {}).get("Outlook", {}).get("token")
        if not token:
            return None
        headers = get_outlook_headers(token)
        response = requests.get(
            "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages",
            headers=headers,
            params={"$top": 1, "$orderby": "receivedDateTime desc"}
        )
        if response.status_code != 200:
            return None
        messages = response.json().get("value", [])
        if not messages:
            return None
        message = messages[0]
        return {
            "id": message["id"],
            "from": "Outlook",
            "subject": f"Hola, tienes un correo nuevo de {message['from']['emailAddress']['address']}",
            "snippet": f"Es sobre: {message['subject']}."
        }

    def fetch_notion_notification(user):
        token = user.get("integrations", {}).get("Notion", {}).get("token")
        if not token:
            return None
        headers = get_notion_headers(token)

        def get_title(properties):
            for prop_name, prop_value in properties.items():
                if prop_value.get("type") == "title" and prop_value.get("title"):
                    return prop_value["title"][0].get("text", {}).get("content", "(Sin título)")
            return "(Sin título)"

        pages_response = requests.post(
            "https://api.notion.com/v1/search",
            headers=headers,
            json={"sort": {"direction": "descending", "timestamp": "last_edited_time"}, "page_size": 100, "filter": {"value": "page", "property": "object"}}
        )
        if pages_response.status_code != 200:
            return None
        pages = [
            {"id": page["id"], "type": "Página", "title": get_title(page.get("properties", {})), "last_edited_time": page["last_edited_time"]}
            for page in pages_response.json().get("results", []) if not page.get("archived", False)
        ]

        databases_response = requests.post(
            "https://api.notion.com/v1/search",
            headers=headers,
            json={"sort": {"direction": "descending", "timestamp": "last_edited_time"}, "page_size": 100, "filter": {"value": "database", "property": "object"}}
        )
        if databases_response.status_code != 200:
            return None
        databases = databases_response.json().get("results", [])

        all_items = pages
        for db in databases:
            db_id = db["id"]
            query_response = requests.post(
                f"https://api.notion.com/v1/databases/{db_id}/query",
                headers=headers,
                json={"sorts": [{"property": "last_edited_time", "direction": "descending"}], "page_size": 1}
            )
            if query_response.status_code == 200:
                db_items = query_response.json().get("results", [])
                for item in db_items:
                    if not item.get("archived", False):
                        all_items.append({
                            "id": item["id"],
                            "type": f"Fila en base de datos '{get_title(db.get('properties', {}))}'",
                            "title": get_title(item.get("properties", {})),
                            "last_edited_time": item["last_edited_time"]
                        })

        if not all_items:
            return None
        latest_item = max(all_items, key=lambda x: x["last_edited_time"])
        return {
            "id": latest_item["id"],
            "from": "Notion",
            "subject": f"Hola, hay algo nuevo en Notion",
            "snippet": f"Es una {latest_item['type']} llamada '{latest_item['title']}'."
        }

    def fetch_slack_notification(user):
        token = user.get("integrations", {}).get("Slack", {}).get("token")
        if not token:
            return None
        headers = get_slack_headers(token)
        response = requests.get("https://slack.com/api/conversations.list?types=im", headers=headers)
        response_json = response.json()
        if not response_json.get("ok"):
            return None
        dms = response_json.get("channels", [])
        if not dms:
            return None
        dms.sort(key=lambda x: x.get("latest", {}).get("ts", "0"), reverse=True)
        for dm in dms:
            channel_id = dm["id"]
            history_response = requests.get(f"https://slack.com/api/conversations.history?channel={channel_id}&limit=1", headers=headers)
            history_json = history_response.json()
            if history_json.get("ok") and history_json.get("messages"):
                message = history_json["messages"][0]
                return {
                    "id": message["ts"],
                    "from": "Slack",
                    "subject": f"Oye, te escribió alguien en Slack",
                    "snippet": f"Es este mensaje: '{message['text']}'."
                }
        return None

    def fetch_onedrive_notification(user):
        token = user.get("integrations", {}).get("OneDrive", {}).get("token")
        if not token:
            return None
        headers = get_onedrive_headers(token)
        url = "https://graph.microsoft.com/v1.0/me/drive/root/search(q='')"
        params = {"$orderby": "lastModifiedDateTime desc", "$top": "5", "$select": "id,name,file,lastModifiedDateTime"}
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            return None
        items = response.json().get('value', [])
        archivos = [item for item in items if "file" in item]
        if not archivos:
            return None
        last_file = archivos[0]
        return {
            "from": "OneDrive",
            "subject": f"Hola, vi un archivo actualizado en OneDrive",
            "snippet": f"Es '{last_file['name']}'.",
            "id": last_file["id"]
        }

    def fetch_asana_notification(user):
        token = user.get("integrations", {}).get("Asana", {}).get("token")
        if not token:
            return None
        headers = get_asana_headers(token)
        workspaces_response = requests.get("https://app.asana.com/api/1.0/workspaces", headers=headers, timeout=10)
        if workspaces_response.status_code != 200:
            return None
        workspace_id = workspaces_response.json().get("data", [])[0]["gid"]
        user_response = requests.get("https://app.asana.com/api/1.0/users/me", headers=headers, timeout=10)
        if user_response.status_code != 200:
            return None
        user_id = user_response.json().get("data", {}).get("gid")
        response = requests.get(
            f"https://app.asana.com/api/1.0/tasks?assignee={user_id}&workspace={workspace_id}&limit=50&opt_fields=name,gid,created_at,completed",
            headers=headers,
            timeout=10
        )
        if response.status_code != 200:
            return None
        tasks = response.json().get("data", [])
        if not tasks:
            return None
        incomplete_tasks = [task for task in tasks if not task.get("completed", False)]
        if not incomplete_tasks:
            return None
        incomplete_tasks.sort(key=lambda x: x["created_at"], reverse=True)
        latest_task = incomplete_tasks[0]
        return {
            "from": "Asana",
            "subject": f"Hola, tienes una tarea nueva en Asana",
            "snippet": f"Es '{latest_task.get('name', '(Sin título)')}'.",
            "id": latest_task["gid"]
        }

    def fetch_dropbox_notification(user):
        token = user.get("integrations", {}).get("Dropbox", {}).get("token")
        if not token:
            return None
        headers = get_dropbox_headers(token)
        response = requests.post("https://api.dropboxapi.com/2/files/list_folder", headers=headers, json={"path": ""})
        if response.status_code != 200:
            return None
        entries = response.json().get("entries", [])
        if not entries:
            return None
        files = [entry for entry in entries if entry[".tag"] == "file"]
        if not files:
            return None
        last_file = sorted(files, key=lambda x: x.get('client_modified', ''), reverse=True)[0]
        return {
            "from": "Dropbox",
            "subject": f"Hola, hay un archivo actualizado en Dropbox",
            "snippet": f"Es '{last_file['name']}'",
            "id": last_file["id"]
        }

    def parse_hubspot_date(date_string, timezone="UTC", output_format="day_month_year_time"):
        try:
            dt = datetime.fromisoformat(date_string.replace("Z", "+00:00"))
            tz = ZoneInfo(timezone)
            dt = dt.astimezone(tz)
            months = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
                      7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"}
            if output_format == "day_month_year_time":
                return f"{dt.day} de {months[dt.month]} de {dt.year}, {dt.strftime('%H:%M')}"
            elif output_format == "datetime":
                return dt
            return dt.isoformat()
        except (ValueError, TypeError) as e:
            raise ValueError(f"No pude parsear la fecha '{date_string}': {str(e)}")

    def fetch_hubspot_notification(user):
        token = user.get("integrations", {}).get("HubSpot", {}).get("token")
        if not token:
            return None
        headers = get_hubspot_headers(token)
        endpoints = {
            "contacto": "https://api.hubapi.com/crm/v3/objects/contacts/search",
            "negocio": "https://api.hubapi.com/crm/v3/objects/deals/search",
            "empresa": "https://api.hubapi.com/crm/v3/objects/companies/search"
        }
        search_data = {
            "filterGroups": [{"filters": [{"propertyName": "hs_lastmodifieddate", "operator": "GT", "value": "0"}]}],
            "properties": ["hs_lastmodifieddate", "dealname", "firstname", "lastname", "email", "name"],
            "limit": 1,
            "sorts": ["-hs_lastmodifieddate"]
        }
        latest_update = None
        for entity, url in endpoints.items():
            response = requests.post(url, headers=headers, json=search_data)
            if response.status_code == 200 and response.json().get("results"):
                result = response.json()["results"][0]
                last_modified = parse_hubspot_date(result["properties"].get("hs_lastmodifieddate", "0"), output_format="datetime")
                if not latest_update or last_modified > latest_update["timestamp"]:
                    latest_update = {"type": entity, "data": result, "timestamp": last_modified}
        if not latest_update:
            return None
        entity_type = latest_update["type"]
        properties = latest_update["data"]["properties"]
        subject = (
            f"{properties.get('firstname', '')} {properties.get('lastname', '')}".strip() if entity_type == "contacto" else
            properties.get("dealname", "(Sin nombre)") if entity_type == "negocio" else
            properties.get("name", "(Sin nombre)")
        )
        return {
            "from": "HubSpot",
            "subject": f"Oye, hay algo nuevo en HubSpot",
            "snippet": f"Es un {entity_type} llamado '{subject}'.",
            "id": latest_update["data"]["id"]
        }

    def convertir_fecha(timestamp):
        if timestamp:
            return datetime.utcfromtimestamp(int(timestamp) / 1000).strftime('%Y-%m-%d %H:%M:%S')
        return "No definida"

    def fetch_clickup_notification(user):
        token = user.get("integrations", {}).get("ClickUp", {}).get("token")
        if not token:
            return None
        headers = get_clickup_headers(token)
        response = requests.get("https://api.clickup.com/api/v2/team", headers=headers)
        if response.status_code != 200:
            return None
        teams = response.json().get("teams", [])
        if not teams:
            return None
        team_id = teams[0]["id"]
        response = requests.get(f"https://api.clickup.com/api/v2/team/{team_id}/task", headers=headers)
        if response.status_code != 200:
            return None
        tasks = response.json().get("tasks", [])
        if not tasks:
            return None
        task = tasks[0]
        due_date = convertir_fecha(task.get("due_date"))
        return {
            "id": task["id"],
            "name": task["name"],
            "status": task["status"]["status"],
            "due_date": due_date,
            "from": "ClickUp",
            "subject": task["name"],
            "snippet": f"Estado: {task['status']['status']}, Fecha límite: {due_date}"
        }

    def fetch_drive_notification(user):
        token = user.get("integrations", {}).get("Drive", {}).get("token")
        if not token:
            return None
        headers = get_google_drive_headers(token)
        url = "https://www.googleapis.com/drive/v3/files"
        params = {"pageSize": 10, "fields": "files(id, name, mimeType, modifiedTime)", "orderBy": "modifiedTime desc"}
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            return None
        files = response.json().get('files', [])
        if not files:
            return None
        last_entry = files[0]
        entry_type = "carpeta" if last_entry["mimeType"] == "application/vnd.google-apps.folder" else "archivo"
        return {
            "from": "Google Drive",
            "subject": f"Hola, vi que hay un {entry_type} actualizado en Drive",
            "snippet": f"Se llama '{last_entry['name']}'.",
            "id": last_entry["id"]
        }

    # Nuevo método para obtener todas las notificaciones
    @app.route("/ultima-notificacion/all", methods=["GET"])
    def obtener_todas_las_notificaciones():
        email = request.args.get("email")
        if not email:
            return jsonify({"error": "Se requiere email"}), 400

        try:
            # Verificación del usuario directamente en MongoDB
            user = mongo.database.usuarios.find_one({"correo": email})
            if not user:
                return jsonify({"error": "Usuario no encontrado en la base de datos"}), 404

            # Refrescar tokens si es necesario
            user = get_user_with_refreshed_tokens(email)
            if not user:
                return jsonify({"error": "No se pudo obtener el usuario actualizado"}), 500

            # Diccionario de funciones de notificación
            notification_functions = {
                "Gmail": fetch_gmail_notification,
                "Outlook": fetch_outlook_notification,
                "Notion": fetch_notion_notification,
                "Slack": fetch_slack_notification,
                "OneDrive": fetch_onedrive_notification,
                "Asana": fetch_asana_notification,
                "Dropbox": fetch_dropbox_notification,
                "HubSpot": fetch_hubspot_notification,
                "ClickUp": fetch_clickup_notification,
                "Drive": fetch_drive_notification
            }

            notifications = {}
            errors = {}

            # Obtener notificaciones para cada servicio
            for service, fetch_func in notification_functions.items():
                try:
                    if service in user.get("integrations", {}):
                        result = fetch_func(user)
                        if result:
                            notifications[service] = result
                        else:
                            errors[service] = f"No hay notificaciones recientes para {service}"
                except Exception as e:
                    errors[service] = f"Error al obtener notificación de {service}: {str(e)}"
                    print(f"[ERROR] Fallo al obtener notificación de {service}: {e}")

            return jsonify({
                "notifications": notifications,
                "errors": errors if errors else None
            }), 200 if not errors else 207  # 207 para éxito parcial
        except Exception as e:
            return jsonify({"error": "Error al obtener notificaciones", "details": str(e)}), 500

    # Mantengo las rutas individuales por si las necesitas, pero sin verificar usuario
    @app.route("/ultima-notificacion/gmail", methods=["GET"])
    def obtener_ultimo_correo_gmail():
        email = request.args.get("email")
        user = get_user_with_refreshed_tokens(email)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404
        result = fetch_gmail_notification(user)
        return jsonify(result if result else {"error": "No hay correos nuevos"}), 200 if result else 404

    @app.route("/ultima-notificacion/outlook", methods=["GET"])
    def obtener_ultimo_correo_outlook():
        email = request.args.get("email")
        user = get_user_with_refreshed_tokens(email)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404
        result = fetch_outlook_notification(user)
        return jsonify(result if result else {"error": "No hay correos nuevos"}), 200 if result else 404

    @app.route("/ultima-notificacion/notion", methods=["GET"])
    def obtener_ultima_notificacion_notion():
        email = request.args.get("email")
        user = get_user_with_refreshed_tokens(email)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404
        result = fetch_notion_notification(user)
        return jsonify(result if result else {"error": "No hay notificaciones nuevas"}), 200 if result else 404

    @app.route("/ultima-notificacion/slack", methods=["GET"])
    def obtener_ultimo_mensaje_slack():
        email = request.args.get("email")
        user = get_user_with_refreshed_tokens(email)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404
        result = fetch_slack_notification(user)
        return jsonify(result if result else {"error": "No hay mensajes nuevos"}), 200 if result else 404

    @app.route("/ultima-notificacion/onedrive", methods=["GET"])
    def obtener_ultimo_archivo_onedrive():
        email = request.args.get("email")
        user = get_user_with_refreshed_tokens(email)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404
        result = fetch_onedrive_notification(user)
        return jsonify(result if result else {"error": "No hay archivos nuevos"}), 200 if result else 404

    @app.route("/ultima-notificacion/asana", methods=["GET"])
    def obtener_ultima_notificacion_asana():
        email = request.args.get("email")
        user = get_user_with_refreshed_tokens(email)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404
        result = fetch_asana_notification(user)
        return jsonify(result if result else {"error": "No hay tareas nuevas"}), 200 if result else 404

    @app.route("/ultima-notificacion/dropbox", methods=["GET"])
    def obtener_ultimo_archivo_dropbox():
        email = request.args.get("email")
        user = get_user_with_refreshed_tokens(email)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404
        result = fetch_dropbox_notification(user)
        return jsonify(result if result else {"error": "No hay archivos nuevos"}), 200 if result else 404

    @app.route("/ultima-notificacion/hubspot", methods=["GET"])
    def get_last_notification_hubspot():
        email = request.args.get("email")
        user = get_user_with_refreshed_tokens(email)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404
        result = fetch_hubspot_notification(user)
        return jsonify(result if result else {"error": "No hay notificaciones nuevas"}), 200 if result else 404

    @app.route("/ultima-notificacion/clickup", methods=["GET"])
    def obtener_ultima_notificacion_clickup():
        email = request.args.get("email")
        user = get_user_with_refreshed_tokens(email)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404
        result = fetch_clickup_notification(user)
        return jsonify(result if result else {"error": "No hay tareas nuevas"}), 200 if result else 404

    @app.route("/ultima-notificacion/drive", methods=["GET"])
    def obtener_ultimo_archivo_drive():
        email = request.args.get("email")
        user = get_user_with_refreshed_tokens(email)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404
        result = fetch_drive_notification(user)
        return jsonify(result if result else {"error": "No hay archivos nuevos"}), 200 if result else 404

    return {
        "get_gmail_headers": get_gmail_headers,
        "get_outlook_headers": get_outlook_headers,
        "get_notion_headers": get_notion_headers,
        "get_slack_headers": get_slack_headers,
        "get_teams_headers": get_teams_headers,
        "get_onedrive_headers": get_onedrive_headers,
        "get_google_drive_headers": get_google_drive_headers,
        "get_hubspot_headers": get_hubspot_headers,
        "get_asana_headers": get_asana_headers,
        "get_dropbox_headers": get_dropbox_headers,
        "get_clickup_headers": get_clickup_headers,
    }
