import re
import requests

def handle_get_request(accion, solicitud, email, user):
    if not user:
        return {"solicitud": "GET", "result": {"error": "¡Órale! No te encontré en la base, ¿seguro que estás registrado?"}}, 404

    onedrive_integration = user.get('integrations', {}).get('onedrive', None)  # Cambié 'OneDrive' a 'onedrive' para consistencia
    if not onedrive_integration or not onedrive_integration.get('token'):
        return {"solicitud": "GET", "result": {"error": "¡Ey! No tengo tu token de OneDrive, ¿me das permisos otra vez?"}}, 400
    onedrive_token = onedrive_integration.get('token')

    if not accion:
        return {"solicitud": "GET", "result": {"error": "¡Qué pasa, compa! No me dijiste qué hacer, ¿qué busco?"}}, 400
    if not solicitud:
        return {"solicitud": "GET", "result": {"error": f"¡Falta algo, papu! Necesito más detalles para buscar, ¿qué quieres ver?"}}, 400

    solicitud = solicitud.lower()

    try:
        if accion == "buscar":
            # Limpiar la solicitud para obtener el nombre de la carpeta o término de búsqueda
            query_clean = solicitud.split("en")[-1].strip() if "en" in solicitud else solicitud.split("de")[-1].strip()

            # Buscar la carpeta directamente por nombre
            folder_url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{query_clean}"
            headers = {
                'Authorization': f"Bearer {onedrive_token}",
                'Accept': 'application/json'
            }

            folder_response = requests.get(folder_url, headers=headers)
            if folder_response.status_code == 404:
                return {"solicitud": "GET", "result": {"message": f"📂 No encontré la carpeta '{query_clean}' en OneDrive."}}, 200

            folder_response.raise_for_status()
            folder_data = folder_response.json()
            folder_id = folder_data.get("id")

            if not folder_id:
                return {"solicitud": "GET", "result": {"error": "No se pudo obtener el ID de la carpeta"}}, 500

            # Buscar archivos dentro de la carpeta
            files_url = f"https://graph.microsoft.com/v1.0/me/drive/items/{folder_id}/children"
            files_response = requests.get(files_url, headers=headers)

            if files_response.status_code != 200:
                return {"solicitud": "GET", "result": {"error": "Error al obtener archivos de la carpeta"}}, files_response.status_code

            files = files_response.json().get('value', [])

            if not files:
                return {"solicitud": "GET", "result": {"message": f"📂 No se encontraron archivos en la carpeta '{query_clean}'."}}, 200

            # Procesar resultados
            search_results = [
                {
                    "name": file.get('name', 'Sin nombre'),
                    "type": file.get('file', {}).get('mimeType', 'Desconocido'),
                    "url": file.get('@microsoft.graph.downloadUrl', None),
                    "id": file.get('id')  # Añadí el ID para posibles acciones futuras
                } for file in files
            ]

            return {"solicitud": "GET", "result": {"message": f"¡Órale, papu! Encontré {len(search_results)} archivos en '{query_clean}' 📄", "data": search_results}}, 200

        else:
            return {"solicitud": "GET", "result": {"error": f"¡No entendí qué quieres con '{accion}'! Usa 'buscar', ¿va?"}}, 400

    except requests.RequestException as e:
        return {"solicitud": "GET", "result": {"error": f"¡Ay, qué mala onda! Falló la conexión con OneDrive: {str(e)}"}}, 500
    except Exception as e:
        return {"solicitud": "GET", "result": {"error": f"¡Uy, se puso feo! Error inesperado: {str(e)}"}}, 500