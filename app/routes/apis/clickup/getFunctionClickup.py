import requests
from datetime import datetime

def handle_get_request(accion, solicitud, email, user):
    """
    Maneja solicitudes GET para ClickUp, como buscar tareas o listas.
    :param accion: Acción detectada (e.g., "buscar").
    :param solicitud: Detalles específicos de la solicitud (e.g., "tareas en Proyectos").
    :param email: Email del usuario.
    :param user: Datos del usuario desde la base de datos.
    :return: Tupla con resultado en formato {"result": {...}} y código de estado HTTP.
    """
    try:
        clickup_token = user.get('integrations', {}).get('ClickUp', {}).get('token')
        if not clickup_token:
            return {"result": {"message": "¡Ey! No tengo tu token de ClickUp, ¿me das permisos? 🔑"}}, 400

        headers = {'Authorization': clickup_token, 'Content-Type': 'application/json'}

        if accion == "buscar":
            if "tareas en" in solicitud:
                search_term = solicitud.split("tareas en")[-1].strip()

                # Obtener el team_id
                team_url = "https://api.clickup.com/api/v2/team"
                team_response = requests.get(team_url, headers=headers)
                team_response.raise_for_status()
                teams = team_response.json().get('teams', [])
                if not teams:
                    return {"result": {"message": "¡Vaya! No perteneces a ningún equipo en ClickUp"}}, 400
                team_id = teams[0].get('id')

                # Obtener espacios
                spaces_url = f"https://api.clickup.com/api/v2/team/{team_id}/space"
                spaces_response = requests.get(spaces_url, headers=headers)
                spaces_response.raise_for_status()
                spaces = spaces_response.json().get('spaces', [])

                results = []
                for space in spaces:
                    space_id = space.get('id')
                    folders_url = f"https://api.clickup.com/api/v2/space/{space_id}/folder"
                    folders_response = requests.get(folders_url, headers=headers)
                    if folders_response.status_code != 200:
                        continue
                    folders = folders_response.json().get('folders', [])

                    for folder in folders:
                        folder_id = folder.get('id')
                        lists_url = f"https://api.clickup.com/api/v2/folder/{folder_id}/list"
                        lists_response = requests.get(lists_url, headers=headers)
                        if lists_response.status_code != 200:
                            continue
                        lists = lists_response.json().get('lists', [])

                        for lst in lists:
                            list_id = lst.get('id')
                            if search_term.lower() not in lst.get('name', '').lower():
                                continue
                            task_url = f"https://api.clickup.com/api/v2/list/{list_id}/task"
                            params = {"search": search_term, "subtasks": True, "include_closed": True}
                            task_response = requests.get(task_url, headers=headers, params=params)
                            if task_response.status_code == 200:
                                tasks = task_response.json().get('tasks', [])
                                for task in tasks:
                                    due_date = "Sin fecha"
                                    if task.get('due_date'):
                                        try:
                                            due_timestamp = int(task.get('due_date')) / 1000
                                            due_date = datetime.fromtimestamp(due_timestamp).strftime("%d/%m/%Y %H:%M")
                                        except:
                                            due_date = task.get('due_date')
                                    task_info = {
                                        "id": task.get('id'),
                                        "name": task.get('name', 'Sin título'),
                                        "status": task.get('status', {}).get('status', 'Sin estado'),
                                        "due_date": due_date
                                    }
                                    results.append(task_info)

                if not results:
                    return {"result": {"message": f"No encontré tareas en '{search_term}'"}}, 200
                return {"result": {"message": f"¡Órale! Encontré {len(results)} tareas en '{search_term}' 📋", "data": results}}, 200
            else:
                return {"result": {"message": "No entendí bien dónde buscar, ¿me das más detalles?"}}, 400
        else:
            return {"result": {"message": "Acción no soportada para GET en ClickUp"}}, 400

    except requests.RequestException as e:
        return {"result": {"message": f"¡Ay, qué mala onda! Error con ClickUp: {str(e)}"}}, 500
    except Exception as e:
        return {"result": {"message": f"¡Se puso feo! Error inesperado: {str(e)}"}}, 500