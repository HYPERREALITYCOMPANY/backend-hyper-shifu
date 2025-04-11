import requests
import re

def handle_post_request(accion, solicitud, email, user):
    """
    Maneja solicitudes POST para ClickUp, como crear, completar, eliminar o cambiar estado de tareas.
    :param accion: Acción detectada (e.g., "crear", "eliminar", "actualizar").
    :param solicitud: Detalles específicos de la solicitud (e.g., "tarea en Proyectos").
    :param email: Email del usuario.
    :param user: Datos del usuario desde la base de datos.
    :return: Tupla con resultado en formato {"result": {...}} y código de estado HTTP.
    """
    try:
        clickup_token = user.get('integrations', {}).get('ClickUp', {}).get('token')
        if not clickup_token:
            return {"result": {"message": "¡Ey! No tengo tu token de ClickUp, ¿me das permisos? 🔑"}}, 400

        headers = {'Authorization': clickup_token, 'Content-Type': 'application/json'}

        if accion == "crear":
            match = re.search(r'tarea\s*(.+?)\s*en\s*(.+)', solicitud, re.IGNORECASE)
            if match:
                task_name = match.group(1).strip()
                list_name = match.group(2).strip()
                # Buscar el list_id
                team_url = "https://api.clickup.com/api/v2/team"
                team_response = requests.get(team_url, headers=headers)
                team_response.raise_for_status()
                team_id = team_response.json().get('teams', [])[0].get('id')

                spaces_url = f"https://api.clickup.com/api/v2/team/{team_id}/space"
                spaces_response = requests.get(spaces_url, headers=headers)
                spaces_response.raise_for_status()
                spaces = spaces_response.json().get('spaces', [])

                list_id = None
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
                            if list_name.lower() in lst.get('name', '').lower():
                                list_id = lst.get('id')
                                break
                        if list_id:
                            break
                    if list_id:
                        break

                if not list_id:
                    return {"result": {"message": f"No encontré la lista '{list_name}'"}}, 404

                task_url = f"https://api.clickup.com/api/v2/list/{list_id}/task"
                data = {"name": task_name, "status": "to do"}
                response = requests.post(task_url, headers=headers, json=data)
                response.raise_for_status()
                return {"result": {"message": f"🚀 Tarea '{task_name}' creada en '{list_name}' con éxito!"}}, 200
            return {"result": {"message": "Falta el nombre de la tarea o la lista, ¿me lo aclaras?"}}, 400

        elif accion in ["actualizar", "eliminar"]:
            match = re.search(r'tarea\s*(.+)', solicitud, re.IGNORECASE)
            if not match:
                return {"result": {"message": "Falta el nombre de la tarea, ¿cuál modifico o elimino?"}}, 400
            task_name = match.group(1).strip()

            # Buscar el task_id
            team_url = "https://api.clickup.com/api/v2/team"
            team_response = requests.get(team_url, headers=headers)
            team_response.raise_for_status()
            team_id = team_response.json().get('teams', [])[0].get('id')

            spaces_url = f"https://api.clickup.com/api/v2/team/{team_id}/space"
            spaces_response = requests.get(spaces_url, headers=headers)
            spaces_response.raise_for_status()
            spaces = spaces_response.json().get('spaces', [])

            task_id = None
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
                        task_url = f"https://api.clickup.com/api/v2/list/{list_id}/task"
                        params = {"search": task_name, "subtasks": True, "include_closed": True}
                        task_response = requests.get(task_url, headers=headers, params=params)
                        if task_response.status_code == 200:
                            tasks = task_response.json().get('tasks', [])
                            for task in tasks:
                                if task.get('name', '').lower() == task_name.lower():
                                    task_id = task.get('id')
                                    break
                        if task_id:
                            break
                    if task_id:
                        break
                if task_id:
                    break

            if not task_id:
                return {"result": {"message": f"No encontré la tarea '{task_name}'"}}, 404

            url = f"https://api.clickup.com/api/v2/task/{task_id}"
            if accion == "actualizar":
                status_match = re.search(r'estado\s*(.+)', solicitud, re.IGNORECASE)
                new_status = status_match.group(1).strip() if status_match else "complete"
                data = {"status": new_status}
                response = requests.put(url, headers=headers, json=data)
                response.raise_for_status()
                return {"result": {"message": f"✨ Estado de la tarea '{task_name}' cambiado a '{new_status}'"}}, 200
            elif accion == "eliminar":
                response = requests.delete(url, headers=headers)
                if response.status_code == 204:
                    return {"result": {"message": f"🗑️ Tarea '{task_name}' eliminada con éxito!"}}, 200
                else:
                    return {"result": {"message": f"No pude eliminar la tarea '{task_name}'"}}, 400

        return {"result": {"message": "Acción no soportada para POST en ClickUp"}}, 400

    except requests.RequestException as e:
        return {"result": {"message": f"¡Ay, qué mala onda! Error con ClickUp: {str(e)}"}}, 500
    except Exception as e:
        return {"result": {"message": f"¡Se puso feo! Error inesperado: {str(e)}"}}, 500