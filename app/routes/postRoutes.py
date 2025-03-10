from flask import request, jsonify
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from config import Config
from datetime import datetime
import re
import json
import openai
openai.api_key=Config.CHAT_API_KEY

def setup_post_routes(app,mongo):
    def get_clickup_headers(token):
        return {
            "Authorization": token,
            "Content-Type": "application/json"
    }

    def post_to_gmail(query):
        """Procesa la consulta y ejecuta la acción en Gmail API o Google Calendar si aplica."""
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        gmail_token = user.get('integrations', {}).get('Gmail', {}).get('token')
        if not gmail_token:
            return jsonify({"error": "Token de Gmail no disponible"}), 400

        match = re.search(r'todos los correos de (.+)', query, re.IGNORECASE)
        if match:
            sender = match.group(1)
            # Determinar la acción: "delete" para eliminar, "spam" para mover a spam.
            action = "delete" if "eliminar" in query.lower() else "spam" if "mover a spam" in query.lower() else None

            if not action:
                return {"error": "Acción no reconocida para Gmail"}

            headers = {"Authorization": f"Bearer {gmail_token}", "Content-Type": "application/json"}
            
            if action == "delete":
                # Primero, buscamos los mensajes del remitente especificado
                list_url = "https://www.googleapis.com/gmail/v1/users/me/messages"
                params = {"q": f"from:{sender}"}
                list_response = requests.get(list_url, headers=headers, params=params)
                messages = list_response.json().get("messages", [])
                
                if not messages:
                    return {"error": f"No se encontraron correos del remitente {sender}"}
                
                delete_results = []
                # Para cada mensaje, movemos a la papelera
                for msg in messages:
                    message_id = msg["id"]
                    delete_url = f"https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}/trash"
                    delete_response = requests.post(delete_url, headers=headers)
                    delete_results.append(delete_response.json())
                
                if delete_results:
                    return {"message": f"Se han eliminado {len(delete_results)} correos del remitente {sender} 🧹✉️🚮"}
            
            elif action == "spam":
                # Primero, buscamos los mensajes del remitente especificado
                list_url = "https://www.googleapis.com/gmail/v1/users/me/messages"
                params = {"q": f"from:{sender}"}
                list_response = requests.get(list_url, headers=headers, params=params)
                messages = list_response.json().get("messages", [])
                
                if not messages:
                    return {"error": f"No se encontraron correos del remitente {sender}"}
                
                spam_results = []
                # Para cada mensaje, modificamos las etiquetas para agregar "SPAM"
                for msg in messages:
                    message_id = msg["id"]
                    modify_url = f"https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}/modify"
                    modify_payload = {"addLabelIds": ["SPAM"]}
                    modify_response = requests.post(modify_url, headers=headers, json=modify_payload)
                    spam_results.append(modify_response.json())
                
                if spam_results:
                    return {"message": f"Se han movido {len(spam_results)} correos del remitente {sender} a spam 🚫📩🛑"}
        if "agendar" or "agendame" in query:
            prompt = f"El usuario dijo: '{query}'. Devuelve un JSON con los campos 'date', 'time' y 'subject' que representen la fecha, hora y asunto de la cita agendada (el asunto ponlo con inicial mayuscula en la primer palabra) .Si no se puede extraer la información, devuelve 'unknown'."
        
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
                    return {"error": "No se pudo interpretar la consulta."}

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
                    return {"error": "Mes no válido en la consulta"}

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
                headers = {"Authorization": f"Bearer {gmail_token}", "Content-Type": "application/json"}
                response = requests.post(url, json=event, headers=headers)
                return {"message": f"¡Tu cita ha sido agendada con éxito! 📅🕒\n\nDetalles:\n- Asunto: {subject}\n- Fecha y hora de inicio: {event['start']['dateTime']}\n- Fecha y hora de fin: {event['end']['dateTime']}\n\n¡Nos vemos pronto! 😊"}
            except Exception as e:
                print(f"Error al procesar la respuesta: {e}")
        return {"error": "No se encontró una acción válida en la consulta"}

    def post_to_outlook(query):
        """Procesa la consulta y ejecuta la acción en Outlook API."""
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        outlook_token = user.get('integrations', {}).get('Outlook', {}).get('token')
        if not outlook_token:
            return jsonify({"error": "Token de Outlook no disponible"}), 400

        match = re.search(r'todos los correos de (.+)', query, re.IGNORECASE)
        if match:
            sender = match.group(1)
            action = "delete" if "eliminar" in query else "spam" if "mover a spam" in query else None

            if not action:
                return {"error": "Acción no reconocida para Outlook"}

            url = "https://graph.microsoft.com/v1.0/me/messages"
            headers = {"Authorization": f"Bearer {outlook_token}", "Content-Type": "application/json"}
            
            # Primero, obtener todos los mensajes del remitente especificado
            params = {"$filter": f"from/emailAddress/address eq '{sender}'"}
            list_response = requests.get(url, headers=headers, params=params)
            messages = list_response.json().get("value", [])

            if not messages:
                return {"error": f"No se encontraron correos del remitente {sender}"}
            
            results = []

            for msg in messages:
                message_id = msg["id"]
                if action == "delete":
                    # Eliminar el correo
                    delete_url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/move"
                    response = requests.post(delete_url, headers=headers, json={"destinationId": "deleteditems"})
                    results.append(response.json())
                
                elif action == "spam":
                    # Mover el correo a la carpeta de "Junk Email"
                    move_url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/move"
                    response = requests.post(move_url, headers=headers, json={"destinationId": "JunkEmail"})
                    results.append(response.json())

            if results:
                if action == "delete":
                    return jsonify({"message": f"Se han eliminado {len(results)} correos del remitente {sender}"})
                elif action == "spam":
                    return jsonify({"message": f"Se han movido {len(results)} correos del remitente {sender} a spam"})
            else:
                return {"error": "No se pudo realizar la acción"}

        return {"error": "No se encontró un remitente válido en la consulta"}
    
    def get_task_id_clickup(name, token):
        headers = get_clickup_headers(token)
        
        # Obtener el equipo
        response = requests.get("https://api.clickup.com/api/v2/team", headers=headers)
        if response.status_code != 200:
            return {"error": "Error al obtener equipos de ClickUp"}, response.status_code
        
        teams = response.json().get("teams", [])
        if not teams:
            return {"error": "No hay equipos en ClickUp"}

        # Seleccionar el primer equipo (puedes personalizar esto si tienes múltiples equipos)
        team_id = teams[0]["id"]

        # Obtener las tareas del equipo
        response = requests.get(f"https://api.clickup.com/api/v2/team/{team_id}/task", headers=headers)
        if response.status_code != 200:
            return {"error": "Error al obtener tareas del equipo"}, response.status_code
        
        tasks = response.json().get("tasks", [])
        if not tasks:
            return {"error": "No hay tareas disponibles en el equipo"}
        
        # Buscar la tarea que coincida con el nombre proporcionado
        for task in tasks:
            if task["name"].lower() == name.lower():
                return task["id"]  # Retorna el ID de la tarea si coincide el nombre

        return {"error": f"No se encontró la tarea con el nombre {name}"}

    def get_task_id_asana(name, token):
        url = "https://app.asana.com/api/1.0/tasks"
        headers = {"Authorization": f"Bearer {token}"}
        params = {"name": name}  # Asumiendo que Asana permite buscar tareas por nombre (verificar en la API de Asana)

        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            tasks = response.json().get('data', [])
            if tasks:
                return tasks[0]["gid"]  # Asana usa "gid" como el identificador de la tarea
        return None

    def get_task_id_notion(name, token):
        url = "https://api.notion.com/v1/databases/YOUR_DATABASE_ID/query"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        data = {
            "filter": {
                "property": "Name",  # Asegúrate de que "Name" es el nombre correcto de la propiedad en tu base de datos
                "rich_text": {
                    "equals": name
                }
            }
        }
        
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            results = response.json().get('results', [])
            if results:
                return results[0]["id"]  # Notion utiliza el "id" de cada página
        return None

    def post_to_notion(query):
        """Procesa la consulta y ejecuta la acción en la API de Notion."""
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        notion_token = user.get('integrations', {}).get('Notion', {}).get('token')
        if not notion_token:
            return jsonify({"error": "Token de Notion no disponible"}), 400

        match = re.search(r'marca como completada la tarea (.+)', query, re.IGNORECASE)
        if match:
            task_name = match.group(1)

            task_id = get_task_id_notion(task_name, notion_token)
            if not task_id:
                return {"error": f"No se encontró la tarea {task_name} en Notion"}

            url = f"https://api.notion.com/v1/pages/{task_id}"
            headers = {
                "Authorization": f"Bearer {notion_token}",
                "Content-Type": "application/json",
                "Notion-Version": "2021-05-13"
            }

            # Marcar la tarea como completada
            data = {
                "properties": {
                    "Status": {
                        "select": {
                            "name": "Completed"  # Asume que "Completed" es el estado de completado
                        }
                    }
                }
            }
            response = requests.patch(url, headers=headers, json=data)
            if response.status_code == 200:
                return jsonify({"message": f"Tarea {task_name} completada correctamente"})
            else:
                return jsonify({"error": "No se pudo completar la tarea"}), 400

        return {"error": "No se encontró una tarea válida en la consulta"}

    def post_to_clickup(query):
        """Procesa la consulta y ejecuta la acción en la API de ClickUp."""
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        clickup_token = user.get('integrations', {}).get('ClickUp', {}).get('token')
        if not clickup_token:
            return jsonify({"error": "Token de ClickUp no disponible"}), 400

        match = re.search(r'(marca como completada|cambia el estado a|elimina) la tarea (.+)', query, re.IGNORECASE)
        if match:
            action = match.group(1).lower()
            task_name = match.group(2)
            
            # Obtener el ID de la tarea
            task_id = get_task_id_clickup(task_name, clickup_token)
            if not task_id:
                return jsonify({"error": f"No se encontró la tarea {task_name} en ClickUp"}), 404

            url = f"https://api.clickup.com/api/v2/task/{task_id}"
            headers = {
                "Authorization": f"Bearer {clickup_token}",
                "Content-Type": "application/json"
            }

            # Acción según la consulta
            if "completada" in action:
                data = {"status": "complete"}  # Asume que "complete" es el estado para tarea completada
                response = requests.put(url, headers=headers, json=data)
                if response.status_code == 200:
                    return jsonify({"message": f"Tarea {task_name} completada correctamente"})
                else:
                    return jsonify({"error": "No se pudo completar la tarea"}), 400
            
            elif "cambia el estado" in action:
                # Extraer el nuevo estado del query
                new_status_match = re.search(r'cambia el estado a (.+)', query, re.IGNORECASE)
                if new_status_match:
                    new_status = new_status_match.group(1)
                    data = {"status": new_status}
                    response = requests.put(url, headers=headers, json=data)
                    if response.status_code == 200:
                        return jsonify({"message": f"Estado de la tarea {task_name} cambiado a {new_status}"})
                    else:
                        return jsonify({"error": "No se pudo cambiar el estado de la tarea"}), 400
                else:
                    return jsonify({"error": "No se proporcionó un nuevo estado"}), 400

            elif "elimina" in action:
                # Eliminar la tarea
                response = requests.delete(f"https://api.clickup.com/api/v2/task/{task_id}", headers=headers)
                if response.status_code == 204:  # El código 204 indica que la tarea se eliminó exitosamente
                    return jsonify({"message": f"Tarea {task_name} eliminada correctamente"})
                else:
                    return jsonify({"error": "No se pudo eliminar la tarea"}), 400

            return jsonify({"error": "Acción no reconocida para ClickUp"}), 400

        return jsonify({"error": "No se encontró una tarea válida en la consulta"}), 400


    def post_to_asana(query):
        """Procesa la consulta y ejecuta la acción en la API de Asana."""
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        asana_token = user.get('integrations', {}).get('Asana', {}).get('token')
        if not asana_token:
            return jsonify({"error": "Token de Asana no disponible"}), 400

        match = re.search(r'marca como completada la tarea (.+)', query, re.IGNORECASE)
        if match:
            task_name = match.group(1)

            task_id = get_task_id_asana(task_name, asana_token)
            if not task_id:
                return {"error": f"No se encontró la tarea {task_name} en Asana"}

            url = f"https://app.asana.com/api/1.0/tasks/{task_id}"
            headers = {
                "Authorization": f"Bearer {asana_token}",
                "Content-Type": "application/json"
            }

            data = {"data": {"completed": True}}
            response = requests.put(url, headers=headers, json=data)
            if response.status_code == 200:
                return jsonify({"message": f"Tarea {task_name} completada correctamente"})
            else:
                return jsonify({"error": "No se pudo completar la tarea"}), 400

        return {"error": "No se encontró una tarea válida en la consulta"}
        
    def post_to_dropbox(query):
        """Procesa la consulta y ejecuta la acción en la API de Dropbox."""
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400
        user = mongo.database.usuarios.find_one({"correo": email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404
        dropbox_token = user.get("integrations", {}).get("Dropbox", {}).get("token")
        if not dropbox_token:
            return jsonify({"error": "Token de Dropbox no disponible"}), 400
        
        match = re.search(r'archivo:(.+?) en carpeta:(.+)', query, re.IGNORECASE)
        print("Match encontrado dropbox:", match, ",")
        if match:
            file_name = match.group(1).strip()
            folder_name = match.group(2).strip()
            
            url = "https://api.dropboxapi.com/2/files/search_v2"
            headers = {
                'Authorization': f"Bearer {dropbox_token}",
                'Content-Type': 'application/json'
            }
            params = {
                "query": file_name,
                "options": {
                    "max_results": 10,
                    "file_status": "active"
                }
            }
            response = requests.post(url, headers=headers, json=params)
            response.raise_for_status()
            results = response.json().get('matches', [])

            file_path = None
            for result in results:
                dropbox_file_name = result['metadata']['metadata']['name']
                dropbox_file_path = result['metadata']['metadata']['path_lower']
                print(dropbox_file_name)
                print(dropbox_file_path)
                
                if dropbox_file_name.lower().startswith(file_name.lower()):
                    file_path = dropbox_file_path
                    break
            
            if not file_path:
                return jsonify({"error": f"Archivo '{file_name}' no encontrado en Dropbox"}), 404
            
            folder_path = f"/{folder_name}/{dropbox_file_name}"

            headers = {
                "Authorization": f"Bearer {dropbox_token}",
                "Content-Type": "application/json"
            }

            data = {
                "from_path": file_path,
                "to_path": folder_path,
                "allow_ownership_transfer": False,
                "allow_shared_folder": True,
                "autorename": False,
            }

            url = "https://api.dropboxapi.com/2/files/move_v2"
            response = requests.post(url, headers=headers, json=data)
            return {"message": f"🎉 El archivo '{dropbox_file_name}' ha sido movido a la carpeta '{folder_name}' con éxito! 🚀"}    

        return jsonify({"error": "Formato de consulta inválido"}), 400

    def post_to_googledrive(query):
        print("HOLA ESTOY ENTRANDO AL METODO POST_TO_GOOGLEDRIVE")
        print("ESTA ES LA QUERY:", query)

        """Procesa la consulta y ejecuta la acción en la API de Google Drive."""
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400
        user = mongo.database.usuarios.find_one({"correo": email})

        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404
        
        google_drive_token = user.get('integrations', {}).get('Drive', {}).get('token')
        print("Token de Google Drive:", google_drive_token)
        if not google_drive_token:
            return jsonify({"error": "Token de Google Drive no disponible."}), 400
        
        match = re.search(r"(?:mover\s+)?archivo:\s*([\w\s\d\.-]+?)\s+(?:a|en)\s+carpeta:\s*([\w\s\d\.-]+)", query, re.IGNORECASE)
        print("Match encontrado drive:", match)

        if match:
            file_name = match.group(1).strip()  # Nombre del archivo
            folder_name = match.group(2).strip()  # Nombre de la carpeta
            print(f"Archivo: {file_name}, Carpeta destino: {folder_name}")
            
            try:
                # Buscar el archivo por nombre
                file_id = get_file_id_by_name(google_drive_token, file_name)
                print("Archivo encontrado:", file_id)
                if not file_id:
                    return jsonify({"error": f"Archivo '{file_name}' no encontrado en Google Drive."}), 404
                
                # Buscar la carpeta por nombre
                folder_id = get_folder_id_by_name(google_drive_token, folder_name)
                print("Carpeta encontrada:", folder_id)
                if not folder_id:
                    return jsonify({"error": f"Carpeta '{folder_name}' no encontrada en Google Drive."}), 404
                
                # Mover el archivo a la nueva carpeta
                move_file_to_folder(google_drive_token, file_id, folder_id)
                
                return jsonify({"message": f"Archivo '{file_name}' movido exitosamente a la carpeta '{folder_name}'."}), 200
            
            except Exception as e:
                return jsonify({"error": f"Error al procesar la solicitud: {str(e)}"}), 500
        
        else:
            return jsonify({"error": "No se encontró una acción válida en la consulta."}), 400

    def get_file_id_by_name(token, file_name):
        url = "https://www.googleapis.com/drive/v3/files"
        headers = {
            "Authorization": f"Bearer {token}"
        }
        params = {
            "q": f"name contains '{file_name.strip()}' and trashed = false",
            "fields": "files(id, name, parents)"
        }
        response = requests.get(url, headers=headers, params=params)
        print("Respuesta completa de Google Drive:", response.json())  # 🔍 Imprime todos los archivos encontrados
        
        if response.status_code == 200:
            files = response.json().get("files", [])
            for f in files:
                print(f"Archivo disponible: {f['name']} - ID: {f['id']} - Carpeta padre: {f.get('parents', 'Sin carpeta')}")

            # Buscar el archivo ignorando diferencias de mayúsculas y espacios
            file_name_clean = file_name.strip().lower()
            return next((f['id'] for f in files if f['name'].strip().lower() == file_name_clean), None)
        
        return None


    def get_folder_id_by_name(token, folder_name):
        """Obtiene el ID de una carpeta por su nombre usando la API de Google Drive."""
        url = "https://www.googleapis.com/drive/v3/files"
        headers = {
            "Authorization": f"Bearer {token}"
        }
        params = {
            "q": f"mimeType = 'application/vnd.google-apps.folder' and name = '{folder_name}'",
            "fields": "files(id)"
        }
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            folders = response.json().get("files", [])
            if folders:
                return folders[0]['id']  # Retorna la primera carpeta que coincida con el nombre
        return None

    def move_file_to_folder(token, file_id, folder_id):
        """Mueve el archivo a la carpeta especificada en Google Drive y lo elimina de su ubicación anterior."""

        # 1️⃣ Obtener las carpetas actuales del archivo
        url_get = f"https://www.googleapis.com/drive/v3/files/{file_id}?fields=parents"
        headers = {"Authorization": f"Bearer {token}"}
        
        response_get = requests.get(url_get, headers=headers)

        if response_get.status_code == 200:
            current_parents = response_get.json().get("parents", [])
            if not current_parents:
                raise Exception(f"El archivo {file_id} no tiene carpetas padre.")
            current_parents_str = ",".join(current_parents)  # Convertir a string separado por comas
        else:
            raise Exception(f"Error al obtener la carpeta actual: {response_get.text}")

        # 2️⃣ Mover el archivo a la nueva carpeta (removiendo la anterior)
        url_patch = f"https://www.googleapis.com/drive/v3/files/{file_id}"

        params = {
            "addParents": folder_id,
            "removeParents": current_parents_str,  # 💡 Remueve TODAS las carpetas anteriores
            "fields": "id, parents"
        }

        response_patch = requests.patch(url_patch, headers=headers, params=params)  # 🚨 Aquí pasamos los datos en `params`, no en `json`

        if response_patch.status_code == 200:
            print(f"✅ Archivo {file_id} movido correctamente a la carpeta {folder_id}.")
        else:
            raise Exception(f"⚠️ Error al mover archivo: {response_patch.text}")

    def post_to_onedrive(query):
        print("Entrando a OneDrive")
        print("query onedrive:", query)

        # Obtener email del usuario
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400

        # Buscar usuario en la base de datos
        user = mongo.database.usuarios.find_one({"correo": email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        # Obtener el token de OneDrive
        OneDrive_token = user.get('integrations', {}).get('OneDrive', {}).get('token')
        if not OneDrive_token:
            return jsonify({"error": "Token de OneDrive no disponible"}), 400

        # ==================================================
        #   🗑 Mover archivos a la papelera en OneDrive 🗑
        # ==================================================

        matchEliminar = re.search(r'eliminar\s*(archivo)?[:\s]*([\w\.\-_]+)', query, re.IGNORECASE)
        print("matchEliminar OneDrive:", matchEliminar)

        if matchEliminar:
            file_name = matchEliminar.group(2).strip()
            print("file_name:", file_name)

            # Buscar archivo en OneDrive
            search_url = f"https://graph.microsoft.com/v1.0/me/drive/root/search(q='{file_name}')"
            headers = {
                'Authorization': f"Bearer {OneDrive_token}",
                'Content-Type': 'application/json'
            }

            response = requests.get(search_url, headers=headers)
            print(response)
            if response.status_code == 401:
                return jsonify({"error": "No autorizado. Verifica el token de acceso."}), 401

            response.raise_for_status()
            results = response.json().get('value', [])

            file_id = None
            for result in results:
                OneDrive_file_name = result['name']
                OneDrive_file_id = result['id']
                
                if OneDrive_file_name.lower().startswith(file_name.lower()):
                    file_id = OneDrive_file_id
                    break

            if not file_id:
                return jsonify({"error": f"Archivo '{file_name}' no encontrado en OneDrive"}), 404

            # Mover el archivo a la papelera (Enviar a "Recycle Bin" en OneDrive)
            move_to_trash_url = f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}"
            delete_response = requests.delete(move_to_trash_url, headers=headers)
            
            if delete_response.status_code == 401:
                return jsonify({"error": "No autorizado. Verifica el token de acceso."}), 401

            delete_response.raise_for_status()

            return jsonify({"message": f"🗑 El archivo '{file_name}' ha sido movido a la papelera en OneDrive con éxito!"})

        return jsonify({"error": "Formato de consulta inválido"}), 400


    return {
        "post_to_gmail" : post_to_gmail,
        "post_to_notion" : post_to_notion,
        "post_to_clickup" : post_to_clickup,
        "post_to_asana" : post_to_asana,
        "post_to_outlook" : post_to_outlook,
        "post_to_dropbox" : post_to_dropbox,
        "post_to_googledrive" : post_to_googledrive,
        "post_to_onedrive": post_to_onedrive,
    }
