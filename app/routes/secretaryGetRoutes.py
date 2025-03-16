from flask import request, jsonify
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from config import Config
from datetime import datetime
import openai
from flask_caching import Cache
from app.utils.utils import get_user_from_db
openai.api_key=Config.CHAT_API_KEY

def setup_routes_secretary_gets(app, mongo, cache):
    cache = Cache(app)
    
    def get_gmail_headers(token):
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    def get_outlook_headers(token):
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    def get_slack_headers(token):
        return {"Authorization": f"Bearer {token}"}

    def get_hubspot_headers(api_key):
        return {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json"
        }

    def get_notion_headers(token):
        return {
            "Authorization": f"Bearer {token}",
            'Notion-Version': '2022-06-28',
            'Content-Type': 'application/json'
        }

    def get_clickup_headers(token):
        return {
            "Authorization": token,
            "Content-Type": "application/json"
        }

    def get_dropbox_headers(token):
        return {"Authorization": f"Bearer {token}"}

    def get_google_drive_headers(token):
        return {"Authorization": f"Bearer {token}"}

    def get_onedrive_headers(token):
        return {"Authorization": f"Bearer {token}"}

    def get_teams_headers(token):
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    def get_asana_headers(token):
        return {
            "Authorization": f"Bearer {token}",
        }


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

    @app.route("/ultima-notificacion/gmail", methods=["GET"])
    def obtener_ultimo_correo_gmail():
        email = request.args.get("email")
        try:
            user = get_user_from_db(email, cache, mongo)
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            token = user.get("integrations", {}).get("Gmail", {}).get("token")
            if not token:
                return jsonify({"error": "Token no disponible"}), 400

            headers = get_gmail_headers(token)
            # Filtrar solo correos en bandeja de entrada, excluyendo enviados por el usuario
            response = requests.get(
                "https://www.googleapis.com/gmail/v1/users/me/messages",
                headers=headers,
                params={
                    "maxResults": 1,
                    "q": "in:inbox -from:me"  # Solo recibidos en la bandeja de entrada
                }
            )

            if response.status_code != 200:
                return jsonify({"error": "Error al obtener correos"}), response.status_code

            messages = response.json().get("messages", [])
            if not messages:
                return jsonify({"error": "No hay correos nuevos en tu bandeja de entrada, ¿reviso luego?"}), 404

            message_id = messages[0]["id"]
            response = requests.get(
                f"https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}?format=full",
                headers=headers
            )
            message = response.json()
            headers_list = message.get("payload", {}).get("headers", [])

            subject = next((h["value"] for h in headers_list if h["name"] == "Subject"), "(Sin asunto)")
            sender = next((h["value"] for h in headers_list if h["name"] == "From"), "(Desconocido)")

            return jsonify({
                "id": message_id,
                "from": "Gmail",
                "subject": f"Hola, te llegó un correo de {sender}",
                "snippet": f"Es sobre: {subject}. Dime qué hago con él en el recuadro de abajo (puedes decirme 'elimina', 'responde' o 'spam')."
            })
        except Exception as e:
            return jsonify({"error": "Uy, algo salió mal al revisar tu Gmail, ¿lo intento de nuevo?", "details": str(e)}), 500
                
    @app.route("/ultima-notificacion/outlook", methods=["GET"])
    def obtener_ultimo_correo_outlook():
        email = request.args.get("email")
        try:
            user = get_user_from_db(email, cache, mongo)
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            token = user.get("integrations", {}).get("Outlook", {}).get("token")
            if not token:
                return jsonify({"error": "Token no disponible"}), 400

            headers = get_outlook_headers(token)
            # Usar 'inbox' directamente en lugar de buscar el ID
            response = requests.get(
                "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages",
                headers=headers,
                params={
                    "$top": 1,
                    "$orderby": "receivedDateTime desc"  # Último recibido
                }
            )

            if response.status_code != 200:
                return jsonify({"error": "Error al obtener correos"}), response.status_code

            messages = response.json().get("value", [])
            if not messages:
                return jsonify({"error": "No hay correos nuevos en tu bandeja de entrada, ¿te aviso si llega algo?"}), 404

            message = messages[0]
            return jsonify({
                "id": message["id"],
                "from": "Outlook",
                "subject": f"Hola, tienes un correo nuevo de {message['from']['emailAddress']['address']}",
                "snippet": f"Es sobre: {message['subject']}. Escribe abajo qué hago: 'elimina', 'responde' o 'spam'."
            })
        except Exception as e:
            return jsonify({"error": "Ups, algo falló con Outlook, ¿lo reviso otra vez?", "details": str(e)}), 500
            
    @app.route("/ultima-notificacion/notion", methods=["GET"])
    def obtener_ultima_notificacion_notion():
        email = request.args.get("email")
        try:
            user = get_user_from_db(email, cache, mongo)
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            notion_token = user.get('integrations', {}).get('Notion', {}).get('token')
            if not notion_token:
                return jsonify({"error": "Token de Notion no disponible"}), 400

            headers = get_notion_headers(notion_token)

            # Función auxiliar para obtener el título de un objeto
            def get_title(properties):
                for prop_name, prop_value in properties.items():
                    if prop_value.get("type") == "title" and prop_value.get("title"):
                        return prop_value["title"][0].get("text", {}).get("content", "(Sin título)")
                return "(Sin título)"

            # 1. Obtener todas las páginas accesibles
            pages_response = requests.post(
                "https://api.notion.com/v1/search",
                headers=headers,
                json={
                    "sort": {"direction": "descending", "timestamp": "last_edited_time"},
                    "page_size": 100,  # Máximo permitido por Notion
                    "filter": {"value": "page", "property": "object"}
                }
            )
            if pages_response.status_code != 200:
                return jsonify({"error": "Error al obtener páginas de Notion"}), pages_response.status_code

            pages = [
                {
                    "id": page["id"],
                    "type": "Página",
                    "title": get_title(page.get("properties", {})),
                    "last_edited_time": page["last_edited_time"]
                }
                for page in pages_response.json().get("results", [])
                if not page.get("archived", False)
            ]

            # 2. Obtener todas las bases de datos accesibles
            databases_response = requests.post(
                "https://api.notion.com/v1/search",
                headers=headers,
                json={
                    "sort": {"direction": "descending", "timestamp": "last_edited_time"},
                    "page_size": 100,
                    "filter": {"value": "database", "property": "object"}
                }
            )
            if databases_response.status_code != 200:
                return jsonify({"error": "Error al obtener bases de datos de Notion"}), databases_response.status_code

            databases = databases_response.json().get("results", [])

            # 3. Consultar las filas (items) de cada base de datos
            all_items = pages  # Combinaremos páginas y filas aquí
            for db in databases:
                db_id = db["id"]
                query_response = requests.post(
                    f"https://api.notion.com/v1/databases/{db_id}/query",
                    headers=headers,
                    json={
                        "sorts": [{"property": "last_edited_time", "direction": "descending"}],
                        "page_size": 1  # Solo queremos el más reciente por base de datos
                    }
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

            # 4. Si no hay elementos, devolver mensaje
            if not all_items:
                return jsonify({"error": "No hay páginas ni filas recientes en Notion, ¿reviso después?"}), 404

            # 5. Ordenar todos los elementos por last_edited_time y tomar el más reciente
            latest_item = max(all_items, key=lambda x: x["last_edited_time"])

            # 6. Formatear la respuesta
            return jsonify({
                "id": latest_item["id"],
                "from": "Notion",
                "subject": f"Hola, hay algo nuevo en Notion",
                "snippet": f"Es una {latest_item['type']} llamada '{latest_item['title']}'. Dime qué hago en el recuadro: 'marca como hecha', 'elimina' o 'edita'."
            })

        except Exception as e:
            return jsonify({"error": "Uy, algo salió mal revisando Notion, ¿lo intento de nuevo?", "details": str(e)}), 500
                
    @app.route("/ultima-notificacion/slack", methods=["GET"])
    def obtener_ultimo_mensaje_slack():
        email = request.args.get("email")
        try:
            user = get_user_from_db(email, cache, mongo)
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            token = user.get("integrations", {}).get("Slack", {}).get("token")
            if not token:
                return jsonify({"error": "Token no disponible"}), 400

            headers = get_slack_headers(token)
            response = requests.get("https://slack.com/api/conversations.list?types=im", headers=headers)
            response_json = response.json()

            if not response_json.get("ok"):
                return jsonify({"error": "Error al obtener conversaciones", "details": response_json}), 400

            dms = response_json.get("channels", [])
            if not dms:
                return jsonify({"error": "No tienes mensajes directos recientes en Slack, ¿todo bien por ahí?"}), 404

            dms.sort(key=lambda x: x.get("latest", {}).get("ts", "0"), reverse=True)

            for dm in dms:
                channel_id = dm["id"]
                history_response = requests.get(f"https://slack.com/api/conversations.history?channel={channel_id}&limit=1", headers=headers)
                history_json = history_response.json()

                if history_json.get("ok") and history_json.get("messages"):
                    message = history_json["messages"][0]
                    return jsonify({
                        "id": message["ts"],
                        "from": "Slack",
                        "subject": f"Oye, te escribió alguien en Slack",
                        "snippet": f"Es este mensaje: '{message['text']}'. ¿Qué quieres que haga? Escribe abajo 'responde', 'reacciona' o 'menciona'."
                    })

            return jsonify({"error": "No hay mensajes nuevos en Slack por ahora, ¿reviso después?"}), 404

        except Exception as e:
            return jsonify({"error": "Ups, algo falló con Slack, ¿quieres que lo revise otra vez?", "details": str(e)}), 500

    @app.route("/ultima-notificacion/onedrive", methods=["GET"])
    def obtener_ultimo_archivo_onedrive():
        email = request.args.get("email")
        try:
            user = get_user_from_db(email, cache, mongo)
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            token = user.get("integrations", {}).get("OneDrive", {}).get("token")
            if not token:
                return jsonify({"error": "Token no disponible"}), 400

            headers = get_onedrive_headers(token)
            url = "https://graph.microsoft.com/v1.0/me/drive/root/search(q='')"
            params = {"$orderby": "lastModifiedDateTime desc", "$top": "5", "$select": "id,name,file,lastModifiedDateTime"}
            response = requests.get(url, headers=headers, params=params)

            if response.status_code != 200:
                return jsonify({"error": "Error al obtener archivos de OneDrive"}), response.status_code

            items = response.json().get('value', [])
            archivos = [item for item in items if "file" in item]
            if not archivos:
                return jsonify({"error": "No hay archivos recientes en OneDrive, ¿te aviso si cambia algo?"}), 404

            last_file = archivos[0]
            return jsonify({
                "from": "OneDrive",
                "subject": f"Hola, vi un archivo actualizado en OneDrive",
                "snippet": f"Es '{last_file['name']}'. Escribe abajo qué hago: 'elimina', 'mueve' o 'renombra'.",
                "id": last_file["id"]
            })
        except Exception as e:
            return jsonify({"error": "Algo salió mal con OneDrive, ¿lo intento de nuevo?", "details": str(e)}), 500

    @app.route("/ultima-notificacion/asana", methods=["GET"])
    def obtener_ultima_notificacion_asana():
        email = request.args.get("email")
        try:
            user = get_user_from_db(email, cache, mongo)
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            token = user.get("integrations", {}).get("Asana", {}).get("token")
            if not token:
                return jsonify({"error": "Token no disponible"}), 400

            headers = get_asana_headers(token)
            workspaces_response = requests.get("https://app.asana.com/api/1.0/workspaces", headers=headers)
            if workspaces_response.status_code != 200:
                return jsonify({"error": "No se pudo obtener el workspace"}), workspaces_response.status_code

            workspace_id = workspaces_response.json().get("data", [])[0]["gid"]
            user_response = requests.get("https://app.asana.com/api/1.0/users/me", headers=headers)
            user_id = user_response.json().get("data", {}).get("gid")

            response = requests.get(
                f"https://app.asana.com/api/1.0/tasks?assignee={user_id}&workspace={workspace_id}&limit=1",
                headers=headers
            )
            if response.status_code != 200:
                return jsonify({"error": "Error al obtener tareas", "details": response.json()}), response.status_code

            tasks = response.json().get("data", [])
            if not tasks:
                return jsonify({"error": "No hay tareas asignadas en Asana, ¿reviso después?"}), 404

            task = tasks[0]
            return jsonify({
                "from": "Asana",
                "subject": f"Hola, tienes una tarea nueva en Asana",
                "snippet": f"Es '{task.get('name', '(Sin título)')}'. Dime qué hago abajo: 'marca como hecha', 'elimina' o 'asigna'.",
                "id": task["gid"]
            })
        except Exception as e:
            return jsonify({"error": "Ups, algo falló con Asana, ¿lo intento de nuevo?", "details": str(e)}), 500

    @app.route("/ultima-notificacion/dropbox", methods=["GET"])
    def obtener_ultimo_archivo_dropbox():
        email = request.args.get("email")
        try:
            user = get_user_from_db(email, cache, mongo)
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            token = user.get("integrations", {}).get("Dropbox", {}).get("token")
            if not token:
                return jsonify({"error": "Token no disponible"}), 400

            headers = get_dropbox_headers(token)
            response = requests.post("https://api.dropboxapi.com/2/files/list_folder", headers=headers, json={"path": ""})
            if response.status_code != 200:
                return jsonify({"error": "Error al obtener archivos"}), response.status_code

            entries = response.json().get("entries", [])
            if not entries:
                return jsonify({"error": "No hay nada nuevo en Dropbox, ¿te aviso después?"}), 404

            files = [entry for entry in entries if entry[".tag"] == "file"]
            if not files:
                return jsonify({"error": "No hay archivos recientes en Dropbox, ¿reviso luego?"}), 404

            last_file = sorted(files, key=lambda x: x.get('client_modified', ''), reverse=True)[0]
            return jsonify({
                "from": "Dropbox",
                "subject": f"Hola, hay un archivo actualizado en Dropbox",
                "snippet": f"Es '{last_file['name']}'. Escribe abajo qué hago: 'elimina', 'mueve' o 'restaura'.",
                "id": last_file["id"]
            })
        except Exception as e:
            return jsonify({"error": "Algo salió mal con Dropbox, ¿lo intento de nuevo?", "details": str(e)}), 500
        
    def parse_hubspot_date(date_string, timezone="UTC", output_format="day_month_year_time"):
        """
        Parsea una fecha de HubSpot en formato ISO 8601 y la convierte a un formato legible.

        Args:
            date_string (str): Fecha en formato ISO 8601 (ej: "2025-03-16T12:34:56Z").
            timezone (str): Zona horaria para ajustar la fecha (default: "UTC").
            output_format (str): Formato de salida. Opciones:
                - "day_month_year_time" (default): "16 de marzo de 2025, 12:34"
                - "iso": "2025-03-16T12:34:56Z" (sin cambios)
                - "datetime": Devuelve objeto datetime sin formatear

        Returns:
            str o datetime: Fecha formateada o objeto datetime según output_format.

        Raises:
            ValueError: Si la fecha no es válida.
        """
        try:
            # Parsear la fecha ISO 8601
            dt = datetime.fromisoformat(date_string.replace("Z", "+00:00"))

            # Convertir a la zona horaria especificada
            tz = ZoneInfo(timezone)
            dt = dt.astimezone(tz)

            # Mapa de meses para formato legible en español
            months = {
                1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
                7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
            }

            # Devolver según el formato solicitado
            if output_format == "day_month_year_time":
                day = dt.day
                month = months[dt.month]
                year = dt.year
                time = dt.strftime("%H:%M")
                return f"{day} de {month} de {year}, {time}"
            elif output_format == "iso":
                return dt.isoformat()
            elif output_format == "datetime":
                return dt
            else:
                raise ValueError("Formato de salida no soportado. Usa 'day_month_year_time', 'iso' o 'datetime'.")

        except (ValueError, TypeError) as e:
            raise ValueError(f"No pude parsear la fecha '{date_string}': {str(e)}")
    
    @app.route('/ultima-notificacion/hubspot', methods=['GET'])
    def get_last_notification_hubspot():
        email = request.args.get("email")
        try:
            user = get_user_from_db(email, cache, mongo)
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            token = user.get('integrations', {}).get('HubSpot', {}).get('token')
            if not token:
                return jsonify({"error": "Token de HubSpot no disponible"}), 400

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
                    last_modified = parse_hubspot_date(result["properties"].get("hs_lastmodifieddate", "0"))
                    if not latest_update or last_modified > latest_update["timestamp"]:
                        latest_update = {"type": entity, "data": result, "timestamp": last_modified}

            if not latest_update:
                return jsonify({"error": "No hay cambios recientes en HubSpot, ¿te aviso luego?"}), 404

            entity_type = latest_update["type"]
            properties = latest_update["data"]["properties"]
            subject = (
                f"{properties.get('firstname', '')} {properties.get('lastname', '')}".strip() if entity_type == "contacto" else
                properties.get("dealname", "(Sin nombre)") if entity_type == "negocio" else
                properties.get("name", "(Sin nombre)")
            )

            return jsonify({
                "from": "HubSpot",
                "subject": f"Oye, hay algo nuevo en HubSpot",
                "snippet": f"Es un {entity_type} llamado '{subject}'. Escribe abajo tu acción que quieres hacer: 'cierra', 'elimina' o 'actualiza'.",
                "id": latest_update["data"]["id"]
            })
        except Exception as e:
            return jsonify({"error": "Ups, algo falló con HubSpot, ¿lo intento de nuevo?", "details": str(e)}), 500

    @app.route("/ultima-notificacion/clickup", methods=["GET"])
    def obtener_ultima_notificacion_clickup():
        email = request.args.get("email")
        try:
            user = get_user_from_db(email, cache, mongo)
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            token = user.get("integrations", {}).get("ClickUp", {}).get("token")
            if not token:
                return jsonify({"error": "Token no disponible"}), 400

            headers = get_clickup_headers(token)
            response = requests.get("https://api.clickup.com/api/v2/team", headers=headers)
            if response.status_code != 200:
                return jsonify({"error": "Error al obtener notificaciones"}), response.status_code

            team_id = response.json().get("teams", [])[0]["id"]
            response = requests.get(f"https://api.clickup.com/api/v2/team/{team_id}/task", headers=headers)
            tasks = response.json().get("tasks", [])
            if not tasks:
                return jsonify({"error": "No hay tareas nuevas en ClickUp, ¿reviso después?"}), 404

            task = tasks[0]
            return jsonify({
                "from": "ClickUp",
                "subject": f"Hola, te llegó una tarea en ClickUp",
                "snippet": f"Es '{task['name']}'. Dime qué hago abajo: 'marca como lista', 'elimina' o 'cambia estado'.",
                "id": task["id"]
            })
        except Exception as e:
            return jsonify({"error": "Algo salió mal con ClickUp, ¿lo intento de nuevo?", "details": str(e)}), 500    

    @app.route("/ultima-notificacion/drive", methods=["GET"])
    def obtener_ultimo_archivo_drive():
        email = request.args.get("email")
        try:
            user = get_user_from_db(email, cache, mongo)
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            token = user.get("integrations", {}).get("Drive", {}).get("token")
            if not token:
                return jsonify({"error": "Token no disponible"}), 400

            headers = get_google_drive_headers(token)
            url = "https://www.googleapis.com/drive/v3/files"
            params = {"pageSize": 10, "fields": "files(id, name, mimeType, modifiedTime)", "orderBy": "modifiedTime desc"}
            response = requests.get(url, headers=headers, params=params)

            if response.status_code != 200:
                return jsonify({"error": "Error al obtener archivos de Google Drive"}), response.status_code

            files = response.json().get('files', [])
            if not files:
                return jsonify({"error": "No hay nada nuevo en Drive, ¿te aviso si cambia algo?"}), 404

            last_entry = files[0]
            entry_type = "carpeta" if last_entry["mimeType"] == "application/vnd.google-apps.folder" else "archivo"

            return jsonify({
                "from": "Google Drive",
                "subject": f"Hola, vi que hay un {entry_type} actualizado en Drive",
                "snippet": f"Se llama '{last_entry['name']}'. Escribe abajo qué hago: 'elimina', 'mueve' o 'renombra'.",
                "id": last_entry["id"]
            })
        except Exception as e:
            return jsonify({"error": "Algo salió mal revisando Drive, ¿lo intento de nuevo?", "details": str(e)}), 500
            
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
