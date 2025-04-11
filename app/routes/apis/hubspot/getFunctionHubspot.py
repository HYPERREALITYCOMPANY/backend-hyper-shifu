import requests

def handle_get_request(accion, solicitud, email, user):
    """
    Maneja solicitudes GET para HubSpot, como buscar contactos, deals o compañías.
    :param accion: Acción detectada (e.g., "buscar").
    :param solicitud: Detalles específicos de la solicitud (e.g., "contactos de mi lista", "negocios de Juan").
    :param email: Email del usuario.
    :param user: Datos del usuario desde la base de datos.
    :return: Tupla con resultado en formato {"result": {...}} y código de estado HTTP.
    """
    try:
        hubspot_token = user.get('integrations', {}).get('hubspot', {}).get('token')
        if not hubspot_token:
            return {"result": {"message": "¡Ey! No tengo tu token de HubSpot, ¿me das permisos? 🔑"}}, 400

        headers = {'Authorization': f"Bearer {hubspot_token}", 'Content-Type': 'application/json'}

        if accion == "buscar":
            solicitud_lower = solicitud.lower()

            # Buscar todos los contactos
            if "todos mis contactos" in solicitud_lower:
                search_data = {
                    "filters": [],
                    "properties": ["firstname", "lastname", "email", "hubspot_owner_id", "company"]
                }
                response = requests.post(
                    "https://api.hubapi.com/crm/v3/objects/contacts/search",
                    headers=headers,
                    json=search_data
                )
                response.raise_for_status()
                contacts = response.json().get('results', [])
                results = [
                    {
                        "contact_name": f"{c['properties'].get('firstname', 'N/A')} {c['properties'].get('lastname', 'N/A')}".strip(),
                        "email": c["properties"].get("email", "N/A"),
                        "id": c["id"]
                    }
                    for c in contacts
                ]
                if not results:
                    return {"result": {"message": "📭 No encontré contactos, ¿estás seguro de que tienes alguno?"}}, 200
                return {"result": {"message": f"¡Órale! Encontré {len(results)} contactos 📇", "data": results}}, 200

            # Buscar contactos
            elif "contactos de" in solicitud_lower:
                search_term = solicitud.split("contactos de")[-1].strip()
                search_data = {
                    "filters": [{"propertyName": "email", "operator": "CONTAINS", "value": search_term}] if search_term else [],
                    "properties": ["firstname", "lastname", "email", "phone", "company", "hubspot_owner_id"]
                }
                response = requests.post(
                    "https://api.hubapi.com/crm/v3/objects/contacts/search",
                    headers=headers,
                    json=search_data
                )
                response.raise_for_status()
                contacts = response.json().get('results', [])
                results = [
                    {
                        "contact_name": f"{c['properties'].get('firstname', 'N/A')} {c['properties'].get('lastname', 'N/A')}".strip(),
                        "email": c["properties"].get("email", "N/A"),
                        "id": c["id"]
                    }
                    for c in contacts
                ]
                if not results:
                    return {"result": {"message": f"📭 No encontré contactos para '{search_term}'"}}, 200
                return {"result": {"message": f"¡Órale! Encontré {len(results)} contactos para '{search_term}' 📇", "data": results}}, 200

            # Buscar negocios (deals)
            elif "negocios de" in solicitud_lower or "negocio" in solicitud_lower:
                search_term = solicitud.split("negocios de")[-1].strip() if "negocios de" in solicitud_lower else solicitud.split("negocio")[-1].strip()
                search_data = {
                    "filters": [{"propertyName": "dealname", "operator": "CONTAINS", "value": search_term}] if search_term else [],
                    "properties": ["dealname", "amount", "dealstage", "hubspot_owner_id", "company"]
                }
                response = requests.post(
                    "https://api.hubapi.com/crm/v3/objects/deals/search",
                    headers=headers,
                    json=search_data
                )
                response.raise_for_status()
                stage_mapping = {
                    "qualifiedtobuy": "Calificado para comprar",
                    "appointmentscheduled": "Cita programada",
                    "noactivity": "Sin actividad",
                    "presentationscheduled": "Presentación programada",
                    "quoteaccepted": "Propuesta aceptada",
                    "contractsent": "Contrato enviado",
                    "closedwon": "Cierre ganado",
                    "closedlost": "Cierre perdido"
                }
                deals = response.json().get('results', [])
                results = [
                    {
                        "deal_name": d["properties"].get("dealname", "N/A"),
                        "amount": d["properties"].get("amount", "N/A"),
                        "stage": stage_mapping.get(d["properties"].get("dealstage", "N/A"), "N/A"),
                        "id": d["id"]
                    }
                    for d in deals
                ]
                if not results:
                    return {"result": {"message": f"📉 No encontré negocios para '{search_term}'"}}, 200
                return {"result": {"message": f"¡Órale! Encontré {len(results)} negocios para '{search_term}' 📉", "data": results}}, 200

            # Buscar empresas (companies)
            elif "empresas de" in solicitud_lower or "compañia" in solicitud_lower or "empresa" in solicitud_lower:
                search_term = solicitud.split("empresas de")[-1].strip() if "empresas de" in solicitud_lower else solicitud.split("compañia")[-1].strip() if "compañia" in solicitud_lower else solicitud.split("empresa")[-1].strip()
                search_data = {
                    "filters": [{"propertyName": "name", "operator": "CONTAINS", "value": search_term}] if search_term else [],
                    "properties": ["name", "industry", "size", "hubspot_owner_id"]
                }
                response = requests.post(
                    "https://api.hubapi.com/crm/v3/objects/companies/search",
                    headers=headers,
                    json=search_data
                )
                response.raise_for_status()
                companies = response.json().get('results', [])
                results = [
                    {
                        "company_name": c["properties"].get("name", "N/A"),
                        "industry": c["properties"].get("industry", "N/A"),
                        "id": c["id"]
                    }
                    for c in companies
                ]
                if not results:
                    return {"result": {"message": f"🏢 No encontré empresas para '{search_term}'"}}, 200
                return {"result": {"message": f"¡Órale! Encontré {len(results)} empresas para '{search_term}' 🏢", "data": results}}, 200

            else:
                return {"result": {"message": "No entendí bien qué buscar, ¿me das más detalles? (contactos, negocios o empresas)"}}, 400
        else:
            return {"result": {"message": "Acción no soportada para GET en HubSpot"}}, 400

    except requests.RequestException as e:
        return {"result": {"message": f"¡Ay, qué mala onda! Error con HubSpot: {str(e)}"}}, 500
    except Exception as e:
        return {"result": {"message": f"¡Se puso feo! Error inesperado: {str(e)}"}}, 500