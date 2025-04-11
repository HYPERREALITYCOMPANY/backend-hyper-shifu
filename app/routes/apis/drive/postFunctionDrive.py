import requests
import re

def handle_post_request(accion, solicitud, email, user):
    """
    Maneja solicitudes POST para Google Drive, como compartir, mover, eliminar, crear o vaciar papelera.
    :param accion: Acción detectada (e.g., "subir", "compartir", "eliminar").
    :param solicitud: Detalles específicos de la solicitud (e.g., "archivo doc1.txt con juan@example.com").
    :param email: Email del usuario.
    :param user: Datos del usuario desde la base de datos.
    :return: Tupla con resultado en formato {"result": {...}} y código de estado HTTP.
    """
    try:
        drive_token = user.get('integrations', {}).get('drive', {}).get('token')
        if not drive_token:
            return {"result": {"message": "¡Ey! No tengo tu token de Google Drive, ¿me das permisos? 🔑"}}, 400

        headers = {'Authorization': f"Bearer {drive_token}", 'Content-Type': 'application/json'}

        if accion == "subir":
            if "a" in solicitud and "archivo" in solicitud:
                file_name = solicitud.split("archivo")[-1].split("a")[0].strip()
                folder = solicitud.split("a")[-1].strip()
                url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"
                metadata = {"name": file_name}
                headers['Content-Type'] = 'multipart/related; boundary=foo_bar_baz'
                payload = (
                    b'--foo_bar_baz\r\n'
                    b'Content-Type: application/json; charset=UTF-8\r\n\r\n' +
                    json.dumps(metadata).encode('utf-8') +
                    b'\r\n--foo_bar_baz\r\n'
                    b'Content-Type: text/plain\r\n\r\n'
                    b"Contenido simulado del archivo\r\n"
                    b'--foo_bar_baz--'
                )
                response = requests.post(url, headers=headers, data=payload)
                response.raise_for_status()
                return {"result": {"message": f"📤 Archivo '{file_name}' subido a '{folder}' con éxito 🚀"}}, 200
            return {"result": {"message": "Falta el nombre del archivo o la carpeta, ¿me lo aclaras?"}}, 400

        elif accion == "compartir":
            match = re.search(r'(archivo|carpeta)\s*(.+?)\s*con\s*(.+)', solicitud, re.IGNORECASE)
            if match:
                tipo = match.group(1).strip()
                nombre = match.group(2).strip()
                destinatarios = match.group(3).strip()
                if not nombre or not destinatarios:
                    return {"result": {"message": "Falta el nombre o los destinatarios, ¿me lo aclaras?"}}, 400

                destinatarios_limpios = [email.strip(":").strip() for email in destinatarios.split(',')]
                url = "https://www.googleapis.com/drive/v3/files"
                params = {"q": f"name contains '{nombre}' trashed=false", "fields": "files(id,name)"}
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()
                results = response.json().get('files', [])

                if not results:
                    return {"result": {"message": f"No encontré el {tipo} '{nombre}'"}}, 404
                if len(results) > 1:
                    return {"result": {"message": f"Encontré varios {tipo}s con '{nombre}', sé más específico"}}, 400

                file_id = results[0]['id']
                for email_dest in destinatarios_limpios:
                    permission_url = f"https://www.googleapis.com/drive/v3/files/{file_id}/permissions"
                    permission_data = {"type": "user", "role": "reader", "emailAddress": email_dest}
                    requests.post(permission_url, headers=headers, json=permission_data).raise_for_status()

                return {"result": {"message": f"🚀 ¡El {tipo} '{nombre}' fue compartido con éxito!"}}, 200
            return {"result": {"message": "No entendí qué compartir o con quién, ¿me lo aclaras?"}}, 400

        elif accion == "mover":
            match = re.search(r'archivo\s*(.+?)\s*a\s*carpeta\s*(.+)', solicitud, re.IGNORECASE)
            if match:
                file_name = match.group(1).strip()
                folder_name = match.group(2).strip()
                url = "https://www.googleapis.com/drive/v3/files"
                params = {"q": f"name contains '{file_name}' trashed=false", "fields": "files(id,name)"}
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()
                files = response.json().get('files', [])
                if not files:
                    return {"result": {"message": f"No encontré el archivo '{file_name}'"}}, 404
                if len(files) > 1:
                    return {"result": {"message": f"Encontré varios archivos con '{file_name}', sé más específico"}}, 400
                file_id = files[0]['id']

                params = {"q": f"name contains '{folder_name}' mimeType='application/vnd.google-apps.folder' trashed=false", "fields": "files(id,name)"}
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()
                folders = response.json().get('files', [])
                if not folders:
                    return {"result": {"message": f"No encontré la carpeta '{folder_name}'"}}, 404
                if len(folders) > 1:
                    return {"result": {"message": f"Encontré varias carpetas con '{folder_name}', sé más específico"}}, 400
                folder_id = folders[0]['id']

                file_url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
                update_data = {"addParents": folder_id}
                response = requests.patch(file_url, headers=headers, params=update_data)
                response.raise_for_status()
                return {"result": {"message": f"🎉 Archivo '{file_name}' movido a '{folder_name}' con éxito!"}}, 200
            return {"result": {"message": "Falta el nombre del archivo o la carpeta, ¿me lo aclaras?"}}, 400

        elif accion == "eliminar":
            if "archivo" in solicitud:
                file_name = solicitud.split("archivo")[-1].strip()
                url = "https://www.googleapis.com/drive/v3/files"
                params = {"q": f"name contains '{file_name}' trashed=false", "fields": "files(id,name)"}
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()
                files = response.json().get('files', [])
                if not files:
                    return {"result": {"message": f"No encontré el archivo '{file_name}'"}}, 404
                if len(files) > 1:
                    return {"result": {"message": f"Encontré varios archivos con '{file_name}', sé más específico"}}, 400
                file_id = files[0]['id']
                trash_url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
                trash_data = {"trashed": True}
                requests.patch(trash_url, headers=headers, json=trash_data).raise_for_status()
                return {"result": {"message": f"🗑️ Archivo '{file_name}' movido a la papelera con éxito!"}}, 200
            return {"result": {"message": "Falta el nombre del archivo, ¿cuál elimino?"}}, 400

        elif accion == "crear":
            if "carpeta" in solicitud:
                folder_name = solicitud.split("carpeta")[-1].strip()
                url = "https://www.googleapis.com/drive/v3/files"
                metadata = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
                response = requests.post(url, headers=headers, json=metadata)
                response.raise_for_status()
                return {"result": {"message": f"🚀 Carpeta '{folder_name}' creada con éxito en Drive!"}}, 200
            return {"result": {"message": "Falta el nombre de la carpeta, ¿me lo das?"}}, 400

        elif accion == "vaciar":
            if "papelera" in solicitud.lower():
                empty_trash_url = "https://www.googleapis.com/drive/v3/files/trash"
                requests.delete(empty_trash_url, headers=headers).raise_for_status()
                return {"result": {"message": "🗑️ ¡La papelera de Google Drive ha sido vaciada con éxito!"}}, 200
            return {"result": {"message": "No entendí qué vaciar, ¿te refieres a la papelera?"}}, 400

        return {"result": {"message": "Acción no soportada para POST en Google Drive"}}, 400

    except requests.RequestException as e:
        return {"result": {"message": f"¡Ay, qué mala onda! Error con Drive: {str(e)}"}}, 500
    except Exception as e:
        return {"result": {"message": f"¡Se puso feo! Error inesperado: {str(e)}"}}, 500