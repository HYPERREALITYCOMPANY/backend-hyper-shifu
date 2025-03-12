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
            response = requests.get("https://www.googleapis.com/gmail/v1/users/me/messages?maxResults=1", headers=headers)

            if response.status_code != 200:
                return jsonify({"error": "Error al obtener correos"}), response.status_code

            messages = response.json().get("messages", [])
            if not messages:
                return jsonify({"error": "No hay correos"})

            message_id = messages[0]["id"]
            response = requests.get(f"https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}?format=full", headers=headers)
            message = response.json()
            headers_list = message.get("payload", {}).get("headers", [])

            subject = next((h["value"] for h in headers_list if h["name"] == "Subject"), "(Sin asunto)")
            sender = next((h["value"] for h in headers_list if h["name"] == "From"), "(Desconocido)")

            return jsonify({
                "id": message_id,
                "from": sender,
                "subject": subject,
                "snippet": message.get("snippet", "(Sin contenido)")
            })
        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500

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
            response = requests.get(
                "https://graph.microsoft.com/v1.0/me/messages?$top=1&$filter=parentFolderId ne 'JunkEmail'",
                headers=headers
            )

            if response.status_code != 200:
                return jsonify({"error": "Error al obtener correos"}), response.status_code

            messages = response.json().get("value", [])
            if not messages:
                return jsonify({"error": "No hay correos"}), 404

            message = messages[0]
            return jsonify({
                "id": message["id"],
                "from": message["from"]["emailAddress"]["address"],
                "subject": message["subject"],
                "snippet": message["bodyPreview"]
            })
        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500

    @app.route("/ultima-notificacion/notion", methods=["GET"])
    def obtener_ultima_notificacion_notion():

        email = request.args.get("email")

        try:
            user = get_user_from_db(email, cache, mongo)
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            notion_integration = user.get('integrations', {}).get('Notion', None)
            notion_token = notion_integration.get('token') if notion_integration else None

            if not notion_token:
                return jsonify({"error": "Token de Notion no disponible"}), 400

            headers = {
                "Authorization": f"Bearer {notion_token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json"
            }

            # 🔍 Buscar elementos ordenados por última edición
            payload = {
                "sort": {
                    "direction": "descending",
                    "timestamp": "last_edited_time"
                },
                "page_size": 5  # Buscamos más de 1 para poder filtrar
            }

            response = requests.post("https://api.notion.com/v1/search", headers=headers, json=payload)
            notion_data = response.json()

            if response.status_code != 200:
                return jsonify({"error": "Error al obtener notificaciones de Notion"}), response.status_code

            results = notion_data.get("results", [])
            if not results:
                return jsonify({"error": "No hay notificaciones"}), 404

            # ❌ Filtrar elementos archivados
            filtered_results = [
                item for item in results
                if not item.get("archived", False) and item.get("object") == "page"
            ]
            if not filtered_results:
                return jsonify({"error": "No hay notificaciones activas"}), 404

            # 📌 Tomar el más reciente después del filtro
            last_update = filtered_results[0]

            # 📝 Extraer título
            title_prop = last_update.get("properties", {}).get("title", {}).get("title", [])
            title = title_prop[0].get("text", {}).get("content", "(Sin título)") if title_prop else "(Sin título)"

            return jsonify({
                "from": "Notion",
                "subject": title,
                "snippet": f"Última edición: {last_update['last_edited_time']}",
                "id": last_update["id"]
            })

        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500
        
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

            # 1️⃣ Obtener la lista de DMs del usuario
            response = requests.get("https://slack.com/api/conversations.list?types=im", headers=headers)
            response_json = response.json()

            if not response_json.get("ok"):
                return jsonify({"error": "Error al obtener conversaciones", "details": response_json}), 400

            dms = response_json.get("channels", [])
            if not dms:
                return jsonify({"error": "No hay conversaciones directas"}), 404

            # 2️⃣ Ordenar DMs por el último mensaje recibido (latest)
            dms.sort(key=lambda x: x.get("latest", {}).get("ts", "0"), reverse=True)

            # 3️⃣ Tomar el canal más reciente y obtener mensajes
            for dm in dms:
                channel_id = dm["id"]

                history_response = requests.get(f"https://slack.com/api/conversations.history?channel={channel_id}&limit=1", headers=headers)
                history_json = history_response.json()

                if history_json.get("ok") and history_json.get("messages"):
                    message = history_json["messages"][0]  # Último mensaje en ese canal
                    return jsonify({
                        "id": message["ts"],
                        "name": "Slack",
                        "lastMessage": message["text"],
                        "from": f"Usuario {message['user']}",
                        "subject": "Mensaje de Slack",
                        "snippet": message["text"]
                    })

            return jsonify({"error": "No se encontraron mensajes"}), 404

        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500

    @app.route("/ultima-notificacion/onedrive", methods=["GET"])
    def obtener_ultimo_archivo_onedrive():
        email = request.args.get("email")
        try:
            # Buscar al usuario en la base de datos
            user = get_user_from_db(email, cache, mongo)
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            # Obtener el token de OneDrive
            token = user.get("integrations", {}).get("OneDrive", {}).get("token")
            if not token:
                return jsonify({"error": "Token no disponible"}), 400

            # Configurar los headers de la API de OneDrive
            headers = {
                "Authorization": f"Bearer {token}"
            }

            # Nueva URL para buscar archivos en TODO OneDrive
            url = "https://graph.microsoft.com/v1.0/me/drive/root/search(q='')"
            params = {
                "$orderby": "lastModifiedDateTime desc",
                "$top": "5",  # Obtener solo los más recientes
                "$select": "id,name,file,lastModifiedDateTime,parentReference"
            }
            response = requests.get(url, headers=headers, params=params)

            # Verificar que la respuesta fue exitosa
            if response.status_code != 200:
                return jsonify({"error": "Error al obtener archivos de OneDrive"}), response.status_code

            items = response.json().get('value', [])
            if not items:
                return jsonify({"error": "No hay archivos nuevos"}), 404

            # Filtrar solo archivos (descartar carpetas)
            archivos = [item for item in items if "file" in item]
            if not archivos:
                return jsonify({"error": "No hay archivos recientes"}), 404

            # Obtener el archivo más reciente
            last_file = archivos[0]

            return jsonify({
                "from": "OneDrive",
                "subject": f"Último archivo modificado: {last_file['name']}",
                "snippet": f"Archivo: {last_file['name']}",
                "id": last_file["id"],
                "modified_time": last_file.get("lastModifiedDateTime", "(Sin fecha de modificación)"),
                "file_path": last_file.get("parentReference", {}).get("path", "Desconocido")  # Ruta del archivo
            })

        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500


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

            headers = {"Authorization": f"Bearer {token.strip()}"}

            # 🔹 Obtener workspace_id
            workspaces_response = requests.get("https://app.asana.com/api/1.0/workspaces", headers=headers)
            workspaces_data = workspaces_response.json()

            if workspaces_response.status_code != 200:
                return jsonify({"error": "No se pudo obtener el workspace"}), workspaces_response.status_code

            workspaces = workspaces_data.get("data", [])
            if not workspaces:
                return jsonify({"error": "No hay workspaces disponibles"}), 404

            workspace_id = workspaces[0]["gid"]  # 🏢 Tomamos el primero

            # 🔹 Obtener user_id del usuario autenticado
            user_response = requests.get("https://app.asana.com/api/1.0/users/me", headers=headers)
            user_data = user_response.json()

            if user_response.status_code != 200:
                return jsonify({"error": "No se pudo obtener el usuario"}), user_response.status_code

            user_id = user_data.get("data", {}).get("gid")
            if not user_id:
                return jsonify({"error": "No se encontró el ID del usuario"}), 404

            # 🔍 Obtener tareas asignadas al usuario en el workspace
            response = requests.get(
                f"https://app.asana.com/api/1.0/tasks?assignee={user_id}&workspace={workspace_id}&limit=1",
                headers=headers
            )
            response_data = response.json()

            if response.status_code != 200:
                return jsonify({"error": "Error al obtener tareas", "details": response_data}), response.status_code

            tasks = response_data.get("data", [])
            if not tasks:
                return jsonify({"error": "No hay tareas asignadas"}), 404

            task = tasks[0]
            return jsonify({
                "from": "Asana",
                "subject": task.get("name", "(Sin título)"),
                "snippet": f"Tarea asignada: {task.get('name', '(Sin título)')}",
                "id": task["gid"],
            })

        except Exception as e:
            print("❌ Error inesperado:", str(e))
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500

    @app.route("/ultima-notificacion/dropbox", methods=["GET"])
    def obtener_ultimo_archivo_dropbox():
        email = request.args.get("email")
        try:
            # Buscar al usuario en la base de datos
            user = get_user_from_db(email, cache, mongo)
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            # Obtener el token de Dropbox
            token = user.get("integrations", {}).get("Dropbox", {}).get("token")
            if not token:
                return jsonify({"error": "Token no disponible"}), 400

            # Configuración de headers para la API de Dropbox
            headers = get_dropbox_headers(token)
            
            # Llamada a la API para obtener la lista de archivos y carpetas en Dropbox
            response = requests.post("https://api.dropboxapi.com/2/files/list_folder", headers=headers, json={"path": ""})

            if response.status_code != 200:
                return jsonify({"error": "Error al obtener archivos"}), response.status_code

            entries = response.json().get("entries", [])
            if not entries:
                return jsonify({"error": "No hay archivos o carpetas nuevos"})

            # Filtramos los archivos y las carpetas
            files_and_folders = []
            for entry in entries:
                if entry[".tag"] == "file":
                    files_and_folders.append({
                        "type": "file",
                        "name": entry["name"],
                        "path_display": entry["path_display"],
                        "client_modified": entry.get("client_modified", ""),
                        "id": entry["id"]
                    })
                elif entry[".tag"] == "folder":
                    files_and_folders.append({
                        "type": "folder",
                        "name": entry["name"],
                        "path_display": entry["path_display"],
                        "client_modified": entry.get("client_modified", ""),
                        "id": entry["id"]
                    })
            
            # Ordenamos los archivos y las carpetas por fecha de modificación (del más reciente al más antiguo)
            files_and_folders.sort(key=lambda x: x.get('client_modified', ''), reverse=True)

            # Obtenemos el más reciente (archivo o carpeta)
            last_entry = files_and_folders[0]

            # Construimos la respuesta según el tipo de la entrada (archivo o carpeta)
            if last_entry["type"] == "file":
                return jsonify({
                    "from": "Dropbox",  # Nombre fijo para Dropbox
                    "subject": f"Ultimo cambio detectado fue en la ruta {last_entry['path_display']} en el archivo llamado: {last_entry['name']}",
                    "snippet": f"Archivo: {last_entry['name']}",
                    "id": last_entry["id"],
                    "server_modified": last_entry.get("client_modified", "(Sin fecha de modificación)"),  # Fecha de modificación
                    "file_path": last_entry["path_display"]  # Carpeta donde se encuentra el archivo
                })
            else:
                return jsonify({
                    "from": "Dropbox",  # Nombre fijo para Dropbox
                    "subject": f"Ultimo cambio detectado fue en la ruta {last_entry['path_display']} en la carpeta llamada: {last_entry['name']}",
                    "snippet": f"Carpeta: {last_entry['name']}",
                    "id": last_entry["id"],
                    "server_modified": last_entry.get("client_modified", "(Sin fecha de modificación)"),  # Fecha de modificación
                    "file_path": last_entry["path_display"]  # Carpeta donde se encuentra la carpeta
                })

        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500

    def parse_hubspot_date(date_str):
        """Convierte una fecha ISO8601 de HubSpot a timestamp en milisegundos"""
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ")
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
            return int(dt.timestamp() * 1000)  # Convertir a milisegundos
        except Exception as e:
            print(f"Error al convertir fecha: {date_str} -> {str(e)}")
            return 0  # Retorna 0 si hay error

    @app.route('/ultima-notificacion/hubspot', methods=['GET'])
    def get_last_notification_hubspot():

        email = request.args.get("email")
        try:
            user = get_user_from_db(email, cache, mongo)
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            hubspot_integration = user.get('integrations', {}).get('HubSpot', None)
            if not hubspot_integration:
                return jsonify({"error": "Integración con HubSpot no configurada"}), 400

            hubspot_token = hubspot_integration.get('token', None)
            if not hubspot_token:
                return jsonify({"error": "Token de HubSpot no disponible"}), 400

            headers = get_hubspot_headers(hubspot_token)

            # URLs de búsqueda para contactos, negocios y empresas
            endpoints = {
                "contacto": "https://api.hubapi.com/crm/v3/objects/contacts/search",
                "negocio": "https://api.hubapi.com/crm/v3/objects/deals/search",
                "empresa": "https://api.hubapi.com/crm/v3/objects/companies/search"
            }

            search_data = {
                "filterGroups": [
                    {
                        "filters": [
                            {
                                "propertyName": "hs_lastmodifieddate",
                                "operator": "GT",
                                "value": "0"
                            }
                        ]
                    }
                ],
                "properties": ["hs_lastmodifieddate","dealname", "firstname", "lastname", "email", "hubspot_owner_id", "name"],
                "limit": 1,
                "sorts": ["-hs_lastmodifieddate"]
            }

            latest_update = None

            for entity, url in endpoints.items():
                try:
                    response = requests.post(url, headers=headers, json=search_data)
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("results"):
                            result = data["results"][0]
                            last_modified_str = result["properties"].get("hs_lastmodifieddate", "0")

                            # Convertir la fecha a timestamp en milisegundos
                            last_modified = parse_hubspot_date(last_modified_str) if isinstance(last_modified_str, str) else int(last_modified_str)

                            if latest_update is None or last_modified > latest_update["timestamp"]:
                                latest_update = {
                                    "type": entity,
                                    "data": result,
                                    "timestamp": last_modified
                                }
                    else:
                        print(f"Error al obtener {entity}: {response.status_code} - {response.text}")
                except Exception as e:
                    print(f"Error en la consulta de {entity}: {str(e)}")

            if not latest_update:
                return jsonify({"message": "No se encontraron cambios recientes."}), 404

            # Formatear respuesta
            update_data = latest_update["data"]
            entity_type = latest_update["type"]
            properties = update_data["properties"]

            if entity_type == "contacto":
                subject = f"{properties.get('firstname', '')} {properties.get('lastname', '')}".strip()
                snippet = f"Nuevo contacto: {properties.get('email', '(sin email)')}"
            elif entity_type == "negocio":
                subject = properties.get("dealname", "(Sin nombre)")
                snippet = f"Nuevo negocio detectado."
            elif entity_type == "empresa":
                subject = properties.get("name", "(Sin nombre)")
                snippet = f"Nuevo cambio en la empresa."

            notification_data = {
                "from": "HubSpot",
                "type": entity_type,
                "subject": subject if subject else "(Sin título)",
                "snippet": snippet,
                "id": update_data.get("id", "N/A"),
                "last_modified": datetime.fromtimestamp(latest_update["timestamp"] / 1000).isoformat()
            }
            return jsonify(notification_data)
        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500
        

    def convertir_fecha(timestamp):
        if timestamp:
            return datetime.utcfromtimestamp(int(timestamp) / 1000).strftime('%Y-%m-%d %H:%M:%S')
        return "No definida"

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

            teams = response.json().get("teams", [])
            if not teams:
                return jsonify({"error": "No hay equipos en ClickUp"})

            team_id = teams[0]["id"]
            response = requests.get(f"https://api.clickup.com/api/v2/team/{team_id}/task", headers=headers)

            tasks = response.json().get("tasks", [])
            if not tasks:
                return jsonify({"error": "No hay tareas nuevas"})

            task = tasks[0]
            due_date = convertir_fecha(task.get("due_date"))

            return jsonify({
                "id": task["id"],
                "name": task["name"],
                "status": task["status"]["status"],
                "due_date": due_date,
                "from": "ClickUp",  # ✅ Para que no falle en el frontend
                "subject": task["name"],  # ✅ Adaptación para React
                "snippet": f"Estado: {task['status']['status']}, Fecha límite: {due_date}"
            })
        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500

    @app.route("/ultima-notificacion/drive", methods=["GET"])
    def obtener_ultimo_archivo_drive():
        email = request.args.get("email")
        try:
            # Buscar al usuario en la base de datos
            user = get_user_from_db(email, cache, mongo)
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            # Obtener el token de Google Drive
            token = user.get("integrations", {}).get("Drive", {}).get("token")
            if not token:
                return jsonify({"error": "Token no disponible"}), 400

            # Configurar los headers de la API de Google Drive
            headers = {
                "Authorization": f"Bearer {token}"
            }

            # Realizar la solicitud a la API de Google Drive para listar los archivos
            url = "https://www.googleapis.com/drive/v3/files"
            params = {
                "pageSize": 10,  # Obtener los primeros 10 archivos
                "fields": "files(id, name, mimeType, modifiedTime, parents)",
                "orderBy": "modifiedTime desc"  # Ordenar por la fecha de modificación
            }
            response = requests.get(url, headers=headers, params=params)

            # Verificar que la respuesta fue exitosa
            if response.status_code != 200:
                return jsonify({"error": "Error al obtener archivos de Google Drive"}), response.status_code

            files = response.json().get('files', [])
            if not files:
                return jsonify({"error": "No hay archivos o carpetas nuevos"}), 404

            # Obtener el archivo o carpeta más reciente
            last_entry = files[0]

            # Clasificar si es un archivo o una carpeta
            if last_entry["mimeType"] == "application/vnd.google-apps.folder":
                entry_type = "folder"
            else:
                entry_type = "file"

            # Crear la respuesta según el tipo (archivo o carpeta)
            if entry_type == "file":
                return jsonify({
                    "from": "Google Drive",
                    "subject": f"Último cambio detectado fue en el archivo llamado: {last_entry['name']}",
                    "snippet": f"Archivo: {last_entry['name']}",
                    "id": last_entry["id"],
                    "modified_time": last_entry.get("modifiedTime", "(Sin fecha de modificación)"),
                    "file_path": last_entry.get("parents", ["Desconocido"])  # Carpeta donde se encuentra el archivo
                })
            else:
                return jsonify({
                    "from": "Google Drive",
                    "subject": f"Último cambio detectado fue en la carpeta llamada: {last_entry['name']} en la ruta {last_entry.get('parents', 'Desconocida')}",
                    "snippet": f"Carpeta: {last_entry['name']}",
                    "id": last_entry["id"],
                    "modified_time": last_entry.get("modifiedTime", "(Sin fecha de modificación)"),
                    "file_path": last_entry.get("parents", ["Desconocido"])  # Carpeta donde se encuentra la carpeta
                })

        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500

    @app.route("/ultima-notificacion/teams", methods=["GET"])
    def obtener_ultimo_mensaje_teams():
        email = request.args.get("email")
        try:
            user = get_user_from_db(email, cache, mongo)
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            token = user.get("integrations", {}).get("Teams", {}).get("token")
            if not token:
                return jsonify({"error": "Token no disponible"}), 400

            headers = get_teams_headers(token)
            response = requests.get("https://graph.microsoft.com/v1.0/me/chats?$top=1", headers=headers)

            if response.status_code != 200:
                return jsonify({"error": "Error al obtener mensajes"}), response.status_code

            chats = response.json().get("value", [])
            if not chats:
                return jsonify({"error": "No hay mensajes recientes"})

            chat = chats[0]
            return jsonify({
                "id": chat["id"],
                "last_message_preview": chat["lastMessagePreview"]["body"]["content"]
            })
        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500
        
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
