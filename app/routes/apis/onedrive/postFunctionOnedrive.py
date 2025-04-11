import re
import requests

def handle_post_request(accion, solicitud, email, user):
    if not user:
        return {"solicitud": "POST", "result": {"error": "No te encontré en la base de datos, ¿estás seguro de que estás registrado?"}}, 404

    onedrive_integration = user.get('integrations', {}).get('onedrive', None)  # Cambié 'OneDrive' a 'onedrive'
    if not onedrive_integration or not onedrive_integration.get('token'):
        return {"solicitud": "POST", "result": {"error": "No tengo tu token de OneDrive, ¿puedes darme permisos nuevamente?"}}, 400
    onedrive_token = onedrive_integration.get('token')

    headers = {"Authorization": f"Bearer {onedrive_token}", "Content-Type": "application/json"}

    if not accion:
        return {"solicitud": "POST", "result": {"error": "No me indicaste qué hacer, ¿en qué puedo ayudarte?"}}, 400
    if not solicitud:
        return {"solicitud": "POST", "result": {"error": "Necesito más detalles para proceder, ¿qué te gustaría hacer?"}}, 400

    solicitud = solicitud.lower()
    try:
        # Eliminar archivo
        if accion == "eliminar":
            match = re.search(r'archivo\s*([\w\.\-_]+)', solicitud, re.IGNORECASE)  # Ej. "eliminar archivo doc1.txt"
            if not match:
                return {"solicitud": "POST", "result": {"message": "🗑️ ¡Falta algo! Dime qué archivo eliminar (ej. 'eliminar archivo doc1.txt') 🚀"}}, 200
            file_name = match.group(1).strip()

            # Buscar archivo en OneDrive
            search_url = f"https://graph.microsoft.com/v1.0/me/drive/root/search(q='{file_name}')"
            response = requests.get(search_url, headers=headers)
            if response.status_code == 401:
                return {"solicitud": "POST", "result": {"error": "No autorizado. Verifica el token de acceso."}}, 401

            response.raise_for_status()
            results = response.json().get('value', [])

            file_id = None
            for result in results:
                onedrive_file_name = result['name']
                onedrive_file_id = result['id']
                if onedrive_file_name.lower().startswith(file_name.lower()):
                    file_id = onedrive_file_id
                    break

            if not file_id:
                return {"solicitud": "POST", "result": {"error": f"Archivo '{file_name}' no encontrado en OneDrive"}}, 404

            # Mover el archivo a la papelera
            move_to_trash_url = f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}"
            delete_response = requests.delete(move_to_trash_url, headers=headers)
            if delete_response.status_code == 401:
                return {"solicitud": "POST", "result": {"error": "No autorizado. Verifica el token de acceso."}}, 401

            delete_response.raise_for_status()
            return {"solicitud": "POST", "result": {"message": f"🗑️ El archivo '{file_name}' ha sido movido a la papelera en OneDrive con éxito! 🚀"}}, 200

        # Espacio para otras acciones (subir, actualizar) si las añades después
        else:
            return {"solicitud": "POST", "result": {"error": f"No entendí '{accion}', ¿puedes usar 'eliminar' por ahora?"}}, 400

    except requests.RequestException as e:
        return {"solicitud": "POST", "result": {"error": f"Lo siento, hubo un problema al conectar con OneDrive: {str(e)}"}}, 500
    except Exception as e:
        return {"solicitud": "POST", "result": {"error": f"Ups, algo salió mal inesperadamente: {str(e)}"}}, 500