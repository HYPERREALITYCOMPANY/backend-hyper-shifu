from datetime import datetime, timedelta
from flask import request, jsonify
from config import Config
import json
import re
from zoneinfo import ZoneInfo
import openai
openai.api_key = Config.CHAT_API_KEY
from app.utils.utils import get_user_from_db
from flask_caching import Cache
from .getFunctionOutlook import handle_get_request
from .postFunctionOutlook import handle_post_request
from app.routes.core.context.ContextHandler import ContextHandler

def process_outlook_chat(email, user_query=None, mongo=None, cache=None, refresh_functions=None):
    """Core logic for processing Outlook chat requests."""
    hoy = datetime.today().strftime('%Y-%m-%d')

    outlook_system_info = f"""
    Eres un intérprete de intenciones avanzado para la API de Outlook (Microsoft Graph). Tu tarea es analizar el mensaje del usuario, clasificarlo en una categoría general y generar consultas generales. Para GET y POST simples, enfócate solo en Outlook Mail/Calendar. Para solicitudes múltiples o automatizadas, incluye todas las intenciones detectadas (incluso de otras APIs) sin filtrarlas. Si el mensaje es ambiguo, solicita aclaración. Sigue estos pasos:

    1. **Clasificación del Tipo de Solicitud**:
       - **Saludo**: Si es un saludo (ej. 'hola', '¿qué tal?', 'buenos días'), responde: `"Es un saludo"`.
       - **Solicitud GET**: Si pide información con verbos como 'Mándame', 'Pásame', 'Muéstrame', 'Busca', 'Dame', 'Dime', 'Lista' (ej. 'Dame los correos de Juan', 'Busca eventos de mañana'), responde: `"Es una solicitud GET"`.
       - **Solicitud GET de Contexto (GET_CONTEXT)**: Si pide detalles sobre un correo o evento específico mencionado previamente (ej. 'De qué trata el correo de Juan?', 'Qué dice el correo de Outlook Fest?', 'Dame el contenido del último correo'), usando frases como 'de qué trata', 'qué dice', 'dame el contenido', 'qué contiene', 'detalle', 'muéstrame el contenido', responde: `"Es una solicitud GET de contexto"`.
       - **Solicitud POST**: Si pide una acción con verbos como 'Enviar', 'Crear', 'Eliminar', 'Mover', 'Marcar', 'Agendar' (ej. 'Enviar correo a Juan', 'Agendar una reunión'), responde: `"Es una solicitud POST"`.
       - **Solicitud Automatizada**: Si es repetitivo o condicional con 'Cada vez que', 'Siempre que', 'Si pasa X haz Y' (ej. 'Si recibo un correo de Juan, muévelo a spam'), responde: `"Es una solicitud automatizada"`.
       - **Solicitud Múltiple**: Si combina acciones con 'y', 'luego', o verbos consecutivos (ej. 'Busca correos de Ana y agendar una reunión'), responde: `"Es una solicitud múltiple"`.
       - **No Clasificable**: Si es vago (ej. 'Haz algo', 'Juan'), responde: `"No puedo clasificar la solicitud, por favor aclara qué quieres hacer"`.

    2. **Reglas Críticas para Clasificación**:
       - **GET**: Solo lectura para Outlook (obtener correos o eventos).
       - **GET_CONTEXT**: Detalles de un correo o evento específico, usando historial si no se especifica.
       - **POST**: Acciones de escritura para Outlook (enviar correos, crear eventos, etc.).
       - **Automatizadas**: Acciones con condiciones, detectando intenciones para Outlook y otras APIs.
       - **Múltiple**: Detecta conjunciones ('y', 'luego') o intenciones separadas, incluyendo otras APIs.
       - **Ambigüedad**: Si un verbo es ambiguo (ej. 'Manda'), usa el contexto; si no hay suficiente, clasifica como "No Clasificable".

    3. **Detección y Generación de Consultas**:
       - Para **GET y POST simples**, genera intenciones solo para Outlook:
         - **Outlook Mail**: Buscar correos, enviar correos, eliminar correos, mover a spam/papelera, crear borradores, marcar como leído/no leído.
         - **Outlook Calendar**: Agendar reuniones, buscar eventos, eliminar eventos, modificar eventos.
       - Para **GET_CONTEXT**, genera una intención que describa qué detalle se pide (ej. "detalle del correo de Juan").
       - Para **Automatizadas y Múltiples**, incluye todas las intenciones detectadas, incluso de otras APIs (ej. Teams, OneDrive).
       - Si una acción no encaja con Outlook en GET o POST simples, usa 'N/A'.

    4. **Formato de Salida**:
       - Devuelve un string con el tipo de solicitud seguido de un JSON con consultas bajo la clave "outlook".
       - **GET**: `{{"outlook": "<intención>"}}`
       - **GET_CONTEXT**: `{{"outlook": "<intención>"}}`
       - **POST**: `{{"outlook": "<intención>"}}`
       - **Automatizada**: `{{"outlook": [{{"condition": "<condición>", "action": "<acción>"}}, ...]}}`
       - **Múltiple**: `{{"outlook": ["<intención 1>", "<intención 2>", ...]}}`
       - **No Clasificable**: `{{"message": "Por favor, aclara qué quieres hacer"}}`
       - **Saludo**: `{{"outlook": "N/A"}}`

    5. **Reglas para Consultas Generales**:
       - **GET**: Describe qué obtener (ej. "obtener correos de Juan").
       - **GET_CONTEXT**: Describe qué detalle se pide (ej. "contenido del correo de Juan"). Si no se especifica, usa "detalle del último correo mencionado".
       - **POST**: Describe la acción (ej. "enviar un correo a Juan").
       - **Automatizada**: Divide en condición y acción (ej. "condición: recibir un correo de Juan", "acción: mover a spam").
       - **Múltiple**: Separa cada intención (ej. "obtener correos de Ana", "agendar una reunión").
       - Incluye nombres o datos clave (ej. "Juan", "mañana") si se mencionan.

    Ejemplos:
    - "Hola" → "Es un saludo" {{"outlook": "N/A"}}
    - "Dame los correos de Juan" → "Es una solicitud GET" {{"outlook": "obtener correos de Juan"}}
    - "De qué trata el correo de Outlook Fest?" → "Es una solicitud GET de contexto" {{"outlook": "detalle del correo de Outlook Fest"}}
    - "Enviar correo a Juan" → "Es una solicitud POST" {{"outlook": "enviar un correo a Juan"}}
    - "Si recibo un correo de Juan, muévelo a spam" → "Es una solicitud automatizada" {{"outlook": [{{"condition": "recibir un correo de Juan", "action": "mover a spam"}}]}}
    - "Busca correos de Ana y agendar una reunión" → "Es una solicitud múltiple" {{"outlook": ["obtener correos de Ana", "agendar una reunión"]}}
    - "Haz algo" → "No puedo clasificar la solicitud, por favor aclara qué quieres hacer" {{"message": "Por favor, aclara qué quieres hacer"}}
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
            if not refresh_tokens_dict or "outlook" not in refresh_tokens_dict:
                cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
                return user

            integrations = user.get("integrations", {})
            tokens_to_refresh = {
                "outlook": refresh_tokens_dict["outlook"]
            } if "outlook" in integrations and integrations["outlook"].get("refresh_token") not in (None, "n/a") else {}

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
                f"De: {item['from']} | Asunto: {item['subject']} | Fecha: {item['date']}"
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
        Eres un asistente de Outlook súper amigable y útil, con un tono relajado y natural, como si charlaras con un amigo. Usa emojis sutiles para darle onda, pero sin exagerar. Basándote en esta info, arma una respuesta concisa y en párrafo que resuma los resultados de forma práctica y clara:

        {base_text}

        - Si hay resultados de correos, haz un resumen breve y útil, mencionando cuántos correos encontré y algo relevante (como quién los mandó, el asunto o un detalle interesante). No listes todo como tabla, solo destaca lo más importante.
        - Si hay resultados de eventos, menciona cuántos eventos encontré y algo relevante (como el nombre del evento o la hora).
        - Si no hay resultados, di algo amable y sugiere ajustar la búsqueda si hace falta.
        - Habla en primera persona y evita sonar robótico o repetir los datos crudos tal cual.
        NO INCLUYAS LINKS y responde amigable pero FORMALMENTE
        """

        try:
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Eres un asistente de Outlook amigable."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=400
            )
            ia_response = response.choices[0].message.content.strip()
            return ia_response, prompt
        except Exception as e:
            return f"¡Ups! Algo salió mal al armar la respuesta: {str(e)}", prompt

    # Extract query if not provided
    if not user_query:
        try:
            data = request.get_json() or {}
            user_query = (
                data.get("messages", [{}])[-1].get("content")
                if data.get("messages")
                else request.args.get("query")
            )
        except Exception:
            return {"message": "¡Ey! No me diste ninguna query, ¿qué quieres que haga con Outlook? 📧"}, 400

    if not email:
        return {"message": "¡Órale! Necesito tu email pa’ trabajar, ¿me lo pasas? 😅"}, 400
    if not user_query:
        return {"message": "¡Ey! No me diste ninguna query, ¿qué quieres que haga con Outlook? 📧"}, 400

    user = get_user_with_refreshed_tokens(email)
    if not user:
        return {"message": "No encontré a este usuario, ¿seguro que está registrado? 😕"}, 404

    if "chats" not in user or not any(chat.get("name") == "OutlookChat" for chat in user.get("chats", [])):
        mongo.database.usuarios.update_one(
            {"correo": email},
            {"$set": {"chats": [{"name": "OutlookChat", "messages": []}]}} if "chats" not in user else {"$push": {"chats": {"name": "OutlookChat", "messages": []}}},
            upsert=True
        )
        user = get_user_with_refreshed_tokens(email)
    
    usuario = mongo.database.usuarios.find_one({"correo": email})
    outlook_chat = next(
        (chat for chat in usuario.get("chats", []) if isinstance(chat, dict) and chat.get("name") == "OutlookChat"),
        None
    )

    if not outlook_chat:
        return {"message": "¡Uy! Algo salió mal al preparar el chat, ¿intentamos otra vez? 😓"}, 500

    timestamp = datetime.utcnow().isoformat()
    user_message = {"role": "user", "content": user_query, "timestamp": timestamp}

    try:
        prompt = f"""
            Interpreta esta query para Outlook: "{user_query}"
            Devuelve un JSON con esta estructura:
            {{
            "peticion": "GET" | "POST" | "SALUDO" | "AUTOMATIZADA" | "MULTIPLE" | "NO_CLASIFICABLE" | "GET_CONTEXT",
            "accion": "buscar" | "enviar" | "crear" | "eliminar" | "mover" | "agendar" | "marcar" | "detalle_correo" | null (si es saludo o no clasificable),
            "solicitud": "<detalles específicos>" | null (si no aplica) | [array de acciones para MULTIPLE] | [{{"condition": "...", "action": "..."}} para AUTOMATIZADA]
            }}

            Reglas:
            1. Si es un saludo (ej. "hola"), responde "SALUDO".
            2. Para GET, agrupa verbos de lectura como "dame", "mándame", "buscar", "muéstrame", "lista" en "accion": "buscar".
               - Si menciona "correo", "correos", "email", "emails" seguido de un término (ej. "Juan"), usa "solicitud": "correos de <término>".
            3. Para GET_CONTEXT, detecta si pide detalles de un correo o evento con frases como "de qué trata", "qué dice", "dame el contenido", "qué contiene", "detalle".
               - Usa "peticion": "GET_CONTEXT", "accion": "detalle_correo", "solicitud": "<término específico del correo o evento>".
               - Si no se especifica, usa "detalle del último correo mencionado".
            4. Para POST, agrupa verbos en estas categorías:
               - "enviar": "enviar", "manda", "envía"
               - "crear": "crear", "hacer", "redactar"
               - "eliminar": "eliminar", "borrar"
               - "mover": "mover", "trasladar"
               - "agendar": "agendar", "programar"
               - "marcar": "marcar", "señalar"
            5. Si es AUTOMATIZADA o MULTIPLE, usa arrays según el system prompt.
            6. Si no se entiende, usa "NO_CLASIFICABLE" con "solicitud": "Por favor, aclara qué quieres hacer".

            Ejemplos:
            - "Dame los correos de Juan" → {{"peticion": "GET", "accion": "buscar", "solicitud": "correos de Juan"}}
            - "De qué trata el correo de Outlook Fest?" → {{"peticion": "GET_CONTEXT", "accion": "detalle_correo", "solicitud": "Outlook Fest"}}
            - "Enviar correo a Juan" → {{"peticion": "POST", "accion": "enviar", "solicitud": "correo a Juan"}}
            """
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": outlook_system_info},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500
        )
        ia_response = response.choices[0].message.content.strip()

        json_pattern = r'\{(?:[^{}]|\{[^{}]*\})*\}'
        match = re.search(json_pattern, ia_response, re.DOTALL | re.MULTILINE)
        if match:
            parsed_response = json.loads(match.group(0))
            peticion = parsed_response.get("peticion")
            accion = parsed_response.get("accion")
            solicitud = parsed_response.get("solicitud")
        else:
            parsed_response = {"peticion": "NO_CLASIFICABLE", "accion": None, "solicitud": "¡Ups! Algo salió mal con la respuesta, ¿me lo repites?"}
            peticion = parsed_response["peticion"]
            accion = parsed_response["accion"]
            solicitud = parsed_response["solicitud"]

        if "saludo" in peticion.lower():
            greeting_prompt = f"El usuario dijo '{user_query}', responde de manera cálida y amigable con emojis. Menciona que eres su asistente personalizado de Outlook."
            greeting_response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": "Eres su asistente personal de Outlook muy amigable."}, {"role": "user", "content": greeting_prompt}],
                max_tokens=200
            )
            result = greeting_response.choices[0].message.content.strip()
            status = 200
        elif "get_context" in peticion.lower():
            context_handler = ContextHandler(mongo.database)
            result, status = context_handler.get_chat_context(
                email=email,
                chat_name="OutlookChat",
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
            result = solicitud
            status = 400

        assistant_message = {"role": "assistant", "content": result if isinstance(result, str) else json.dumps(result), "timestamp": datetime.utcnow().isoformat()}
        mongo.database.usuarios.update_one(
            {"correo": email, "chats.name": "OutlookChat"},
            {"$push": {"chats.$.messages": {"$each": [user_message, assistant_message]}}}
        )

        return {"message": result}, status

    except Exception as e:
        return {"message": f"¡Ay, caray! Algo se rompió: {str(e)} 😓"}, 500

def setup_outlook_chat(app, mongo, cache, refresh_functions):
    """Register Outlook chat route."""
    @app.route("/api/chat/outlook", methods=["POST"])
    def chatOutlook():
        email = request.args.get("email")
        data = request.get_json() or {}
        user_query = (
            data.get("messages", [{}])[-1].get("content")
            if data.get("messages")
            else request.args.get("query")
        )
        result, status = process_outlook_chat(email, user_query, mongo, cache, refresh_functions)
        return jsonify(result), status

    return chatOutlook