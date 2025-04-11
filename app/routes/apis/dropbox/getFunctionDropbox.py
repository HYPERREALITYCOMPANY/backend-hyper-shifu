import requests
from flask import jsonify

def handle_get_request(accion, solicitud, email, user):
    """
    Maneja solicitudes GET para Dropbox, como buscar archivos o carpetas.
    :param accion: Acción detectada (e.g., "buscar").
    :param solicitud: Detalles específicos de la solicitud (e.g., "archivos en Proyectos").
    :param email: Email del usuario.
    :param user: Datos del usuario desde la base de datos.
    :return: Tupla con resultado en formato {"result": {...}} y código de estado HTTP.
    """
    try:
        dropbox_integration = user.get('integrations', {}).get('Dropbox', None)
        dropbox_token = dropbox_integration.get('token') if dropbox_integration else None

        if not dropbox_token:
            return {"result": {"message": "Token de Dropbox no disponible"}}, 400

        if accion == "buscar":
            if "archivos en" in solicitud:
                folder = solicitud.split("archivos en")[-1].strip()
                search_term = folder
                search_type = None  # Puede ser "file" o "folder"

                # Extraer filtros adicionales si existen
                if "carpeta:" in solicitud:
                    search_term = solicitud.split("carpeta:")[-1].strip()
                    search_type = "folder"
                elif "archivo:" in solicitud:
                    search_term = solicitud.split("archivo:")[-1].strip()
                    search_type = "file"

                # Llamada a la API de Dropbox para buscar
                url = "https://api.dropboxapi.com/2/files/search_v2"
                headers = {
                    'Authorization': f"Bearer {dropbox_token}",
                    'Content-Type': 'application/json'
                }
                params = {
                    "query": search_term,
                    "options": {
                        "max_results": 10,
                        "file_status": "active"
                    }
                }

                response = requests.post(url, headers=headers, json=params)
                response.raise_for_status()

                results = response.json().get('matches', [])
                if not results:
                    return {"result": {"message": f"No encontré nada en Dropbox para '{search_term}'"}}, 200

                # Procesar resultados
                filtered_results = []
                for result in results:
                    metadata = result.get('metadata', {}).get('metadata', {})
                    name = metadata.get('name', 'Sin nombre')
                    path = metadata.get('path_display', 'Sin ruta')
                    tag = metadata.get('.tag', '')
                    size = metadata.get('size', None)
                    modified = metadata.get('server_modified', None)

                    if search_type == "folder" and tag == "folder":
                        # Listar contenido de la carpeta
                        list_folder_url = "https://api.dropboxapi.com/2/files/list_folder"
                        list_folder_headers = {
                            'Authorization': f"Bearer {dropbox_token}",
                            'Content-Type': 'application/json'
                        }
                        list_folder_params = {"path": path}

                        list_response = requests.post(list_folder_url, headers=list_folder_headers, json=list_folder_params)
                        list_response.raise_for_status()
                        folder_contents = list_response.json().get('entries', [])

                        for item in folder_contents:
                            if item['.tag'] == 'file':
                                file_link = generate_dropbox_link(dropbox_token, item['path_display'])
                                filtered_results.append({
                                    'name': item['name'],
                                    'path': item['path_display'],
                                    'type': 'file',
                                    'size': item.get('size'),
                                    'last_modified': item.get('server_modified')
                                })
                    elif not search_type or tag == search_type:
                        filtered_results.append({
                            'name': name,
                            'path': path,
                            'type': tag,
                            'size': size,
                            'last_modified': modified
                        })

                if not filtered_results:
                    return {"result": {"message": f"No encontré archivos o carpetas que coincidan con '{search_term}'"}}, 200

                return {"result": {"message": f"Encontré {len(filtered_results)} resultado(s) en Dropbox", "data": filtered_results}}, 200
            else:
                return {"result": {"message": "No entendí bien dónde buscar, ¿me das más detalles?"}}, 400
        else:
            return {"result": {"message": "Acción no soportada para GET en Dropbox"}}, 400

    except requests.RequestException as e:
        return {"result": {"message": "Error al realizar la solicitud a Dropbox", "details": str(e)}}, 500
    except Exception as e:
        return {"result": {"message": "Error inesperado", "details": str(e)}}, 500

def generate_dropbox_link(token, file_path):
    """Genera un enlace temporal de descarga para un archivo en Dropbox."""
    url = "https://api.dropboxapi.com/2/files/get_temporary_link"
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }
    params = {"path": file_path}

    try:
        response = requests.post(url, headers=headers, json=params)
        response.raise_for_status()
        return response.json().get("link")
    except requests.RequestException as e:
        print(f"Error al generar link para {file_path}: {e}")
        return None