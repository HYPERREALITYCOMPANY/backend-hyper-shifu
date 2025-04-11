from datetime import datetime, timedelta
import re
from config import Config
from zoneinfo import ZoneInfo
from email.mime.text import MIMEText
import base64
import json
import requests
import openai
openai.api_key = Config.CHAT_API_KEY

def analyze_request(solicitud):
    """Analiza la solicitud con IA para extraer destinatario, asunto y cuerpo."""
    prompt = f"""
    Eres un asistente inteligente que analiza solicitudes para enviar correos. Dada la solicitud: "{solicitud}", identifica:
    - Destinatario (correo o nombre de usuario)
    - Asunto (tema del correo)
    - Cuerpo (mensaje dado en la solicitud)
    
    Devuelve un JSON con "destinatario", "asunto", "cuerpo". Usa null si algo no está claro.
    """
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150
        )
        return json.loads(response.choices[0].message.content.strip())
    except Exception as e:
        return {"destinatario": None, "asunto": None, "cuerpo": None, "error": str(e)}
    
def analyze_event_request(solicitud):
    """Analiza la solicitud de agendar un evento con IA."""
    prompt = f"""
    Eres un asistente inteligente que analiza solicitudes para agendar eventos en Google Calendar. Dada la solicitud: "{solicitud}", identifica:
    - Título del evento (summary, ej. "Reunión con equipo")
    - Asistentes (correos o nombres, separados por comas si hay varios)
    - Fecha y hora de inicio (ej. "mañana a las 11 am", "hoy 15:00")
    - Fecha y hora de fin (si se menciona, ej. "hasta las 12 pm", de lo contrario null)
    
    Devuelve un JSON con "titulo", "asistentes", "inicio", "fin". Usa null si algo no está claro o falta. Si no hay suficiente información para el inicio, indica qué falta en "falta".
    Ejemplos:
    - "Agendar reunión mañana a las 11 con Juan" → {{"titulo": "reunión", "asistentes": "Juan", "inicio": "mañana a las 11", "fin": null}}
    - "Agendar cita con Ana y Luis hoy a las 14:00 hasta las 15:00" → {{"titulo": "cita", "asistentes": "Ana, Luis", "inicio": "hoy a las 14:00", "fin": "hoy a las 15:00"}}
    - "Agendar evento" → {{"titulo": null, "asistentes": null, "inicio": null, "fin": null, "falta": "cuándo empezar el evento"}}
    """
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200
        )
        return json.loads(response.choices[0].message.content.strip())
    except Exception as e:
        return {"titulo": None, "asistentes": None, "inicio": None, "fin": None, "falta": f"Error al analizar: {str(e)}"}

def generate_email_body(tema):
    """Genera un cuerpo de correo con IA basado en el tema proporcionado."""
    prompt = f"""
    Redacta un mensaje breve y natural (máximo 100 palabras) sobre '{tema}'. Usa un tono profesional pero amigable, como si escribieras a un colega. Solo el cuerpo, sin saludos ni despedidas.
    """
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Hubo un problema al generar el mensaje: {str(e)}"

def handle_post_request(accion, solicitud, email, user):
    if not user:
        return {"solicitud": "POST", "result": {"error": "No te encontré en la base de datos, ¿estás seguro de que estás registrado?"}}, 404

    gmail_integration = user.get('integrations', {}).get('Gmail', None)
    if not gmail_integration or not gmail_integration.get('token'):
        return {"solicitud": "POST", "result": {"error": "No tengo tu token de Gmail, ¿puedes darme permisos nuevamente?"}}, 400
    gmail_token = gmail_integration.get('token')

    headers = {"Authorization": f"Bearer {gmail_token}", "Content-Type": "application/json"}
    user_timezone = "America/Mexico_City"

    if not accion:
        return {"solicitud": "POST", "result": {"error": "No me indicaste qué hacer, ¿en qué puedo ayudarte?"}}, 400
    if not solicitud:
        return {"solicitud": "POST", "result": {"error": "Necesito más detalles para proceder, ¿qué te gustaría hacer?"}}, 400

    solicitud = solicitud.lower()
    try:
        # Enviar correo
        if accion == "enviar":
            analysis = analyze_request(solicitud)
            destinatario = analysis.get("destinatario")
            asunto = analysis.get("asunto")
            cuerpo = analysis.get("cuerpo")

            if not destinatario:
                return {"solicitud": "POST", "result": {"message": "📩 ¡Falta algo! Dime a quién enviar el correo para continuar 🚀"}}, 200

            if "@" not in destinatario:
                destinatario = f"{destinatario}@gmail.com"
            elif not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', destinatario):
                return {"solicitud": "POST", "result": {"error": "El correo no parece válido, ¿puedes revisarlo?"}}, 400

            asunto = asunto if asunto else "Mensaje desde Shifu"
            generar_cuerpo = any(phrase in solicitud for phrase in ["genera un mensaje", "crea el cuerpo", "con un mensaje creado"])
            if generar_cuerpo:
                tema = f"{asunto} {cuerpo or ''}".strip()
                cuerpo = generate_email_body(tema)
            elif not cuerpo:
                cuerpo = "Te envío un mensaje rápido desde Shifu, ¡espero que estés bien!"
            else:
                cuerpo = cuerpo

            mensaje = MIMEText(cuerpo)
            mensaje["To"] = destinatario
            mensaje["Subject"] = asunto
            mensaje["From"] = "me"
            raw = base64.urlsafe_b64encode(mensaje.as_bytes()).decode()
            url = "https://www.googleapis.com/gmail/v1/users/me/messages/send"
            response = requests.post(url, json={"raw": raw}, headers=headers)
            response.raise_for_status()
            return {"solicitud": "POST", "result": {"message": f"📩 ¡Correo enviado a {destinatario} con asunto '{asunto}'! 🚀"}}, 200

        # Crear borrador
        elif accion == "crear":
            match = re.search(r'(borrador|draft|correo)(?:\s*(?:para|a)\s*([\w\.-@,\s]+))?(?:\s*con\s*(?:el)?\s*asunto\s*:?\s*(.*?))?(?:\s*y\s*cuerpo\s*:?\s*(.*))?', solicitud, re.IGNORECASE)
            if not match:
                return {"solicitud": "POST", "result": {"message": "📩 ¡Falta algo! Dime qué crear (ej. un borrador) y para quién 🚀"}}, 200

            destinatario = match.group(2).strip() if match.group(2) else None
            asunto = match.group(3).strip() if match.group(3) else "Borrador creado por Shifu"
            cuerpo = match.group(4).strip() if match.group(4) else "Aquí tienes un borrador para que lo completes."

            mensaje = MIMEText(cuerpo)
            destinatario_msg = ""
            if destinatario:
                if "@" not in destinatario:
                    destinatario = f"{destinatario}@gmail.com"
                elif not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', destinatario):
                    return {"solicitud": "POST", "result": {"error": "El correo no parece válido, ¿puedes revisarlo?"}}, 400
                mensaje["To"] = destinatario
                destinatario_msg = f" para {destinatario}"

            mensaje["Subject"] = asunto
            raw = base64.urlsafe_b64encode(mensaje.as_bytes()).decode()
            borrador = {"message": {"raw": raw}}
            url = "https://www.googleapis.com/gmail/v1/users/me/drafts"
            response = requests.post(url, json=borrador, headers=headers)
            response.raise_for_status()
            return {"solicitud": "POST", "result": {"message": f"📩 ¡Borrador creado{destinatario_msg} con asunto '{asunto}' ya está en Gmail! 🚀"}}, 200

        # Eliminar correos
        elif accion == "eliminar":
            match = re.search(r'(correos|emails)\s*de\s*([\w\.-]+@[\w\.-]+|\w+)', solicitud, re.IGNORECASE)
            if not match:
                return {"solicitud": "POST", "result": {"message": "📩 ¡Falta algo! Dime de quién eliminar los correos 🚀"}}, 200
            sender = match.group(2).strip()
            list_url = "https://www.googleapis.com/gmail/v1/users/me/messages"
            params = {"q": f"from:{sender}", "maxResults": 5}
            list_response = requests.get(list_url, headers=headers, params=params)
            list_response.raise_for_status()
            messages = list_response.json().get("messages", [])
            if not messages:
                return {"solicitud": "POST", "result": {"message": f"📭 No encontré correos de '{sender}' para eliminar."}}, 200
            delete_results = []
            for msg in messages:
                delete_url = f"{list_url}/{msg['id']}/trash"
                response = requests.post(delete_url, headers=headers)
                if response.status_code == 200:
                    delete_results.append(msg["id"])
            return {"solicitud": "POST", "result": {"message": f"📩 ¡He movido {len(delete_results)} correos de '{sender}' a la papelera! 🗑️"}}, 200

        # Mover a spam
        elif accion == "mover":
            match = re.search(r'de\s*([\w\.-]+@[\w\.-]+|\w+)', solicitud, re.IGNORECASE)
            if not match:
                return {"solicitud": "POST", "result": {"message": "📩 ¡Falta algo! Dime de quién mover los correos a spam 🚀"}}, 200
            sender = match.group(1).strip()
            list_url = "https://www.googleapis.com/gmail/v1/users/me/messages"
            params = {"q": f"from:{sender}", "maxResults": 5}
            list_response = requests.get(list_url, headers=headers, params=params)
            list_response.raise_for_status()
            messages = list_response.json().get("messages", [])
            if not messages:
                return {"solicitud": "POST", "result": {"message": f"📭 No encontré correos de '{sender}' para mover a spam."}}, 200
            spam_results = []
            for msg in messages:
                modify_url = f"{list_url}/{msg['id']}/modify"
                payload = {"addLabelIds": ["SPAM"]}
                response = requests.post(modify_url, json=payload, headers=headers)
                if response.status_code == 200:
                    spam_results.append(msg["id"])
            return {"solicitud": "POST", "result": {"message": f"📩 ¡He movido {len(spam_results)} correos de '{sender}' a spam! 🚫"}}, 200

        # Agendar evento
        elif accion == "agendar":
            analysis = analyze_event_request(solicitud)
            summary = analysis.get("titulo") or "Reunión por defecto"
            attendees_str = analysis.get("asistentes")
            start_str = analysis.get("inicio")
            end_str = analysis.get("fin")
            falta = analysis.get("falta")

            if falta or not start_str:
                return {"solicitud": "POST", "result": {"message": f"📩 ¡Falta algo! Dime {falta or 'cuándo empezar el evento'} (ej. 'mañana a las 11 am') 🚀"}}, 200

            def parse_datetime(dt_str, base_date=None):
                try:
                    parts = dt_str.lower().split()
                    day_part = parts[0] if parts[0] in ["hoy", "mañana"] else "hoy"
                    time_part = parts[2] if parts[1] in ["a", "las"] else parts[1] if len(parts) > 1 else parts[0]
                    am_pm = parts[-1] if parts[-1] in ["am", "pm"] else "am"
                    now = datetime.now(tz=ZoneInfo(user_timezone))
                    base_date = now + timedelta(days=1) if day_part == "mañana" else now
                    hour, minute = (int(time_part.split(":")[0]), int(time_part.split(":")[1])) if ":" in time_part else (int(time_part), 0)
                    if am_pm == "pm" and hour != 12:
                        hour += 12
                    elif am_pm == "am" and hour == 12:
                        hour = 0
                    return base_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                except Exception:
                    return None

            start_dt = parse_datetime(start_str)
            if not start_dt:
                return {"solicitud": "POST", "result": {"message": "📩 ¡Falta algo! No entendí la fecha de inicio, ¿puedes darla como 'mañana a las 11 am'? 🚀"}}, 200
            end_dt = parse_datetime(end_str) if end_str else start_dt + timedelta(hours=1)
            if end_dt <= start_dt:
                end_dt = start_dt + timedelta(hours=1)

            event = {
                "summary": summary,
                "start": {"dateTime": start_dt.isoformat(), "timeZone": user_timezone},
                "end": {"dateTime": end_dt.isoformat(), "timeZone": user_timezone},
                "conferenceData": {
                    "createRequest": {
                        "requestId": f"meet-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        "conferenceSolutionKey": {"type": "hangoutsMeet"}
                    }
                }
            }
            if attendees_str:
                event["attendees"] = [{"email": email.strip() if "@" in email else f"{email.strip()}@gmail.com"} for email in attendees_str.split(",")]

            url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
            response = requests.post(url, json=event, headers=headers, params={"conferenceDataVersion": 1, "sendNotifications": True})
            response.raise_for_status()
            json_response = response.json()
            hangout_link = json_response.get("hangoutLink", "No se generó enlace de Meet")
            start_formatted = start_dt.strftime("%d/%m/%Y a las %H:%M")
            attendees_msg = f"\nAsistentes: {attendees_str}" if attendees_str else ""
            return {"solicitud": "POST", "result": {"message": f"📩 ¡Reunión '{summary}' agendada para el {start_formatted}!\nEnlace de Meet: {hangout_link}{attendees_msg} 🚀"}}, 200
        # Marcar como leído/no leído
        elif accion == "marcar":
            match = re.search(r'como\s*(leído|no leído)\s*(correos|emails)\s*de\s*([\w\.-]+@[\w\.-]+|\w+)', solicitud, re.IGNORECASE)
            if not match:
                return {"solicitud": "POST", "result": {"message": "📩 ¡Falta algo! Dime qué marcar (leído/no leído) y de quién son los correos 🚀"}}, 200
            estado = match.group(1).lower()
            sender = match.group(3).strip()
            list_url = "https://www.googleapis.com/gmail/v1/users/me/messages"
            params = {"q": f"from:{sender}", "maxResults": 5}
            list_response = requests.get(list_url, headers=headers, params=params)
            list_response.raise_for_status()
            messages = list_response.json().get("messages", [])
            if not messages:
                return {"solicitud": "POST", "result": {"message": f"📭 No encontré correos de '{sender}' para marcar como {estado}."}}, 200
            marked_results = []
            label_action = {"removeLabelIds": ["UNREAD"]} if estado == "leído" else {"addLabelIds": ["UNREAD"]}
            for msg in messages:
                modify_url = f"{list_url}/{msg['id']}/modify"
                response = requests.post(modify_url, json=label_action, headers=headers)
                if response.status_code == 200:
                    marked_results.append(msg["id"])
            estado_str = "leídos" if estado == "leído" else "no leídos"
            return {"solicitud": "POST", "result": {"message": f"📩 ¡He marcado {len(marked_results)} correos de '{sender}' como {estado_str}! 🚀"}}, 200

        # Archivar correos
        elif accion == "archivar":
            match = re.search(r'(correos|emails)\s*de\s*([\w\.-]+@[\w\.-]+|\w+)', solicitud, re.IGNORECASE)
            if not match:
                return {"solicitud": "POST", "result": {"message": "📩 ¡Falta algo! Dime de quién archivar los correos 🚀"}}, 200
            sender = match.group(2).strip()
            list_url = "https://www.googleapis.com/gmail/v1/users/me/messages"
            params = {"q": f"from:{sender}", "maxResults": 5}
            list_response = requests.get(list_url, headers=headers, params=params)
            list_response.raise_for_status()
            messages = list_response.json().get("messages", [])
            if not messages:
                return {"solicitud": "POST", "result": {"message": f"📭 No encontré correos de '{sender}' para archivar."}}, 200
            archived_results = []
            for msg in messages:
                modify_url = f"{list_url}/{msg['id']}/modify"
                payload = {"removeLabelIds": ["INBOX"]}
                response = requests.post(modify_url, json=payload, headers=headers)
                if response.status_code == 200:
                    archived_results.append(msg["id"])
            return {"solicitud": "POST", "result": {"message": f"📩 ¡He archivado {len(archived_results)} correos de '{sender}'! 🗂️🚀"}}, 200

        # Responder correo
        elif accion == "responder":
            match = re.search(r'(correo|email)\s*de\s*([\w\.-]+@[\w\.-]+|\w+)(?:\s*con\s*cuerpo:\s*(.*))?', solicitud, re.IGNORECASE)
            if not match:
                return {"solicitud": "POST", "result": {"message": "📩 ¡Falta algo! Dime de quién es el correo al que quieres responder 🚀"}}, 200
            sender = match.group(2).strip()
            cuerpo = match.group(3).strip() if match.group(3) else "¡Gracias por tu mensaje! Te respondo rápidamente desde Shifu."
            list_url = "https://www.googleapis.com/gmail/v1/users/me/messages"
            params = {"q": f"from:{sender}", "maxResults": 1}
            list_response = requests.get(list_url, headers=headers, params=params)
            list_response.raise_for_status()
            messages = list_response.json().get("messages", [])
            if not messages:
                return {"solicitud": "POST", "result": {"message": f"📭 No encontré correos recientes de '{sender}' para responder."}}, 200
            message_id = messages[0]["id"]
            msg_response = requests.get(f"{list_url}/{message_id}", headers=headers)
            msg_response.raise_for_status()
            msg_data = msg_response.json()
            thread_id = msg_data["threadId"]
            headers_msg = msg_data.get('payload', {}).get('headers', [])
            subject = next((h['value'] for h in headers_msg if h['name'] == 'Subject'), "Sin asunto")
            mensaje = MIMEText(cuerpo)
            mensaje["To"] = sender if "@" in sender else f"{sender}@gmail.com"
            mensaje["Subject"] = f"Re: {subject}"
            mensaje["From"] = "me"
            raw = base64.urlsafe_b64encode(mensaje.as_bytes()).decode()
            url = "https://www.googleapis.com/gmail/v1/users/me/messages/send"
            response = requests.post(url, json={"raw": raw, "threadId": thread_id}, headers=headers)
            response.raise_for_status()
            return {"solicitud": "POST", "result": {"message": f"📩 ¡He respondido el correo de '{sender}' con asunto 'Re: {subject}'! 🚀"}}, 200

        else:
            return {"solicitud": "POST", "result": {"error": f"No entendí '{accion}', ¿puedes usar 'enviar', 'crear', 'eliminar', etc.?"}}, 400

    except requests.RequestException as e:
        return {"solicitud": "POST", "result": {"error": f"Lo siento, hubo un problema al conectar con Gmail: {str(e)}"}}, 500
    except Exception as e:
        return {"solicitud": "POST", "result": {"error": f"Ups, algo salió mal inesperadamente: {str(e)}"}}, 500