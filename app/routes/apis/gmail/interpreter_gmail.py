from datetime import datetime, timedelta
from flask import request, jsonify
from config import Config
import json
import re
from zoneinfo import ZoneInfo
import openai
from email.mime.text import MIMEText
import base64
import requests
openai.api_key = Config.CHAT_API_KEY
from app.utils.utils import get_user_from_db
from flask_caching import Cache
from .getFunctionGmail import handle_get_request
from .postFunctionGmail import handle_post_request
from app.routes.core.context.ContextHandler import ContextHandler

def process_gmail_chat(email, user_query, mongo, cache, refresh_functions):
    """Core logic for processing Gmail chat requests."""
    hoy = datetime.today().strftime('%Y-%m-%d')

    gmail_system_info = f"""
    Eres un intérprete de intenciones avanzado para la API de Gmail y Google Calendar, pero también debes detectar acciones relacionadas con otras APIs cuando el usuario las mencione en solicitudes múltiples o automatizadas. Tu tarea es analizar el mensaje del usuario, clasificarlo en una categoría general y generar consultas generales. Para GET y POST simples, enfócate solo en Gmail/Google Calendar. Para solicitudes múltiples y automatizadas, incluye todas las intenciones detectadas (incluso de otras APIs) sin filtrarlas, dejando que un intérprete multitarea las procese. Si el mensaje es ambiguo o no se puede clasificar, solicita aclaración al usuario. Sigue estos pasos:

    1. **Clasificación del Tipo de Solicitud**:
    - **Saludo**: Si el mensaje es un saludo o una interacción social (ej. 'hola', '¿cómo estás?', 'buenos días', 'hey'), clasifica como: `"Es un saludo"`.
    - **Solicitud GET**: Si el usuario pide información con verbos como 'Mándame', 'Pásame', 'Envíame', 'Muéstrame', 'Busca', 'Dame', 'Dime', 'Quiero ver', 'Lista', 'Encuentra', '¿Qué hay?', '¿Cuáles son?' (ej. 'Dame los correos de Juan', 'Busca eventos de mañana'), clasifica como: `"Es una solicitud GET"`.
    - **Solicitud GET de Contexto (GET_CONTEXT)**: Si el usuario pide detalles sobre un correo o evento específico mencionado previamente (ej. 'De qué trata el correo de Vercel SHIP 2025?', 'Qué dice el correo de Juan?', 'Dame el contenido del último correo'), usando frases como 'de qué trata', 'qué dice', 'dame el contenido', 'qué contiene', 'detalle', 'muéstrame el contenido', clasifica como: `"Es una solicitud GET de contexto"`.
    - **Solicitud POST**: Si el usuario pide una acción con verbos como 'Crear', 'Enviar', 'Eliminar', 'Mover', 'Marcar', 'Archivar', 'Agendar', 'Escribe', 'Redacta', 'Responde' (ej. 'Enviar correo a Juan', 'Agendar una reunión para mañana'), clasifica como: `"Es una solicitud POST"`.
    - **Solicitud Automatizada**: Si el usuario pide algo repetitivo o condicional con frases como 'Cada vez que', 'Siempre que', 'Automáticamente', 'Si pasa X haz Y', 'Cuando ocurra X' (ej. 'Si recibo un correo de Juan, envía un mensaje a Slack'), clasifica como: `"Es una solicitud automatizada"`.
    - **Solicitud Múltiple**: Si el mensaje combina varias acciones con conjunciones como 'y', 'luego', 'después', o verbos consecutivos (ej. 'Busca correos de Ana y sube un archivo a Drive', 'Redacta un correo y agendar una reunión'), clasifica como: `"Es una solicitud múltiple"`.
    - **No Clasificable**: Si el mensaje es demasiado vago, incompleto o no encaja en las categorías anteriores (ej. 'Haz algo', 'Juan', 'Correo'), clasifica como: `"No puedo clasificar la solicitud, por favor aclara qué quieres hacer"`.

    2. **Reglas Críticas para Clasificación**:
    - **GET**: Solicitudes de lectura solo para Gmail/Google Calendar (obtener correos o eventos). Ejemplo: 'Dame los correos de Juan' → GET.
    - **GET_CONTEXT**: Solicitudes que buscan detalles de un correo o evento específico mencionado antes, generalmente usando el historial del chat. Ejemplo: 'De qué trata el correo de Vercel?' → GET_CONTEXT.
    - **POST**: Acciones de escritura solo para Gmail/Google Calendar (enviar correos, crear eventos, etc.). Ejemplo: 'Enviar un correo a Juan' → POST.
    - **Automatizadas**: Acciones con condiciones, detectando intenciones para Gmail y otras APIs mencionadas. Ejemplo: 'Si recibo un correo de Juan, envía un mensaje a Slack' → Automatizada.
    - **Múltiple**: Detecta conjunciones ('y', 'luego'), verbos consecutivos, o intenciones separadas, incluyendo acciones de cualquier API. Ejemplo: 'Busca correos de Ana y envía un mensaje a Slack' → Múltiple.
    - **Ambigüedad**: Si un verbo puede ser GET o POST (ej. 'Manda'), analiza el contexto:
        - Si pide información (ej. 'Manda los correos de Juan'), es GET.
        - Si pide una acción (ej. 'Manda un correo a Juan'), es POST.
        - Si no hay suficiente contexto, clasifica como "No Clasificable".
    - **Errores del Usuario**: Si falta información clave (ej. 'Busca el correo' sin especificar de quién), clasifica como "No Clasificable".

    3. **Detección y Generación de Consultas**:
    - Para **GET y POST simples**, genera intenciones solo para Gmail/Google Calendar:
        - **Gmail**: Buscar correos, enviar correos, eliminar correos, mover a spam/papelera, crear borradores, marcar como leído/no leído, archivar correos, responder correos.
        - **Google Calendar**: Agendar reuniones, buscar eventos, eliminar eventos, modificar eventos.
    - Para **GET_CONTEXT**, genera una intención que describa qué detalle se pide del correo o evento (ej. "detalle del correo de Vercel SHIP 2025").
    - Para **Automatizadas y Múltiples**, incluye todas las intenciones detectadas, incluso si involucran otras APIs (ej. Slack, Drive, ClickUp), sin filtrarlas.
    - Si una acción no encaja con Gmail/Google Calendar en GET o POST simples, usa 'N/A'.

    4. **Formato de Salida**:
    - Devuelve un string con el tipo de solicitud seguido de un JSON con consultas generales bajo la clave "gmail".
    - **GET**: `{{"gmail": "<intención>"}}`
    - **GET_CONTEXT**: `{{"gmail": "<intención>"}}`
    - **POST**: `{{"gmail": "<intención>"}}`
    - **Automatizada**: `{{"gmail": [{{"condition": "<condición>", "action": "<acción>"}}, ...]}}`
    - **Múltiple**: `{{"gmail": ["<intención 1>", "<intención 2>", ...]}}`
    - **No Clasificable**: `{{"message": "Por favor, aclara qué quieres hacer"}}`
    - **Saludo**: `{{"gmail": "N/A"}}`

    5. **Reglas para Consultas Generales**:
    - **GET**: Describe qué obtener en Gmail/Google Calendar (ej. "obtener correos de Juan", "buscar eventos de mañana"). Si no aplica, clasifica como "No Clasificable".
    - **GET_CONTEXT**: Describe qué detalle se pide (ej. "detalle del correo de Vercel SHIP 2025", "contenido del correo de Juan"). Si no se especifica un correo, usa "detalle del último correo mencionado".
    - **POST**: Describe la acción en Gmail/Google Calendar (ej. "enviar un correo a Juan", "agendar una reunión para mañana"). Si no aplica, clasifica como "No Clasificable".
    - **Automatizada**: Divide en condición y acción, incluyendo otras APIs (ej. "condición: recibir un correo de Juan", "acción: enviar un mensaje a Slack").
    - **Múltiple**: Separa cada intención en una frase clara, incluyendo acciones de otras APIs (ej. "obtener correos de Ana", "subir un archivo a Drive").
    - Incluye nombres, fechas o datos clave del usuario (ej. "Juan", "mañana") si se mencionan.

    6. **Manejo de Casos Especiales**:
    - **Términos Temporales**: Si se mencionan términos como 'hoy', 'mañana', 'ayer', inclúyelos en la intención (ej. 'buscar eventos de mañana').
    - **Correos o Eventos Específicos**: Si se pide un correo o evento específico (ej. 'el último correo de Juan', 'la reunión de mañana con Ana'), inclúyelo en la intención (ej. "obtener el último correo de Juan").
    - **Contexto Implícito**: Si el usuario no especifica un correo o evento en una solicitud GET_CONTEXT, asume que se refiere al último correo o evento mencionado en el historial (ej. 'De qué trata el correo?' → "detalle del último correo mencionado").

    Ejemplos:
    - "Mandame el correo de Hyper" → "Es una solicitud GET" {{"gmail": "obtener correos de Hyper"}}
    - "Dame los correos de Juan" → "Es una solicitud GET" {{"gmail": "obtener correos de Juan"}}
    - "Busca el último correo de Vercel" → "Es una solicitud GET" {{"gmail": "obtener el último correo de Vercel"}}
    - "De qué trata el correo de Vercel SHIP 2025?" → "Es una solicitud GET de contexto" {{"gmail": "detalle del correo de Vercel SHIP 2025"}}
    - "Qué dice el correo de Juan?" → "Es una solicitud GET de contexto" {{"gmail": "contenido del correo de Juan"}}
    - "De qué trata el correo?" → "Es una solicitud GET de contexto" {{"gmail": "detalle del último correo mencionado"}}
    - "Enviar correo a Juan" → "Es una solicitud POST" {{"gmail": "enviar un correo a Juan"}}
    - "Agendar una reunión para mañana con Ana" → "Es una solicitud POST" {{"gmail": "agendar una reunión para mañana con Ana"}}
    - "Si recibo un correo de Juan, envía un mensaje a Slack" → "Es una solicitud automatizada" {{"gmail": [{{"condition": "recibir un correo de Juan", "action": "enviar un mensaje a Slack"}}]}}
    - "Busca correos de Ana y sube un archivo a Drive" → "Es una solicitud múltiple" {{"gmail": ["obtener correos de Ana", "subir un archivo a Drive"]}}
    - "Busca correos de Juan y envía un correo a María" → "Es una solicitud múltiple" {{"gmail": ["obtener correos de Juan", "enviar un correo a María"]}}
    - "Hola" → "Es un saludo" {{"gmail": "N/A"}}
    - "Sube un archivo a Drive" → "No puedo clasificar la solicitud, por favor aclara qué quieres hacer" {{"message": "Esto no es una acción para Gmail, ¿qué quieres hacer con Gmail?"}}
    - "Busca el correo" → "No puedo clasificar la solicitud, por favor aclara qué quieres hacer" {{"message": "Por favor, aclara qué correo quieres buscar y de quién"}}
    - "Dame algo" → "No puedo clasificar la solicitud, por favor aclara qué quieres hacer" {{"message": "Por favor, aclara qué quieres que busque o haga"}}
    """

    def should_refresh_tokens(email):
        last_refresh_key = f"last_refresh_{email}"
        last_refresh = cache.get(last_refresh_key)
        current_time = datetime.utcnow()
        if last_refresh is None:
            return True
        last_refresh_time = datetime.fromtimestamp(last_refresh)
        refresh_interval = timedelta(minutes=30)
        return (current_time - last_refresh_time) >= refresh_interval

    def get_user_with_refreshed_tokens(email):
        try:
            user = cache.get(email)
            if not user:
                user = get_user_from_db(email, cache, mongo)
                if not user:
                    return None
                cache.set(email, user, timeout=1800)

            if not should_refresh_tokens(email):
                return user

            refresh_tokens_dict = refresh_functions["get_refresh_tokens_from_db"](email)
            if not refresh_tokens_dict or "gmail" not in refresh_tokens_dict:
                cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
                return user

            integrations = user.get("integrations", {})
            tokens_to_refresh = {
                "gmail": refresh_tokens_dict["gmail"]
            } if "gmail" in integrations and integrations["gmail"].get("refresh_token") not in (None, "n/a") else {}

            if not tokens_to_refresh:
                cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
                return user

            refreshed_tokens, errors = refresh_functions["refresh_tokens"](tokens_to_refresh, email)
            if refreshed_tokens or errors:
                user = get_user_from_db(email, cache, mongo)
                cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
            return user
        except Exception as e:
            print(f"[ERROR] Error en get_user_with_refreshed_tokens para {email}: {e}")
            return None

    def generate_prompt(get_result):
        result = get_result.get("result", {})
        message = result.get("message", "No se pudo procesar la solicitud, algo salió mal.")
        data = result.get("data", None)

        if data and "correos" in message.lower():
            correo_info = "\n".join(
                f"De: {item['from']} | Asunto: {item['subject']} | Fecha: {item['date']} | Cuerpo: {item['body']}"
                for item in data
            )
            base_text = f"El usuario pidió correos y esto encontré:\n{message}\nDetalles:\n{correo_info}"
        elif data and "eventos" in message.lower():
            evento_info = "\n".join(
                f"Evento: {item['summary']} | Inicio: {item['start']}"
                for item in data
            )
            base_text = f"El usuario pidió eventos y esto encontré:\n{message}\nDetalles:\n{evento_info}"
        else:
            base_text = f"El usuario pidió algo y esto obtuve:\n{message}" + (f"\nDetalles: {str(data)}" if data else "")

        prompt = f"""
        Debes responder la petición del usuario: {user_query}
        Eres un asistente de Gmail súper amigable y útil, con un tono relajado y natural, como si charlaras con un amigo. Usa emojis sutiles para darle onda, pero sin exagerar. Basándote en esta info, arma una respuesta concisa y en párrafo que resuma los resultados de forma práctica y clara:

        {base_text}

        - Si hay resultados de correos, haz un resumen breve y útil, mencionando cuántos correos encontré y algo relevante (como quién los mandó, el asunto o un detalle interesante del cuerpo del correo). No listes todo como tabla, solo destaca lo más importante.
        - Si hay resultados de eventos, menciona cuántos eventos encontré y algo relevante (como el nombre del evento o la hora).
        - Si no hay resultados, di algo amable y sugiere ajustar la búsqueda si hace falta.
        - Habla en primera persona y evita sonar robótico o repetir los datos crudos tal cual. Y pon emojis.
        NO INCLUYAS LINKS y responde amigable pero FORMALMENTE
        """

        try:
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Eres un asistente de Gmail amigable."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=400
            )
            ia_response = response.choices[0].message.content.strip()
            return ia_response, prompt
        except Exception as e:
            return f"¡Ups! Algo salió mal al armar la respuesta: {str(e)}", None

    if not email:
        return {"error": "¡Órale! Necesito el email del usuario pa’ trabajar, ¿me lo pasas?"}, 400
    if not user_query:
        return {"error": "¡Ey! No me diste ninguna query, ¿qué quieres que haga?"}, 400

    user = get_user_with_refreshed_tokens(email)
    if not user:
        return {"error": "No encontré a este usuario, ¿seguro que está registrado?"}, 404

    if "chats" not in user or not any(chat.get("name") == "GmailChat" for chat in user.get("chats", [])):
        mongo.database.usuarios.update_one(
            {"correo": email},
            {"$set": {"chats": [{"name": "GmailChat", "messages": []}]}} if "chats" not in user else {"$push": {"chats": {"name": "GmailChat", "messages": []}}},
            upsert=True
        )
        user = get_user_with_refreshed_tokens(email)
    usuario = mongo.database.usuarios.find_one({"correo": email})
    gmail_chat = next(
        (chat for chat in usuario.get("chats", []) if isinstance(chat, dict) and chat.get("name") == "GmailChat"),
        None
    )

    if not gmail_chat:
        return {"error": "¡Uy! Algo salió mal al preparar el chat, ¿intentamos otra vez?"}, 500

    timestamp = datetime.utcnow().isoformat()
    user_message = {"role": "user", "content": user_query, "timestamp": timestamp}

    try:
        prompt = f"""
            Interpreta esta query para Gmail: "{user_query}"
            Devuelve un JSON con esta estructura:
            {{
            "peticion": "GET" | "POST" | "SALUDO" | "AUTOMATIZADA" | "MULTIPLE" | "NO_CLASIFICABLE" | "GET_CONTEXT",
            "accion": "buscar" | "enviar" | "crear" | "eliminar" | "mover" | "agendar" | "marcar" | "archivar" | "responder" | "detalle_correo" | null (si es saludo o no clasificable),
            "solicitud": "<detalles específicos>" | null (si no aplica) | [array de acciones para MULTIPLE] | [{{"condition": "...", "action": "..."}} para AUTOMATIZADA]
            }}

            Reglas:
            1. Si es un saludo (ej. "hola"), responde un string como "SALUDO".
            2. Para GET, agrupa verbos de lectura como "dame", "mándame", "buscar", "muéstrame", "lista", "encuentra" en "accion": "buscar".
            - Si la query menciona "correo", "correos", "email", "emails", "mensajes" o "mails" seguido de un término (ej. "Vercel", "Juan"), asume que es un remitente y usa "solicitud": "correos de <término>".
            - Si incluye "relacionado con" o "sobre", extrae el término después como tema (ej. "correo relacionado con Vercel" → "solicitud": "correos de Vercel"), priorizando remitente sobre tema si hay ambigüedad.
            3. Para GET de contexto (GET_CONTEXT), detecta si el usuario pide detalles sobre un correo específico mencionado antes (ej. "De qué trata el correo de Vercel SHIP 2025?", "Qué dice el correo de Juan", "Dame el contenido del correo de Vercel") usando verbos o frases como "de qué trata", "qué dice", "detalle", "muéstrame el contenido", "qué contiene", "dame el contenido". Usa "peticion": "GET_CONTEXT", "accion": "detalle_correo", "solicitud": "<término específico del correo>", donde el término es el asunto o parte del asunto mencionado (ej. "Vercel SHIP 2025", "Juan"). Si no se menciona un término claro, usa el último correo mencionado en el historial.
            4. Para POST, agrupa verbos en estas categorías:
            - "enviar": "enviar", "manda", "envía", "enviale"
            - "crear": "crear", "hacer", "redactar", "redacta"
            - "eliminar": "eliminar", "borrar", "quitar"
            - "mover": "mover", "trasladar"
            - "agendar": "agendar", "programar", "agendame"
            - "marcar": "marcar", "señalar"
            - "archivar": "archivar", "guardar"
            - "responder": "responder", "contestar", "responde"
            5. Si es AUTOMATIZADA o MULTIPLE, usa arrays según el system prompt.
            6. Si no se entiende, usa "peticion": "NO_CLASIFICABLE", "accion": null, "solicitud": "Por favor, aclara qué quieres hacer".

            Ejemplos:
            - "Holaaaa" → {{"peticion": "SALUDO", "accion": null, "solicitud": null}}
            - "Mándame los correos de Juan" → {{"peticion": "GET", "accion": "buscar", "solicitud": "correos de Juan"}}
            - "Correo relacionado con Vercel" → {{"peticion": "GET", "accion": "buscar", "solicitud": "correos de Vercel"}}
            - "De qué trata el correo de Vercel SHIP 2025?" → {{"peticion": "GET_CONTEXT", "accion": "detalle_correo", "solicitud": "Vercel SHIP 2025"}}
            - "Qué dice el correo de Juan?" → {{"peticion": "GET_CONTEXT", "accion": "detalle_correo", "solicitud": "Juan"}}
            - "Dame el contenido del correo de Vercel" → {{"peticion": "GET_CONTEXT", "accion": "detalle_correo", "solicitud": "Vercel"}}
            - "Redacta un correo para Juan con asunto: Hola" → {{"peticion": "POST", "accion": "crear", "solicitud": "correo para Juan con asunto: Hola"}}
            - "Si recibo correo de Juan, envía mensaje" → {{"peticion": "AUTOMATIZADA", "accion": null, "solicitud": [{{"condition": "recibo correo de Juan", "action": "envía mensaje"}}]}}
            """
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": gmail_system_info},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500
        )
        ia_response = response.choices[0].message.content.strip()

        try:
            json_pattern = r'\{(?:[^{}]|\{[^{}]*\})*\}'
            match = re.search(json_pattern, ia_response, re.DOTALL | re.MULTILINE)
            if match:
                json_str = match.group(0)
                parsed_response = json.loads(json_str)
                peticion = parsed_response.get("peticion")
                accion = parsed_response.get("accion")
                solicitud = parsed_response.get("solicitud")
            else:
                raise json.JSONDecodeError("No JSON found", ia_response, 0)
        except json.JSONDecodeError:
            parsed_response = {"peticion": "NO_CLASIFICABLE", "accion": None, "solicitud": "¡Ups! Algo salió mal con la respuesta, ¿me lo repites?"}
            peticion = parsed_response["peticion"]
            accion = parsed_response["accion"]
            solicitud = parsed_response["solicitud"]

        if "saludo" in peticion.lower():
            greeting_prompt = f"El usuario dijo '{user_query}', responde de manera cálida y amigable con emojis. Menciona que eres su asistente personalizado de Gmail."
            greeting_response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": "Eres su asistente personal de Gmail muy amigable."}, {"role": "user", "content": greeting_prompt}],
                max_tokens=200
            )
            result = greeting_response.choices[0].message.content.strip()
            status = 200
        elif "get_context" in peticion.lower():
            context_handler = ContextHandler(mongo.database)
            result, status = context_handler.get_chat_context(
                email=email,
                chat_name="GmailChat",
                query=user_query,
                solicitud=solicitud
            )
        elif "get" in peticion.lower():
            result, status = handle_get_request(accion, solicitud, email, user)
            result, prompt = generate_prompt(result)
        elif "post" in peticion.lower():
            result, status = handle_post_request(accion, solicitud, email, user)
            result = result.get("result", {}).get("message", "No se encontró mensaje")
        else:
            result = {"solicitud": "ERROR", "result": {"error": solicitud}}
            status = 400

        assistant_message = {"role": "assistant", "content": result if isinstance(result, str) else json.dumps(result), "timestamp": datetime.utcnow().isoformat()}
        mongo.database.usuarios.update_one(
            {"correo": email, "chats.name": "GmailChat"},
            {"$push": {"chats.$.messages": {"$each": [user_message, assistant_message]}}}
        )

        return {"message": result}, status

    except Exception as e:
        return {"message": {"solicitud": "ERROR", "result": {"error": f"¡Ay, caray! Algo se rompió: {str(e)}"}}}, 500

def setup_gmail_chat(app, mongo, cache, refresh_functions):
    """Register Gmail chat route."""
    @app.route("/api/chat/gmail", methods=["POST"])
    def chatGmail():
        email = request.args.get("email")
        data = request.get_json()
        user_query = data.get("messages", [{}])[-1].get("content") if data.get("messages") else None
        result, status = process_gmail_chat(email, user_query, mongo, cache, refresh_functions)
        print(result)
        return jsonify(result), status

    return chatGmail