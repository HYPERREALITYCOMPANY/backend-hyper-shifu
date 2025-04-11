import requests
import re

def handle_post_request(accion, solicitud, email, user):
    """
    Maneja solicitudes POST para Dropbox, como subir, crear, eliminar o mover.
    :param accion: Acción detectada (e.g., "subir", "crear", "eliminar").
    :param solicitud: Detalles específicos de la solicitud (e.g., "archivo doc1.txt a Proyectos").
    :param email: Email del usuario.
    :param user: Datos del usuario desde la base de datos.
    :return: Tupla con resultado en formato {"result": {...}} y código de estado HTTP.
    """
    try:
        dropbox_integration = user.get('integrations', {}).get('Dropbox', None)
        dropbox_token = dropbox_integration.get('token') if dropbox_integration else None

        if not dropbox_token:
            return {"result": {"message": "Token de Dropbox no disponible"}}, 400

        headers = {
            'Authorization': f"Bearer {dropbox_token}",
            'Content-Type': 'application/json'
        }

        if accion == "subir":
            if "a" in solicitud and "archivo" in solicitud:
                file_name = solicitud.split("archivo")[-1].split("a")[0].strip()
                folder = solicitud.split("a")[-1].strip()
                return {"result": {"message": f"Archivo '{file_name}' subido a '{folder}' con éxito"}}, 200  # Simulación, ajustar con API real
            return {"result": {"message": "Falta el nombre del archivo o la carpeta, ¿me lo aclaras?"}}, 400

        elif accion == "crear":
            if "carpeta" in solicitud:
                folder_name = solicitud.split("carpeta")[-1].strip()
                url = "https://api.dropboxapi.com/2/files/create_folder_v2"
                data = {
                    "path": f"/{folder_name}",
                    "autorename": False
                }
                response = requests.post(url, headers=headers, json=data)
                response.raise_for_status()
                return {"result": {"message": f"Carpeta '{folder_name}' creada con éxito en Dropbox"}}, 200
            return {"result": {"message": "Falta el nombre de la carpeta, ¿me lo das?"}}, 400

        elif accion == "eliminar":
            if "archivo" in solicitud or "carpeta" in solicitud:
                target = "archivo" if "archivo" in solicitud else "carpeta"
                name = solicitud.split(target)[-1].strip()

                # Buscar el archivo o carpeta
                url = "https://api.dropboxapi.com/2/files/search_v2"
                params = {
                    "query": name,
                    "options": {"max_results": 10, "file_status": "active"}
                }
                response = requests.post(url, headers=headers, json=params)
                response.raise_for_status()
                results = response.json().get('matches', [])

                if not results:
                    return {"result": {"message": f"No encontré '{name}' en Dropbox"}}, 404
                if len(results) > 1:
                    return {"result": {"message": f"Encontré varios '{target}s' similares a '{name}', por favor sé más específico"}}, 400

                path = results[0]['metadata']['metadata']['path_lower']
                delete_url = "https://api.dropboxapi.com/2/files/delete_v2"
                delete_data = {"path": path}
                delete_response = requests.post(delete_url, headers=headers, json=delete_data)
                delete_response.raise_for_status()
                return {"result": {"message": f"{target.capitalize()} '{name}' eliminado con éxito"}}, 200
            return {"result": {"message": f"Falta el nombre del {target}, ¿cuál elimino?"}}, 400

        elif accion == "mover":  # Agregar soporte para mover archivos
            match = re.search(r'archivo (.+?) a carpeta (.+)', solicitud, re.IGNORECASE)
            if match:
                file_name = match.group(1).strip()
                folder_name = match.group(2).strip()

                # Buscar el archivo
                url = "https://api.dropboxapi.com/2/files/search_v2"
                params = {
                    "query": file_name,
                    "options": {"max_results": 10, "file_status": "active"}
                }
                response = requests.post(url, headers=headers, json=params)
                response.raise_for_status()
                results = response.json().get('matches', [])

                if not results:
                    return {"result": {"message": f"No encontré el archivo '{file_name}'"}}, 404
                if len(results) > 1:
                    return {"result": {"message": f"Encontré varios archivos similares a '{file_name}', por favor sé más específico"}}, 400

                file_path = results[0]['metadata']['metadata']['path_lower']
                folder_path = f"/{folder_name}/{file_name}"

                # Mover el archivo
                url_move = "https://api.dropboxapi.com/2/files/move_v2"
                data = {
                    "from_path": file_path,
                    "to_path": folder_path,
                    "allow_ownership_transfer": False,
                    "allow_shared_folder": True,
                    "autorename": False
                }
                move_response = requests.post(url_move, headers=headers, json=data)
                move_response.raise_for_status()
                return {"result": {"message": f"Archivo '{file_name}' movido a '{folder_name}' con éxito"}}, 200
            return {"result": {"message": "Falta el nombre del archivo o la carpeta de destino, ¿me lo aclaras?"}}, 400

        elif accion == "restaurar":  # Soporte para restaurar archivos
            if "archivo" in solicitud:
                file_name = solicitud.split("archivo")[-1].strip()

                # Buscar revisiones del archivo (simulación, ajustar según API real)
                url = "https://api.dropboxapi.com/2/files/list_revisions"
                params = {"path": f"/{file_name}", "limit": 1}
                response = requests.post(url, headers=headers, json=params)
                response.raise_for_status()
                revisions = response.json()

                if 'entries' in revisions and revisions['entries']:
                    rev = revisions['entries'][0]['rev']
                    url_restore = "https://api.dropboxapi.com/2/files/restore"
                    restore_params = {"path": f"/{file_name}", "rev": rev}
                    restore_response = requests.post(url_restore, headers=headers, json=restore_params)
                    restore_response.raise_for_status()
                    return {"result": {"message": f"Archivo '{file_name}' restaurado con éxito"}}, 200
                return {"result": {"message": f"No encontré revisiones para '{file_name}'"}}, 404
            return {"result": {"message": "Falta el nombre del archivo a restaurar, ¿me lo das?"}}, 400

        return {"result": {"message": "Acción no soportada para POST en Dropbox"}}, 400

    except requests.RequestException as e:
        return {"result": {"message": "Error al realizar la solicitud a Dropbox", "details": str(e)}}, 500
    except Exception as e:
        return {"result": {"message": "Error inesperado", "details": str(e)}}, 500