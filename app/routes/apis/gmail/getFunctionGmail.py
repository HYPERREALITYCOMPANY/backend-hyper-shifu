from datetime import datetime, timedelta
import requests
import base64


def decode_message_body(encoded_body):
    return base64.urlsafe_b64decode(encoded_body).decode('utf-8')

def extract_text_from_html(html):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    return soup.get_text()
        
def handle_get_request(accion, solicitud, email, user):
    print(accion)
    print(solicitud)
    if not user:
        return {"solicitud": "GET", "result": {"error": "¡Órale! No te encontré en la base, ¿seguro que estás registrado?"}}, 404

    gmail_integration = user.get('integrations', {}).get('Gmail', None)
    if not gmail_integration or not gmail_integration.get('token'):
        return {"solicitud": "GET", "result": {"error": "¡Ey! No tengo tu token de Gmail, ¿me das permisos otra vez?"}}, 400
    gmail_token = gmail_integration.get('token')

    headers = {'Authorization': f"Bearer {gmail_token}"}
    url = "https://www.googleapis.com/gmail/v1/users/me/messages"

    if not accion:
        return {"solicitud": "GET", "result": {"error": "¡Qué pasa, compa! No me dijiste qué hacer, ¿qué busco?"}}, 400
    if not solicitud:
        return {"solicitud": "GET", "result": {"error": f"¡Falta algo, papu! Necesito más detalles para buscar, ¿qué quieres ver?"}}, 400

    solicitud = solicitud.lower()

    try:
        if accion == "buscar":
            if any(palabra in solicitud for palabra in ["ultimo", "último"]):
                if any(palabra in solicitud for palabra in ["mi", "mí", "mis"]) and "de" not in solicitud:
                    query = "is:inbox"
                    params = {"q": query, "maxResults": 1}
                    search_type = "último correo"
                elif " de " in solicitud:
                    sender = solicitud.split(" de ")[-1].strip()
                    if not sender:
                        return {"solicitud": "GET", "result": {"error": "¡Ey! ¿De quién quieres el último correo? Dame un nombre o correo."}}, 400
                    query = f"from:{sender}"
                    params = {"q": query, "maxResults": 1}
                    search_type = f"último correo de '{sender}'"
                else:
                    return {"solicitud": "GET", "result": {"error": "¡Uy! Si quieres el último correo, dime 'mi último correo' o 'último correo de alguien', ¿va?"}}, 400
            else:
                if any(p in solicitud for p in ["correos", "emails", "mensajes", "mails"]):
                    if " de " in solicitud:
                        sender = solicitud.split(" de ")[-1].strip()
                        if sender:
                            query = f"from:{sender}"
                            search_type = f"correos de '{sender}'"
                        else:
                            return {"solicitud": "GET", "result": {"error": "¡Ey! ¿De quién quieres los correos? Dame un nombre o correo."}}, 400
                    else:
                        posibles_temas = solicitud
                        for palabra in ["correos", "emails", "mensajes", "mails", "relacionados con", "sobre"]:
                            posibles_temas = posibles_temas.replace(palabra, "")
                        posibles_temas = posibles_temas.strip()
                        if not posibles_temas:
                            return {"solicitud": "GET", "result": {"error": "¡Ey! Dame algo pa’ buscar en los correos, ¿qué quieres encontrar?"}}, 400
                        query = posibles_temas
                        search_type = f"correos relacionados con '{query}'"

                    params = {"q": query, "maxResults": 5}
                elif "eventos" in solicitud or "reuniones" in solicitud:
                    url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
                    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
                    params = {
                        "timeMin": f"{tomorrow}T00:00:00Z",
                        "timeMax": f"{tomorrow}T23:59:59Z",
                        "maxResults": 5
                    }
                    if " de " in solicitud:
                        attendee = solicitud.split(" de ")[-1].strip()
                        params["q"] = attendee
                    search_type = "eventos de mañana"
                else:
                    query = solicitud.strip()
                    if not query:
                        return {"solicitud": "GET", "result": {"error": "¡Ey! Dame algo pa’ buscar, ¿qué quieres encontrar?"}}, 400
                    params = {"q": query, "maxResults": 5}
                    search_type = f"correos sobre '{query}'"

            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()

            if "events" in url:
                events = response.json().get('items', [])
                if not events:
                    return {"solicitud": "GET", "result": {"message": "📅 ¡Nada pa’ mañana, compa! Estás libre como el viento 🌬️"}}, 200
                results = [
                    {
                        'summary': event["summary"],
                        'start': event["start"]["dateTime"],
                        'link': event.get("htmlLink", "Sin enlace")
                    } for event in events
                ]
                return {"solicitud": "GET", "result": {"message": f"¡Aquí tienes, papu! {len(results)} eventos pa’ mañana 📆", "data": results}}, 200
            else:
                messages = response.json().get('messages', [])
                if not messages:
                    return {"solicitud": "GET", "result": {"message": f"📭 No encontré {search_type}, ¿será que no hay nada?"}}, 200

                search_results = []
                for message in messages:
                    message_id = message['id']
                    message_response = requests.get(f"{url}/{message_id}", headers=headers)
                    message_response.raise_for_status()

                    message_data = message_response.json()
                    message_headers = message_data.get('payload', {}).get('headers', [])
                    sender = next((h['value'] for h in message_headers if h['name'] == 'From'), "Sin remitente")
                    date = next((h['value'] for h in message_headers if h['name'] == 'Date'), "Sin fecha")
                    subject = next((h['value'] for h in message_headers if h['name'] == 'Subject'), "Sin asunto")

                    body = ""
                    if 'parts' in message_data['payload']:
                        for part in message_data['payload']['parts']:
                            if part['mimeType'] in ['text/plain', 'text/html']:
                                body = decode_message_body(part['body']['data'])
                                if part['mimeType'] == 'text/html':
                                    body = extract_text_from_html(body)
                                    break
                    elif message_data['payload'].get('body', {}).get('data'):
                        body = decode_message_body(message_data['payload']['body']['data'])

                    search_results.append({
                        'from': sender,
                        'date': date,
                        'subject': subject,
                        'body': body[:200] + "..." if len(body) > 200 else body,
                        'link': f"https://mail.google.com/mail/u/0/#inbox/{message_id}"
                    })

                return {"solicitud": "GET", "result": {"message": f"¡Órale, papu! Encontré {len(search_results)} {search_type} 📬", "data": search_results}}, 200

        else:
            return {"solicitud": "GET", "result": {"error": f"¡No entendí qué quieres con '{accion}'! Usa algo pa’ buscar, ¿va?"}}, 400

    except requests.RequestException as e:
        return {"solicitud": "GET", "result": {"error": f"¡Ay, qué mala onda! Falló la conexión con Gmail: {str(e)}"}}, 500
    except Exception as e:
        return {"solicitud": "GET", "result": {"error": f"¡Uy, se puso feo! Error inesperado: {str(e)}"}}, 500
