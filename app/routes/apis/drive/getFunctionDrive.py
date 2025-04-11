import requests

def handle_get_request(accion, solicitud, email, user):
    """
    Maneja solicitudes GET para Google Drive, como buscar archivos o carpetas.
    :param accion: Acción detectada (e.g., "buscar").
    :param solicitud: Detalles específicos de la solicitud (e.g., "archivos en Proyecto X").
    :param email: Email del usuario.
    :param user: Datos del usuario desde la base de datos.
    :return: Tupla con resultado en formato {"result": {...}} y código de estado HTTP.
    """
    try:
        drive_token = user.get('integrations', {}).get('drive', {}).get('token')
        if not drive_token:
            return {"result": {"message": "¡Ey! No tengo tu token de Google Drive, ¿me das permisos? 🔑"}}, 400

        headers = {'Authorization': f"Bearer {drive_token}", 'Content-Type': 'application/json'}
        url = "https://www.googleapis.com/drive/v3/files"

        if accion == "buscar":
            if "archivos en" in solicitud:
                folder_name = solicitud.split("archivos en")[-1].strip()
                # Buscar la carpeta por nombre
                params = {
                    "q": f"'root' in parents {folder_name} mimeType='application/vnd.google-apps.folder' trashed=false",
                    "fields": "files(id,name)"
                }
                folder_response = requests.get(url, headers=headers, params=params)
                folder_response.raise_for_status()
                folders = folder_response.json().get('files', [])

                if not folders:
                    # Si no se encuentra como carpeta, buscar como término general
                    params = {
                        "q": f"{folder_name} trashed=false",
                        "fields": "files(id,name,webViewLink,size,modifiedTime)"
                    }
                    response = requests.get(url, headers=headers, params=params)
                    response.raise_for_status()
                    files = response.json().get('files', [])
                else:
                    folder_id = folders[0]['id']
                    # Buscar archivos dentro de la carpeta
                    params = {
                        "q": f"'{folder_id}' in parents trashed=false",
                        "fields": "files(id,name,webViewLink,size,modifiedTime)"
                    }
                    response = requests.get(url, headers=headers, params=params)
                    response.raise_for_status()
                    files = response.json().get('files', [])

                if not files:
                    return {"result": {"message": f"No encontré archivos en '{folder_name}'"}}, 200

                results = [
                    {
                        "file_name": file["name"],
                        "url": file["webViewLink"],
                        "size": file.get("size"),
                        "last_modified": file.get("modifiedTime")
                    } for file in files
                ]
                return {"result": {"message": f"¡Órale! Encontré {len(results)} archivos en '{folder_name}' 📁", "data": results}}, 200
            else:
                return {"result": {"message": "No entendí bien dónde buscar, ¿me das más detalles?"}}, 400
        else:
            return {"result": {"message": "Acción no soportada para GET en Google Drive"}}, 400

    except requests.RequestException as e:
        return {"result": {"message": f"¡Ay, qué mala onda! Error con Drive: {str(e)}"}}, 500
    except Exception as e:
        return {"result": {"message": f"¡Se puso feo! Error inesperado: {str(e)}"}}, 500