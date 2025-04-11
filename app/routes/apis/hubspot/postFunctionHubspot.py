import requests
import re

def handle_post_request(accion, solicitud, email, user):
    """
    Maneja solicitudes POST para HubSpot, como crear, actualizar o eliminar contactos.
    :param accion: Acción detectada (e.g., "crear", "actualizar", "eliminar").
    :param solicitud: Detalles específicos de la solicitud (e.g., "contacto Juan").
    :param email: Email del usuario.
    :param user: Datos del usuario desde la base de datos.
    :return: Tupla con resultado en formato {"result": {...}} y código de estado HTTP.
    """
    try:
        hubspot_token = user.get('integrations', {}).get('hubspot', {}).get('token')
        if not hubspot_token:
            return {"result": {"message": "¡Ey! No tengo tu token de HubSpot, ¿me das permisos? 🔑"}}, 400

        headers = {'Authorization': f"Bearer {hubspot_token}", 'Content-Type': 'application/json'}

        if accion == "crear":
            match = re.search(r'contacto\s*(.+)', solicitud, re.IGNORECASE)
            if match:
                contact_name = match.group(1).strip()
                url = "https://api.hubapi.com/crm/v3/objects/contacts"
                name_parts = contact_name.split(" ", 1)
                payload = {
                    "properties": {
                        "firstname": name_parts[0],
                        "lastname": name_parts[1] if len(name_parts) > 1 else ""
                    }
                }
                response = requests.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return {"result": {"message": f"📇 Contacto '{contact_name}' creado con éxito 🚀"}}, 200
            return {"result": {"message": "Falta el nombre del contacto, ¿me lo aclaras?"}}, 400

        elif accion in ["actualizar", "eliminar"]:
            match = re.search(r'contacto\s*"(.+?)"', solicitud, re.IGNORECASE)
            if not match:
                return {"result": {"message": "Falta el nombre del contacto, ¿cuál modifico o elimino?"}}, 400
            contact_name = match.group(1).strip()

            search_url = "https://api.hubapi.com/crm/v3/objects/contacts"
            response = requests.get(search_url, headers=headers)
            response.raise_for_status()
            contacts = response.json().get('results', [])
            contact_id = next(
                (c["id"] for c in contacts if f"{c['properties'].get('firstname', '')} {c['properties'].get('lastname', '')}".strip().lower() == contact_name.lower()),
                None
            )
            if not contact_id:
                return {"result": {"message": f"📭 No encontré el contacto '{contact_name}'"}}, 404

            url = f"https://api.hubapi.com/crm/v3/objects/contacts/{contact_id}"
            if accion == "actualizar":
                update_match = re.search(r'con\s*(.+)', solicitud, re.IGNORECASE)
                update_content = update_match.group(1).strip() if update_match else "Datos actualizados"
                payload = {"properties": {"company": update_content}}
                response = requests.patch(url, headers=headers, json=payload)
                response.raise_for_status()
                return {"result": {"message": f"✨ Contacto '{contact_name}' actualizado con '{update_content}'"}}, 200
            elif accion == "eliminar":
                response = requests.delete(url, headers=headers)
                response.raise_for_status()
                return {"result": {"message": f"🗑️ Contacto '{contact_name}' eliminado con éxito"}}, 200

        return {"result": {"message": "Acción no soportada para POST en HubSpot"}}, 400

    except requests.RequestException as e:
        return {"result": {"message": f"¡Ay, qué mala onda! Error con HubSpot: {str(e)}"}}, 500
    except Exception as e:
        return {"result": {"message": f"¡Se puso feo! Error inesperado: {str(e)}"}}, 500