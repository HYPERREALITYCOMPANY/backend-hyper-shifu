import requests
from datetime import datetime, timedelta

def handle_get_request(accion, solicitud, email, user):
    """
    Maneja solicitudes GET para Asana, como buscar tareas.
    :param accion: Acción detectada (e.g., "buscar").
    :param solicitud: Detalles específicos de la solicitud (e.g., "tareas en Proyectos").
    :param email: Email del usuario.
    :param user: Datos del usuario desde la base de datos.
    :return: Tupla con resultado en formato {"result": {...}} y código de estado HTTP.
    """
    try:
        asana_token = user.get('integrations', {}).get('Asana', {}).get('token')
        if not asana_token:
            return {"result": {"message": "¡Ey! No tengo tu token de Asana, ¿me das permisos? 🔑"}}, 400

        headers = {'Authorization': f"Bearer {asana_token}", 'Content-Type': 'application/json'}

        if accion == "buscar":
            if "tareas en" in solicitud:
                search_term = solicitud.split("tareas en")[-1].strip().lower()

                # Obtener el workspace_id
                workspaces_url = "https://app.asana.com/api/1.0/workspaces"
                workspaces_response = requests.get(workspaces_url, headers=headers)
                workspaces_response.raise_for_status()
                workspaces = workspaces_response.json().get('data', [])
                if not workspaces:
                    return {"result": {"message": "¡Vaya! No tienes workspaces en Asana"}}, 400
                workspace_id = workspaces[0].get('gid')

                # Obtener el user_id
                user_url = "https://app.asana.com/api/1.0/users/me"
                user_response = requests.get(user_url, headers=headers)
                user_response.raise_for_status()
                user_id = user_response.json().get('data', {}).get('gid')

                # Listar tareas asignadas al usuario en el workspace
                tasks_url = "https://app.asana.com/api/1.0/tasks"
                params = {
                    "opt_fields": "name,gid,completed,assignee.name,due_on,projects.name",
                    "limit": 100,
                    "assignee": user_id,
                    "workspace": workspace_id
                }
                tasks_response = requests.get(tasks_url, headers=headers, params=params)
                tasks_response.raise_for_status()
                tasks = tasks_response.json().get('data', [])

                if not tasks:
                    return {"result": {"message": "No hay tareas asignadas a ti en este workspace"}}, 200

                # Filtrar tareas según el término de búsqueda
                today = datetime.today().strftime('%Y-%m-%d')
                tomorrow = (datetime.today() + timedelta(days=1)).strftime('%Y-%m-%d')
                filtered_tasks = []
                for task in tasks:
                    task_name = task.get('name', '').lower()
                    if "hoy" in search_term and task.get('due_on') == today:
                        filtered_tasks.append(task)
                    elif "mañana" in search_term and task.get('due_on') == tomorrow:
                        filtered_tasks.append(task)
                    elif "pendientes" in search_term and not task.get('completed'):
                        filtered_tasks.append(task)
                    elif search_term in task_name:
                        filtered_tasks.append(task)

                if not filtered_tasks:
                    return {"result": {"message": f"No encontré tareas para '{search_term}'"}}, 200

                # Formatear resultados
                results = [
                    {
                        "id": task.get('gid'),
                        "name": task.get('name', 'Sin título'),
                        "status": "Completada" if task.get('completed') else "Pendiente",
                        "due_date": task.get('due_on', 'Sin fecha')
                    }
                    for task in filtered_tasks
                ]
                return {"result": {"message": f"¡Órale! Encontré {len(results)} tareas para '{search_term}' 📋", "data": results}}, 200
            else:
                return {"result": {"message": "No entendí bien dónde buscar, ¿me das más detalles?"}}, 400
        else:
            return {"result": {"message": "Acción no soportada para GET en Asana"}}, 400

    except requests.RequestException as e:
        return {"result": {"message": f"¡Ay, qué mala onda! Error con Asana: {str(e)}"}}, 500
    except Exception as e:
        return {"result": {"message": f"¡Se puso feo! Error inesperado: {str(e)}"}}, 500