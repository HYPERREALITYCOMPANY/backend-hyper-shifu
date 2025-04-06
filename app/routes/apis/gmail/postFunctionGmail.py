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
    Eres un asistente inteligente que analiza solicitudes para enviar correos. Dada la siguiente solicitud: "{solicitud}", identifica:
    - Destinatario (correo o nombre de usuario)
    - Asunto (tema del correo)
    - Cuerpo (mensaje QUE ESTA DADO EN LA SOLICITUD)
    
    Devuelve la respuesta en formato JSON con estas claves: "destinatario", "asunto", "cuerpo".
    Si algo no está claro, usa null para esa clave. Asegúrate de que el resultado sea un JSON válido.
    """
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150
        )
        response_text = response.choices[0].message.content.strip()
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        return {"destinatario": None, "asunto": None, "cuerpo": None, "error": f"Error parsing JSON: {str(e)}"}
    except Exception as e:
        return {"destinatario": None, "asunto": None, "cuerpo": None, "error": str(e)}

def generate_email_body(tema):
    """Genera un cuerpo de correo con IA basado en el tema proporcionado."""
    prompt = f"""
    Eres un asistente útil y profesional. Redacta un mensaje de correo breve y natural (máximo 100 palabras) sobre el tema: '{tema}'. 
    Usa un tono amigable pero formal, como si escribieras a un colega o cliente. No incluyas saludos ni despedidas, solo el cuerpo.
    Ignora cualquier instrucción como "genera un mensaje" o "correo a" que no sea parte del contenido real del tema.
    NO MENCIONES QUE ESTAS GENERANDO O BUSCANDO GENERAR ESE MENSAJE SOLO GENERA COMO TAL EL MENSAJE
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
        return {"solicitud": "POST", "result": {"error": "¡Órale! No te encontré en la base, ¿seguro que estás registrado?"}}, 404

    gmail_integration = user.get('integrations', {}).get('Gmail', None)
    if not gmail_integration or not gmail_integration.get('token'):
        return {"solicitud": "POST", "result": {"error": "¡Ey! No tengo tu token de Gmail, ¿me das permisos otra vez?"}}, 400
    gmail_token = gmail_integration.get('token')

    headers = {"Authorization": f"Bearer {gmail_token}", "Content-Type": "application/json"}
    user_timezone = "America/Mexico_City"

    if not accion:
        return {"solicitud": "POST", "result": {"error": "¡Qué pasa, compa! No me dijiste qué hacer, ¿qué quieres?"}}, 400
    if not solicitud:
        return {"solicitud": "POST", "result": {"error": f"¡Falta algo, papu! Con '{accion}' necesito más detalles, ¿qué hago?"}}, 400

    solicitud = solicitud.lower()
    try:
                # Enviar correo
        # Enviar correo
        if accion == "enviar":
# Analizar la solicitud con IA
            analysis = analyze_request(solicitud)
            print("Análisis de la solicitud:", analysis)

            destinatario = analysis.get("destinatario")
            asunto = analysis.get("asunto")
            cuerpo = analysis.get("cuerpo", None)

            # Validar destinatario
            if not destinatario:
                return {"solicitud": "POST", "result": {"error": "¡Oops! 😅 ¿A quién le mando esto? Dame un correo válido o un nombre de usuario, porfa."}}, 400
            
            if "@" not in destinatario:
                destinatario = f"{destinatario}@gmail.com"
            elif not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', destinatario):
                return {"solicitud": "POST", "result": {"error": "¡Ey! Ese correo no se ve bien, ¿me das uno válido?"}}, 400

            # Asunto por defecto si no se especifica
            asunto = asunto if asunto else "Mensaje desde Shifu AI"

            # Verificar si el usuario pidió explícitamente generar el cuerpo
            generar_phrases = ["genera un mensaje", "crea el cuerpo", "con un mensaje creado por ti", "genera el mensaje"]
            generar_cuerpo = any(phrase in solicitud for phrase in generar_phrases)
            print(generar_cuerpo)
            # Generar cuerpo solo si se pide explícitamente
            if generar_cuerpo:
                tema = f"{asunto} {cuerpo or ''}".strip()
                cuerpo = generate_email_body(tema)
            # Si no hay cuerpo y no se pidió generar, usar un valor por defecto
            elif not cuerpo:
                cuerpo = "¡Qué tal! Te mando un mensaje rápido desde Shifu AI."
            # Si hay cuerpo y no se pidió generar, usarlo tal cual
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
            return {"solicitud": "POST", "result": {"message": f"📤 ¡Listo! Correo enviado a {destinatario} con asunto '{asunto}' 🚀"}}, 200
        # Crear borrador
        elif accion == "crear":
            match = re.search(r'(borrador|draft|correo)(?:\s*(?:para|a)\s*([\w\.-@,\s]+))?(?:\s*con\s*(?:el)?\s*asunto\s*:?\s*(.*?))?(?:\s*y\s*cuerpo\s*:?\s*(.*))?', solicitud, re.IGNORECASE)
            if match:
            # Buscar destinatario (opcional)
                destinatario_match = re.search(r'(?:para|a)\s*([\w\.-@,\s]+)', solicitud, re.IGNORECASE)
                destinatario = destinatario_match.group(1).strip() if destinatario_match else None
                if "@" not in destinatario:
                    destinatario =""

                # Buscar asunto (opcional)
                asunto_match = re.search(r'con\s*(?:el)?\s*asunto\s*:?\s*(.+?)(?:\s*y\s*cuerpo|$)', solicitud, re.IGNORECASE)
                asunto = asunto_match.group(1).strip() if asunto_match else "Borrador creado por Shifu"

                # Buscar cuerpo (opcional)
                cuerpo_match = re.search(r'y\s*cuerpo\s*:?\s*(.+)', solicitud, re.IGNORECASE)
                cuerpo = cuerpo_match.group(1).strip() if cuerpo_match else "Aquí va tu borrador, ¡tú dale el toque final! ✍️"

                print(destinatario)
                print(asunto)
                print(cuerpo)
                
                mensaje = MIMEText(cuerpo)
                if destinatario:
                    if "@" not in destinatario:
                        destinatario = f"{destinatario}@gmail.com"
                    elif not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', destinatario):
                        return {"solicitud": "POST", "result": {"error": "¡Ey! Ese correo no se ve bien, ¿me das uno válido?"}}, 400
                    mensaje["To"] = destinatario
                
                mensaje["Subject"] = asunto
                raw = base64.urlsafe_b64encode(mensaje.as_bytes()).decode()
                borrador = {"message": {"raw": raw}}
                url = "https://www.googleapis.com/gmail/v1/users/me/drafts"
                response = requests.post(url, json=borrador, headers=headers)
                response.raise_for_status()
                destinatario_msg = f" pa {destinatario}" if destinatario else ""
                return {"solicitud": "POST", "result": {"message": f"📩 ¡Borrador creado{destinatario_msg} con asunto '{asunto}' ya está en Gmail 🚀"}}, 200
            else:
                return {"solicitud": "POST", "result": {"error": "¡Ey! No sé qué crear, ¿un borrador? Dame más detalles, porfa."}}, 400
        # Eliminar correos
        elif accion == "eliminar":
            match = re.search(r'(correos|emails)\s*de\s*([\w\.-]+@[\w\.-]+|\w+)', solicitud, re.IGNORECASE)
            if match:
                sender = match.group(2).strip()
                if sender == "n/a":
                    return {"solicitud": "POST", "result": {"error": "¡Parece que olvidaste el remitente! 😊 ¿De quién quieres borrar los correos?"}}, 400
                list_url = "https://www.googleapis.com/gmail/v1/users/me/messages"
                params = {"q": f"from:{sender}", "maxResults": 5}
                list_response = requests.get(list_url, headers=headers, params=params)
                list_response.raise_for_status()
                messages = list_response.json().get("messages", [])
                if not messages:
                    return {"solicitud": "POST", "result": {"message": f"📭 No hay correos de '{sender}' pa’ borrar, ¡todo limpio por aquí!"}}, 200
                delete_results = []
                for msg in messages:
                    delete_url = f"{list_url}/{msg['id']}/trash"
                    response = requests.post(delete_url, headers=headers)
                    if response.status_code == 200:
                        delete_results.append(msg["id"])
                return {"solicitud": "POST", "result": {"message": f"🧹 ¡Listo! Moví {len(delete_results)} correos de '{sender}' a la papelera 🗑️"}}, 200
            else:
                return {"solicitud": "POST", "result": {"error": "¡Uy! Necesito saber qué correos borrar, ¿de quién son?"}}, 400

        # Mover a spam
        elif accion == "mover":
            match = re.search(r'de\s*([\w\.-]+@[\w\.-]+|\w+)', solicitud, re.IGNORECASE)
            if match:
                sender = match.group(1).strip()
                print(sender)
                if sender == "n/a":
                    return {"solicitud": "POST", "result": {"error": "¡Parece que olvidaste el remitente! 😊 ¿De quién quieres mover los correos a spam?"}}, 400
                list_url = "https://www.googleapis.com/gmail/v1/users/me/messages"
                params = {"q": f"from:{sender}", "maxResults": 5}
                list_response = requests.get(list_url, headers=headers, params=params)
                list_response.raise_for_status()
                messages = list_response.json().get("messages", [])
                if not messages:
                    return {"solicitud": "POST", "result": {"message": f"📭 No encontré correos de '{sender}' pa’ mover a spam."}}, 200
                spam_results = []
                for msg in messages:
                    modify_url = f"{list_url}/{msg['id']}/modify"
                    payload = {"addLabelIds": ["SPAM"]}
                    response = requests.post(modify_url, json=payload, headers=headers)
                    if response.status_code == 200:
                        spam_results.append(msg["id"])
                return {"solicitud": "POST", "result": {"message": f"🚫 ¡Hecho! {len(spam_results)} correos de '{sender}' ahora están en spam 😈"}}, 200
            else:
                return {"solicitud": "POST", "result": {"error": "¡Ey! No sé a dónde mover, ¿a spam? Dame más detalles."}}, 400

        # Agendar evento
        elif accion == "agendar":
            print("Entrando en agendar")
            # Verificar que sea una reunión o evento
            print("Paso 1: Reunión/evento encontrado")
            user_timezone = "America/Mexico_City"

            # Extraer parámetros con regex
            # Título (summary)
            summary_match = re.search(r'(?:con\s*(?:el)?\s*(título\s*de|asunto)|titulada)\s*["\']?([^"\']+?)["\']?(?=\s*(?:y\s*(el\s*)?correo|con|para|inicio|a\s*las|hasta|fin|$))', solicitud, re.IGNORECASE)
            summary = summary_match.group(2).strip() if summary_match else "Reunión por defecto"
            print(f"Título: {summary}")

            # Asistentes (attendees)
            attendees_match = re.search(r'(?:con|para)\s+.*?([\w\.-]+@[\w\.-]+)', solicitud, re.IGNORECASE)
            attendees_str = attendees_match.group(1).strip() if attendees_match else None
            print(f"Asistentes: {attendees_str}")

            # Fecha/hora de inicio (start)
            start_match = re.search(r'(mañana|hoy)?\s*(?:a\s*las)?\s*(\d{1,2}(?::\d{2})?\s*(am|pm)?)', solicitud, re.IGNORECASE)
            if start_match:
                day_part = start_match.group(1)  # "mañana" o "hoy" o None
                time_part = start_match.group(2)  # "11" o "11:00"
                am_pm = start_match.group(3)     # "am" o "pm" o None
                start_str = f"{day_part or 'hoy'} {time_part} {am_pm or ''}".strip()
                print(f"Start str: {start_str}")
            else:
                start_str = None
                print("No se encontró fecha/hora de inicio")

            # Fecha/hora de fin (end)
            end_match = re.search(r'(?:hasta|fin:)\s*(\d{1,2}(?::\d{2})?\s*(am|pm)?)', solicitud, re.IGNORECASE)
            end_str = end_match.group(1).strip() if end_match else None
            print(f"End str: {end_str}")

            # Función para normalizar la fecha/hora (basada en el código proporcionado)
            def parse_datetime(dt_str, base_date=None):
                dt_str = dt_str.replace("t", "T").strip()
                if not any(c in dt_str for c in ["+", "-", "Z"]):  # Si no tiene zona horaria
                    dt_str += f"-{user_timezone[-5:]}" if user_timezone[-5:].startswith("0") else f"+{user_timezone[-5:]}"
                try:
                    dt = datetime.fromisoformat(dt_str)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=ZoneInfo(user_timezone))
                    return dt
                except ValueError:
                    # Si es un formato incompleto (ej. "mañana 11 am"), construir manualmente
                    parts = dt_str.split()
                    day_part = parts[0].lower() if len(parts) > 1 else "hoy"
                    time_part = parts[1] if len(parts) > 1 else parts[0]
                    am_pm = parts[2].lower() if len(parts) > 2 else "am"

                    # Determinar la fecha base
                    now = datetime.now(tz=ZoneInfo(user_timezone))
                    if day_part == "mañana":
                        base_date = now + timedelta(days=1)
                    else:  # "hoy" o no especificado
                        base_date = now

                    # Parsear hora
                    if ":" in time_part:
                        hour, minute = map(int, time_part.split(":"))
                    else:
                        hour = int(time_part)
                        minute = 0

                    if am_pm == "pm" and hour != 12:
                        hour += 12
                    elif am_pm == "am" and hour == 12:
                        hour = 0

                    return base_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

            # Normalizar fechas
            if not start_str:
                start_dt = datetime.now(tz=ZoneInfo(user_timezone)) + timedelta(hours=1)
                print(f"Usando default start_dt: {start_dt}")
            else:
                try:
                    start_dt = parse_datetime(start_str)
                    print(f"Parsed start_dt: {start_dt}")
                except Exception as e:
                    print(f"Error parsing start_str '{start_str}': {str(e)}")
                    return {"solicitud": "POST", "result": {"error": "¡Uy! No entendí la fecha de inicio, ¿me la das bien?"}}, 400

            if not end_str:
                end_dt = start_dt + timedelta(hours=1)
                print(f"Default end_dt: {end_dt}")
            else:
                try:
                    end_dt = parse_datetime(end_str)
                    print(f"Parsed end_dt: {end_dt}")
                except Exception as e:
                    print(f"Error parsing end_str '{end_str}': {str(e)}")
                    return {"solicitud": "POST", "result": {"error": "¡Uy! No entendí la fecha de fin, ¿me la das bien?"}}, 400

            if end_dt <= start_dt:
                end_dt = start_dt + timedelta(hours=1)
                print(f"Adjusted end_dt: {end_dt}")

            # Construir el objeto del evento
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
                event["attendees"] = [{"email": email.strip()} for email in attendees_str.split(",")]

            # Enviar la solicitud a Google Calendar
            url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
            response = requests.post(url, json=event, headers=headers, params={"conferenceDataVersion": 1, "sendNotifications": True})
            response.raise_for_status()
            json_response = response.json()
            hangout_link = json_response.get("hangoutLink", "No se generó enlace de Meet")
            start_formatted = start_dt.strftime("%d/%m/%Y a las %H:%M")
            attendees_msg = f"\n👥 Asistentes: {attendees_str}" if attendees_str else ""
            return {"solicitud": "POST", "result": {"message": f"✅ ¡Listo! Agendé '{summary}' para el {start_formatted}\nEnlace de Meet: {hangout_link}{attendees_msg} 🎉"}}, 200

        # Marcar como leído/no leído
        elif accion == "marcar":
            match = re.search(r'como\s*(leído|no leído)\s*(correos|emails)\s*de\s*([\w\.-]+@[\w\.-]+|\w+)', solicitud, re.IGNORECASE)
            if match:
                estado = match.group(1).lower()
                sender = match.group(3).strip()
                list_url = "https://www.googleapis.com/gmail/v1/users/me/messages"
                params = {"q": f"from:{sender}", "maxResults": 5}
                list_response = requests.get(list_url, headers=headers, params=params)
                list_response.raise_for_status()
                messages = list_response.json().get("messages", [])
                if not messages:
                    return {"solicitud": "POST", "result": {"message": f"📭 No hay correos de '{sender}' pa’ marcar como {estado}."}}, 200
                marked_results = []
                label_action = {"removeLabelIds": ["UNREAD"]} if estado == "leído" else {"addLabelIds": ["UNREAD"]}
                for msg in messages:
                    modify_url = f"{list_url}/{msg['id']}/modify"
                    response = requests.post(modify_url, json=label_action, headers=headers)
                    if response.status_code == 200:
                        marked_results.append(msg["id"])
                estado_str = "leídos" if estado == "leído" else "no leídos"
                return {"solicitud": "POST", "result": {"message": f"📩 ¡Órale! Marqué {len(marked_results)} correos de '{sender}' como {estado_str} 👍"}}, 200
            else:
                return {"solicitud": "POST", "result": {"error": "¡Uy! Necesito saber qué marcar y cómo (leído/no leído), ¿me das más datos?"}}, 400

        # Archivar correos
        elif accion == "archivar":
            match = re.search(r'(correos|emails)\s*de\s*([\w\.-]+@[\w\.-]+|\w+)', solicitud, re.IGNORECASE)
            if match:
                sender = match.group(2).strip()
                list_url = "https://www.googleapis.com/gmail/v1/users/me/messages"
                params = {"q": f"from:{sender}", "maxResults": 5}
                list_response = requests.get(list_url, headers=headers, params=params)
                list_response.raise_for_status()
                messages = list_response.json().get("messages", [])
                if not messages:
                    return {"solicitud": "POST", "result": {"message": f"📭 No hay correos de '{sender}' pa’ archivar."}}, 200
                archived_results = []
                for msg in messages:
                    modify_url = f"{list_url}/{msg['id']}/modify"
                    payload = {"removeLabelIds": ["INBOX"]}
                    response = requests.post(modify_url, json=payload, headers=headers)
                    if response.status_code == 200:
                        archived_results.append(msg["id"])
                return {"solicitud": "POST", "result": {"message": f"📥 ¡Listo, compa! Archivé {len(archived_results)} correos de '{sender}' 🗂️"}}, 200
            else:
                return {"solicitud": "POST", "result": {"error": "¡Ey! Necesito saber qué archivar, ¿correos de quién?"}}, 400

        # Responder correo
        elif accion == "responder":
            match = re.search(r'(correo|email)\s*de\s*([\w\.-]+@[\w\.-]+|\w+)(?:\s*con\s*cuerpo:\s*(.*))?', solicitud, re.IGNORECASE)
            if match:
                sender = match.group(2).strip()
                cuerpo = match.group(3).strip() if match.group(3) else "¡Qué tal! Aquí va mi respuesta rapidita 😊"
                list_url = "https://www.googleapis.com/gmail/v1/users/me/messages"
                params = {"q": f"from:{sender}", "maxResults": 1}
                list_response = requests.get(list_url, headers=headers, params=params)
                list_response.raise_for_status()
                messages = list_response.json().get("messages", [])
                if not messages:
                    return {"solicitud": "POST", "result": {"error": f"📭 No encontré correos recientes de '{sender}' pa’ responder."}}, 400
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
                return {"solicitud": "POST", "result": {"message": f"📨 ¡Listo, papu! Respondí el correo de '{sender}' con asunto 'Re: {subject}' ✌️"}}, 200
            else:
                return {"solicitud": "POST", "result": {"error": "¡Ey! Necesito saber qué correo responder, ¿de quién es?"}}, 400

        else:
            return {"solicitud": "POST", "result": {"error": f"¡No entendí '{accion}'! Usa algo como 'enviar', 'crear', 'eliminar', ¿va?"}}, 400

    except requests.RequestException as e:
        return {"solicitud": "POST", "result": {"error": f"¡Ay, qué mala onda! Falló la conexión con Gmail: {str(e)}"}}, 500
    except Exception as e:
        return {"solicitud": "POST", "result": {"error": f"¡Uy, se puso feo! Error inesperado: {str(e)}"}}, 500

# Función auxiliar pa’ parsear fechas (sacada de post_to_gmail)
def parse_datetime(dt_str):
    dt_str = dt_str.replace("t", "T").strip()
    user_timezone = "America/Mexico_City"
    if not any(c in dt_str for c in ["+", "-", "Z"]):
        dt_str += f"-{user_timezone[-5:]}" if user_timezone[-5:].startswith("0") else f"+{user_timezone[-5:]}"
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo(user_timezone))
        return dt
    except ValueError:
        if "T" in dt_str:
            time_part = dt_str.split("T")[1]
            if len(time_part) == 2:
                dt_str += ":00:00"
            elif len(time_part) == 5:
                dt_str += ":00"
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo(user_timezone))
        return dt