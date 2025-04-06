from datetime import datetime, timedelta
import requests

def handle_get_request(accion, solicitud, email, user):
    print(accion)
    print(solicitud)
    if not user:
        return {"solicitud": "GET", "result": {"error": "¡Órale! No te encontré en la base, ¿seguro que estás registrado?"}}, 404

    outlook_integration = user.get('integrations', {}).get('outlook', None)
    if not outlook_integration or not outlook_integration.get('token'):
        return {"solicitud": "GET", "result": {"error": "¡Ey! No tengo tu token de Outlook, ¿me das permisos otra vez?"}}, 400
    outlook_token = outlook_integration.get('token')

    headers = {'Authorization': f"Bearer {outlook_token}", 'Accept': 'application/json'}
    url = "https://graph.microsoft.com/v1.0/me/messages"

    if not accion:
        return {"solicitud": "GET", "result": {"error": "¡Qué pasa, compa! No me dijiste qué hacer, ¿qué busco?"}}, 400
    if not solicitud:
        return {"solicitud": "GET", "result": {"error": f"¡Falta algo! Necesito más detalles para buscar, ¿qué quieres ver?"}}, 400

    solicitud = solicitud.lower()

    try:
        if accion == "buscar":
            if any(palabra in solicitud for palabra in ["ultimo", "último"]):
                # Caso 1: Último correo genérico (sin remitente específico)
                if any(palabra in solicitud for palabra in ["mi", "mí", "mis"]) and "de" not in solicitud:
                    params = {"$top": 1, "$filter": "isDraft eq false"}
                    search_type = "último correo"
                # Caso 2: Último correo de un remitente específico
                elif "de" in solicitud:
                    sender = solicitud.split("de")[-1].strip()
                    if not sender:
                        return {"solicitud": "GET", "result": {"error": "¡Ey! ¿De quién quieres el último correo? Dame un nombre o correo."}}, 400
                    params = {"$top": 1, "$filter": f"from/emailAddress/address eq '{sender}'"}
                    search_type = f"último correo de '{sender}'"
                else:
                    return {"solicitud": "GET", "result": {"error": "¡Uy! Si quieres el último correo, dime 'mi último correo' o 'último correo de alguien', ¿va?"}}, 400
            else:
                # Búsqueda normal (sin "último")
                if "correos" in solicitud or "email" in solicitud:
                    if "de" in solicitud:
                        sender = solicitud.split("de")[-1].strip()
                        if not sender:
                            return {"solicitud": "GET", "result": {"error": "¡Ey! ¿De quién quieres los correos? Dame un nombre o correo."}}, 400
                        params = {"$top": 5, "$filter": f"from/emailAddress/address eq '{sender}'"}
                        search_type = f"correos de '{sender}'"
                    else:
                        query = solicitud.replace("correos", "").replace("email", "").strip()
                        if not query:
                            return {"solicitud": "GET", "result": {"error": "¡Ey! Dame algo para buscar en los correos, ¿qué quieres encontrar?"}}, 400
                        params = {"$top": 5, "$search": f"\"{query}\""}
                        search_type = f"correos sobre '{query}'"
                elif "eventos" in solicitud or "reuniones" in solicitud:
                    url = "https://graph.microsoft.com/v1.0/me/events"
                    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
                    params = {"$top": 5, "$filter": f"start/dateTime ge '{tomorrow}T00:00:00Z' and end/dateTime le '{tomorrow}T23:59:59Z'"}
                    if "de" in solicitud:
                        attendee = solicitud.split("de")[-1].strip()
                        params["$filter"] += f" and attendees/any(a:a/emailAddress/address eq '{attendee}')"
                    search_type = "eventos de mañana"
                else:
                    query = solicitud.strip()
                    if not query:
                        return {"solicitud": "GET", "result": {"error": "¡Ey! Dame algo para buscar, ¿qué quieres encontrar?"}}, 400
                    params = {"$top": 5, "$search": f"\"{query}\""}
                    search_type = f"correos sobre '{query}'"

            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()

            if "events" in url:
                events = response.json().get('value', [])
                if not events:
                    return {"solicitud": "GET", "result": {"message": "📅 ¡Nada para mañana, compa! Estás libre como el viento 🌬️"}}, 200
                results = [
                    {
                        'summary': event["subject"],
                        'start': event["start"]["dateTime"],
                        'link': event.get("webLink", "Sin enlace")
                    } for event in events
                ]
                return {"solicitud": "GET", "result": {"message": f"¡Listo! {len(results)} eventos para mañana 📆", "data": results}}, 200
            else:
                messages = response.json().get('value', [])
                if not messages:
                    return {"solicitud": "GET", "result": {"message": f"📭 No encontré {search_type}, ¿será que no hay nada?"}}, 200

                search_results = []
                for message in messages:
                    sender = message['from']['emailAddress']['address'] if message.get('from') else "Sin remitente"
                    date = message.get('receivedDateTime', "Sin fecha")
                    subject = message.get('subject', "Sin asunto")
                    body = message.get('bodyPreview', "Sin vista previa")[:200] + "..." if len(message.get('bodyPreview', "")) > 200 else message.get('bodyPreview', "")

                    search_results.append({
                        'from': sender,
                        'date': date,
                        'subject': subject,
                        'body': body,
                        'link': message.get('webLink', "Sin enlace")
                    })

                return {"solicitud": "GET", "result": {"message": f"¡Listo! Encontré {len(search_results)} {search_type} 📬", "data": search_results}}, 200

        else:
            return {"solicitud": "GET", "result": {"error": f"¡No entendí qué quieres con '{accion}'! Usa algo pa’ buscar, ¿va?"}}, 400

    except requests.RequestException as e:
        return {"solicitud": "GET", "result": {"error": f"¡Ay, qué mala onda! Falló la conexión con Outlook: {str(e)}"}}, 500
    except Exception as e:
        return {"solicitud": "GET", "result": {"error": f"¡Uy, se puso feo! Error inesperado: {str(e)}"}}, 500