import requests
import re

def get_task_id_asana(task_name, asana_token):
    """Busca el ID de una tarea en Asana por su nombre."""
    headers = {'Authorization': f"Bearer {asana_token}", 'Content-Type': 'application/json'}
    workspaces_url = "https://app.asana.com/api/1.0/workspaces"
    workspaces_response = requests.get(workspaces_url, headers=headers)
    workspaces_response.raise_for_status()
    workspace_id = workspaces_response.json().get('data', [])[0].get('gid')

    tasks_url = f"https://app.asana.com/api/1.0/workspaces/{workspace_id}/tasks/search"
    params = {"text": task_name, "opt_fields": "name,gid"}
    tasks_response = requests.get(tasks_url, headers=headers, params=params)
    tasks_response.raise_for_status()
    tasks = tasks_response.json().get('data', [])

    for task in tasks:
        if task.get('name', '').lower() == task_name.lower():
            return task.get('gid')
    return None

def handle_post_request(accion, solicitud, email, user):
    """
    Maneja solicitudes POST para Asana, como crear, completar o eliminar tareas.
    :param accion: Acción detectada (e.g., "crear", "actualizar", "eliminar").
    :param solicitud: Detalles específicos de la solicitud (e.g., "tarea en Proyectos").
    :param email: Email del usuario.
    :param user: Datos del usuario desde la base de datos.
    :return: Tupla con resultado en formato {"result": {...}} y código de estado HTTP.
    """
    try:
        asana_token = user.get('integrations', {}).get('Asana', {}).get('token')
        if not asana_token:
            return {"result": {"message": "¡Ey! No tengo tu token de Asana, ¿me das permisos? 🔑"}}, 400

        headers = {'Authorization': f"Bearer {asana_token}", 'Content-Type': 'application/json'}

        if accion == "crear":
            match = re.search(r'tarea\s*(.+?)\s*en\s*(.+)', solicitud, re.IGNORECASE)
            if match:
                task_name = match.group(1).strip()
                project_name = match.group(2).strip()

                # Obtener workspace
                workspaces_url = "https://app.asana.com/api/1.0/workspaces"
                workspaces_response = requests.get(workspaces_url, headers=headers)
                workspaces_response.raise_for_status()
                workspace_id = workspaces_response.json().get('data', [])[0].get('gid')

                # Obtener proyecto
                projects_url = f"https://app.asana.com/api/1.0/workspaces/{workspace_id}/projects"
                projects_response = requests.get(projects_url, headers=headers)
                projects_response.raise_for_status()
                projects = projects_response.json().get('data', [])
                
                project_id = None
                for project in projects:
                    if project_name.lower() in project.get('name', '').lower():
                        project_id = project.get('gid')
                        break
                
                if not project_id:
                    return {"result": {"message": f"No encontré el proyecto '{project_name}'"}}, 404

                # Crear tarea
                tasks_url = "https://app.asana.com/api/1.0/tasks"
                data = {
                    "data": {
                        "name": task_name,
                        "projects": [project_id],
                        "completed": False
                    }
                }
                response = requests.post(tasks_url, headers=headers, json=data)
                response.raise_for_status()
                return {"result": {"message": f"🚀 Tarea '{task_name}' creada en '{project_name}' con éxito!"}}, 200
            return {"result": {"message": "Falta el nombre de la tarea o el proyecto, ¿me lo aclaras?"}}, 400

        elif accion in ["actualizar", "eliminar"]:
            match = re.search(r'tarea\s*(.+)', solicitud, re.IGNORECASE)
            if not match:
                return {"result": {"message": "Falta el nombre de la tarea, ¿cuál modifico o elimino?"}}, 400
            task_name = match.group(1).strip()

            task_id = get_task_id_asana(task_name, asana_token)
            if not task_id:
                return {"result": {"message": f"No encontré la tarea '{task_name}'"}}, 404

            url = f"https://app.asana.com/api/1.0/tasks/{task_id}"
            if accion == "actualizar":
                status_match = re.search(r'estado\s*(.+)', solicitud, re.IGNORECASE)
                completed = True if (status_match and "complet" in status_match.group(1).lower()) or "completada" in solicitud.lower() else False
                data = {"data": {"completed": completed}}
                response = requests.put(url, headers=headers, json=data)
                response.raise_for_status()
                status_text = "completada" if completed else "pendiente"
                return {"result": {"message": f"✨ Tarea '{task_name}' marcada como {status_text}"}}, 200
            elif accion == "eliminar":
                response = requests.delete(url, headers=headers)
                response.raise_for_status()
                return {"result": {"message": f"🗑️ Tarea '{task_name}' eliminada con éxito!"}}, 200

        return {"result": {"message": "Acción no soportada para POST en Asana"}}, 400

    except requests.RequestException as e:
        return {"result": {"message": f"¡Ay, qué mala onda! Error con Asana: {str(e)}"}}, 500
    except Exception as e:
        return {"result": {"message": f"¡Se puso feo! Error inesperado: {str(e)}"}}, 500