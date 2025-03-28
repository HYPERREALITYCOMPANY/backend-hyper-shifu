from flask import request, jsonify
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from config import Config
import re
import json
import openai
from app.utils.utils import get_user_from_db
from flask_caching import Cache


def setup_execute_routes(app,mongo, cache, refresh_functions):
    cache = Cache(app)
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
                
    @app.route('/execute/gmail', methods=['GET'])
    def execute_gmail_rules():
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400

        user = get_user_with_refreshed_tokens(email)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        gmail_token = user.get('integrations', {}).get('Gmail', {}).get('token')
        if not gmail_token:
            return jsonify({"error": "Token de Gmail no disponible"}), 400

        rules = [rule for rule in user.get('automatizaciones', []) if rule.get("service") == "Gmail" and rule.get("active")]
        executed_rules = []
        results = []

        for rule in rules:
            condition = rule.get("condition", "").lower().strip()
            action = rule.get("action", "").lower().strip()

            condition_match = re.search(r"de\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z0-9]{2,})", condition)
            expected_sender = condition_match.group(1).lower().strip() if condition_match else None
            if not expected_sender:
                company_match = re.search(r"de\s+(.+)", condition)
                expected_sender = company_match.group(1).lower().strip() if company_match else None

            if expected_sender:
                try:
                    url = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
                    headers = {"Authorization": f"Bearer {gmail_token}"}
                    params = {"q": f"from:{expected_sender}"}
                    
                    response = requests.get(url, headers=headers, params=params)
                    if response.status_code == 200:
                        messages = response.json().get('messages', [])
                        if messages:
                            for message in messages:
                                message_id = message['id']
                                if action in ["borrar", "eliminar"]:
                                    delete_url = f"https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}/trash"
                                    delete_response = requests.post(delete_url, headers=headers)
                                    if delete_response.status_code == 204:
                                        results.append(f"Mensaje {message_id}: Eliminado con éxito")
                                    else:
                                        results.append(f"Mensaje {message_id}: Error al eliminar - {delete_response.text}")
                                elif action == "mover a spam":
                                    modify_url = f"https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}/modify"
                                    modify_payload = {"addLabelIds": ["SPAM"]}
                                    modify_response = requests.post(modify_url, headers=headers, json=modify_payload)
                                    if modify_response.status_code == 200:
                                        results.append(f"Mensaje {message_id}: Movido a spam")
                                    else:
                                        results.append(f"Mensaje {message_id}: Error al mover a spam - {modify_response.text}")
                                elif action == "responder":
                                    reply_url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
                                    reply_body = {
                                        "raw": create_message(expected_sender, "Gracias por tu correo, responderé pronto.")
                                    }
                                    reply_response = requests.post(reply_url, headers=headers, json=reply_body)
                                    if reply_response.status_code == 200:
                                        results.append(f"Mensaje {message_id}: Respondido con éxito")
                                    else:
                                        results.append(f"Mensaje {message_id}: Error al responder - {reply_response.text}")

                            # Actualizar la última ejecución de la regla
                            mongo.database.usuarios.update_one(
                                {"_id": user["_id"], "automatizaciones.condition": condition},
                                {"$set": {"automatizaciones.$.last_executed": datetime.utcnow()}}
                            )
                            executed_rules.append(rule)
                        else:
                            results.append(f"No se encontraron correos de {expected_sender}")
                    else:
                        results.append(f"Error al obtener correos: {response.text}")

                except requests.exceptions.RequestException as error:
                    return jsonify({"error": f"Error en la petición a la API de Gmail: {str(error)}"}), 500

        if executed_rules:
            return jsonify({"message": "Ejecución completada", "results": results, "executed_rules": executed_rules})
        return jsonify({"message": "No se ejecutaron reglas", "results": results}), 200

    def create_message(to, body):
        """ Crea un mensaje MIME para enviar una respuesta en Gmail (en formato base64) """
        from email.mime.text import MIMEText
        import base64

        # Crear el cuerpo del mensaje en formato MIME
        message = MIMEText(body)
        message['to'] = to
        message['subject'] = "Respuesta automática"
        
        # Codificar el mensaje en base64
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        return raw_message
    
    @app.route('/execute/outlook', methods=['GET'])
    def execute_outlook_rules():
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400

        # Buscar el usuario en la base de datos
        user = get_user_with_refreshed_tokens(email)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        # Obtener el token actualizado
        outlook_token = user.get('integrations', {}).get('Outlook', {}).get('token')
        if not outlook_token:
            return jsonify({"error": "Token de Outlook no disponible"}), 400

        rules = [rule for rule in user.get('automatizaciones', []) if rule.get("service") == "Outlook" and rule.get("active")]

        executed_rules = []
        for rule in rules:
            condition = rule.get("condition", "").lower().strip()
            action = rule.get("action", "").lower().strip()

            # Extraer el remitente de la condición
            condition_match = re.search(r"de\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z0-9]{2,})", condition)
            if condition_match:
                expected_sender = condition_match.group(1).lower().strip()
                print(f"Outlook: Regla con remitente específico '{expected_sender}'")
            else:
                company_match = re.search(r"de\s+(.+)", condition)
                if company_match:
                    expected_sender = company_match.group(1).lower().strip()
                    print(f"Outlook: Buscando correos de remitentes que contengan '{expected_sender}'")
                else:
                    print(f"Outlook: No se pudo extraer un remitente válido de la condición: {condition}")
                    expected_sender = None

            if expected_sender:
                try:
                    url = "https://graph.microsoft.com/v1.0/me/messages"
                    headers = {"Authorization": f"Bearer {outlook_token}"}
                    params = {"$filter": f"from/emailAddress/address eq '{expected_sender}'"}
                    
                    response = requests.get(url, headers=headers, params=params)
                    if response.status_code == 200:
                        messages = response.json().get('value', [])
                        if messages:
                            for message in messages:
                                message_id = message['id']
                                if action == "borrar":
                                    delete_url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}"
                                    delete_response = requests.delete(delete_url, headers=headers)
                                    if delete_response.status_code == 204:
                                        print(f"Outlook: Correo eliminado con éxito.")
                                    else:
                                        print(f"Outlook: Error al eliminar el correo: {delete_response.text}")
                                elif action == "mover a spam":
                                    move_url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/move"
                                    move_payload = {"destinationId": "junkemail"}
                                    move_response = requests.post(move_url, headers=headers, json=move_payload)
                                    if move_response.status_code == 200:
                                        print(f"Outlook: Correo movido a spam.")
                                    else:
                                        print(f"Outlook: Error al mover a spam: {move_response.text}")
                                elif action == "responder":
                                    reply_url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/reply"
                                    reply_payload = {"comment": "Gracias por tu correo, responderé pronto."}
                                    reply_response = requests.post(reply_url, headers=headers, json=reply_payload)
                                    if reply_response.status_code == 202:
                                        print(f"Outlook: Correo respondido con éxito.")
                                    else:
                                        print(f"Outlook: Error al enviar respuesta: {reply_response.text}")

                            # Actualizar la última ejecución de la regla
                            mongo.database.usuarios.update_one(
                                {"_id": user["_id"], "automatizaciones.condition": condition},
                                {"$set": {"automatizaciones.$.last_executed": datetime.utcnow()}}
                            )
                            executed_rules.append(rule)
                        else:
                            print(f"Outlook: No se encontraron correos de {expected_sender}.")
                    else:
                        print(f"Outlook: Error al obtener correos: {response.text}")

                except requests.exceptions.RequestException as error:
                    return jsonify({"error": f"Error en la petición a la API de Outlook: {str(error)}"}), 500

        if executed_rules:
            return jsonify({"message": "Ejecución de reglas de Outlook completada.", "executed_rules": executed_rules})
        else:
            return jsonify({"message": "No se ejecutaron reglas de Outlook."}), 200
        
    @app.route('/execute/notion', methods=['GET'])
    def execute_notion_rules():
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400

        user = get_user_with_refreshed_tokens(email)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        notion_token = user.get('integrations', {}).get('Notion', {}).get('token')
        if not notion_token:
            return jsonify({"error": "Token de Notion no disponible"}), 400

        rules = [rule for rule in user.get('automatizaciones', []) if rule.get("service") == "Notion" and rule.get("active")]
        executed_rules = []

        headers = {"Authorization": f"Bearer {notion_token}", "Notion-Version": "2022-06-28"}
        databases_url = "https://api.notion.com/v1/search"
        db_response = requests.post(databases_url, headers=headers, json={"query": "", "filter": {"value": "database", "property": "object"}})
        
        if db_response.status_code != 200:
            return jsonify({"error": "Error al obtener bases de datos de Notion"}), 500
        
        notion_dbs = db_response.json().get("results", [])
        
        for rule in rules:
            condition = rule.get("condition", "").lower().strip()
            action = rule.get("action", "").lower().strip()

            for db in notion_dbs:
                db_id = db["id"]
                query_url = f"https://api.notion.com/v1/databases/{db_id}/query"
                response = requests.post(query_url, headers=headers)
                
                if response.status_code == 200:
                    tasks = response.json().get("results", [])
                    for task in tasks:
                        task_id = task["id"]
                        properties = task.get("properties", {})
                        status = properties.get("Status", {}).get("select", {}).get("name", "").lower()
                        priority = properties.get("Priority", {}).get("select", {}).get("name", "").lower()
                        
                        if "en curso" in condition and status == "en curso":
                            update_notion_task(task_id, "Priority", "Crítica", headers)
                        elif "prioridad alta" in condition and priority == "alta":
                            update_notion_task(task_id, "Color", "Red", headers)
                        elif "tarea se complete" in condition and status == "completado":
                            update_notion_task(task_id, "Status", "Finalizados", headers)
                        elif "fecha de entrega muy lejana" in condition:
                            due_date = properties.get("Due Date", {}).get("date", {}).get("start")
                            if due_date and is_far_due_date(due_date):
                                update_notion_task(task_id, "Priority", "Baja", headers)

                        executed_rules.append(rule)

        return jsonify({"message": "Ejecución de reglas de Notion completada", "executed_rules": executed_rules})

    def update_notion_task(task_id, property_name, new_value, headers):
        update_url = f"https://api.notion.com/v1/pages/{task_id}"
        update_payload = {"properties": {property_name: {"select": {"name": new_value}}}}
        requests.patch(update_url, headers=headers, json=update_payload)

    @app.route('/execute/clickup', methods=['GET'])
    def execute_clickup_rules():
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400

        user = get_user_with_refreshed_tokens(email)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        clickup_token = user.get('integrations', {}).get('ClickUp', {}).get('token')
        if not clickup_token:
            return jsonify({"error": "Token de ClickUp no disponible"}), 400

        rules = [rule for rule in user.get('automatizaciones', []) if rule.get("service") == "ClickUp" and rule.get("active")]
        executed_rules = []

        headers = {'Authorization': f"Bearer {clickup_token}"}
        team_url = "https://api.clickup.com/api/v2/team"
        team_response = requests.get(team_url, headers=headers)

        if team_response.status_code != 200:
            return jsonify({"error": "Error al obtener equipos de ClickUp"}), 500

        teams = team_response.json().get("teams", [])
        for team in teams:
            team_id = team["id"]
            tasks_url = f"https://api.clickup.com/api/v2/team/{team_id}/task"
            tasks_response = requests.get(tasks_url, headers=headers)
            
            if tasks_response.status_code == 200:
                tasks = tasks_response.json().get("tasks", [])
                for task in tasks:
                    task_id = task["id"]
                    status = task.get("status", {}).get("status", "").lower()
                    priority = task.get("priority", None)
                    if priority:
                        priority = priority.lower()
                    else:
                        priority = ""

                    for rule in rules:
                        condition = rule.get("condition", "").lower().strip()
                        action = rule.get("action", "").lower().strip()
                        
                        if "en curso" in condition and status == "en curso":
                            update_clickup_task(task_id, "priority", "critical", headers)
                        elif "prioridad alta" in condition and priority == "alta":
                            update_clickup_task(task_id, "highlight", "red", headers)
                        elif "tarea se complete" in condition and status == "completado":
                            update_clickup_task(task_id, "status", "Finalizados", headers)
                        elif "fecha de entrega muy lejana" in condition:
                            due_date = task.get("due_date")
                            if due_date and is_far_due_date(due_date):
                                update_clickup_task(task_id, "priority", "low", headers)
                        
                        executed_rules.append(rule)
        
        return jsonify({"message": "Ejecución de reglas de ClickUp completada", "executed_rules": executed_rules})

    def update_clickup_task(task_id, field, new_value, headers):
        update_url = f"https://api.clickup.com/api/v2/task/{task_id}"
        update_payload = {field: new_value}
        requests.put(update_url, headers=headers, json=update_payload)

    def is_far_due_date(due_date):
        due_date_obj = datetime.fromisoformat(due_date[:-1])
        return (due_date_obj - datetime.utcnow()).days > 30

    @app.route('/execute/asana', methods=['GET'])
    def execute_asana_rules():
        try:
            email = request.args.get('email')
            if not email:
                return jsonify({"error": "Se debe proporcionar un email"}), 400

            # Buscar el usuario en la base de datos
            user = get_user_with_refreshed_tokens(email)
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            # Obtener el token actualizado
            asana_token = user.get('integrations', {}).get('Asana', {}).get('token')
            if not asana_token:
                return jsonify({"error": "Token de Asana no disponible"}), 400

            headers = {'Authorization': f'Bearer {asana_token}'}
            workspace_url = "https://app.asana.com/api/1.0/workspaces"
            workspace_response = requests.get(workspace_url, headers=headers)
            print(workspace_response)
            if workspace_response.status_code != 200:
                return jsonify({"error": "Error obteniendo el workspace de Asana"}), 500
            
            workspaces = workspace_response.json().get("data", [])
            if not workspaces:
                return jsonify({"error": "No se encontraron workspaces en Asana"}), 404
            
            workspace_id = workspaces[0]['gid']  # Se asume el primer workspace
            tasks_url = f"https://app.asana.com/api/1.0/workspaces/{workspace_id}/tasks"
            tasks_response = requests.get(tasks_url, headers=headers)
            if tasks_response.status_code != 200:
                return jsonify({"error": "Error obteniendo tareas de Asana"}), 500

            tasks = tasks_response.json().get("data", [])
            if not tasks:
                return jsonify({"message": "No hay tareas en Asana"}), 200

            # Obtener reglas activas para Asana
            rules = [rule for rule in user.get('automatizaciones', []) if rule.get("service") == "Asana" and rule.get("active")]
            executed_rules = []
            
            for rule in rules:
                condition = rule.get("condition", "").lower().strip()
                action = rule.get("action", "").lower().strip()

                for task in tasks:
                    task_id = task["gid"]
                    task_name = task["name"].lower()
                    task_details_url = f"https://app.asana.com/api/1.0/tasks/{task_id}"
                    task_details_response = requests.get(task_details_url, headers=headers)
                    if task_details_response.status_code != 200:
                        continue
                    
                    task_details = task_details_response.json().get("data", {})
                    priority = task_details.get("priority", "").lower()
                    status = task_details.get("status", "").lower()
                    due_date = task_details.get("due_on", "")
                    
                    # Evaluar condiciones
                    if "tarea esté 'en curso'" in condition and status == "en curso":
                        if action == "cambiar la prioridad a crítica":
                            update_task_priority(task_id, "crítica", headers)
                    elif "tarea tenga prioridad 'alta'" in condition and priority == "alta":
                        if action == "resaltar en rojo el título":
                            highlight_task_title(task_id, headers)
                    elif "tarea se complete" in condition and status == "completado":
                        if action == "mover a 'finalizados'":
                            move_task_to_completed(task_id, headers)
                    elif "tarea se cree con una fecha de entrega muy lejana" in condition:
                        if action == "marcar como 'baja prioridad'" and is_due_date_far(due_date):
                            update_task_priority(task_id, "baja", headers)

                    executed_rules.append(rule)

            return jsonify({"message": "Ejecución de reglas de Asana completada.", "executed_rules": executed_rules})
        
        except Exception as e:
            return jsonify({"error": str(e)}), 500


    def update_task_priority(task_id, priority, headers):
        update_url = f"https://app.asana.com/api/1.0/tasks/{task_id}"
        update_payload = {"priority": priority}
        requests.put(update_url, headers=headers, json=update_payload)

    def highlight_task_title(task_id, headers):
        update_url = f"https://app.asana.com/api/1.0/tasks/{task_id}"
        update_payload = {"name": "🔴 " + task_id}
        requests.put(update_url, headers=headers, json=update_payload)

    def move_task_to_completed(task_id, headers):
        update_url = f"https://app.asana.com/api/1.0/tasks/{task_id}"
        update_payload = {"status": "finalizado"}
        requests.put(update_url, headers=headers, json=update_payload)

    def is_due_date_far(due_date):
        from datetime import datetime, timedelta
        if not due_date:
            return False
        due_date_obj = datetime.strptime(due_date, "%Y-%m-%d")
        return due_date_obj > datetime.utcnow() + timedelta(days=30)