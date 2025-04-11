from datetime import datetime, timedelta
from flask import request, jsonify
from config import Config
import json
import re
import openai
import requests
openai.api_key = Config.CHAT_API_KEY
from app.utils.utils import get_user_from_db
from flask_caching import Cache
from .getFunctionSlack import handle_get_request
from .postFunctionSlack import handle_post_request
from app.routes.core.context.ContextHandler import ContextHandler

def process_slack_chat(email, user_query=None, mongo=None, cache=None, refresh_functions=None):
    """Core logic for processing Slack chat requests."""
    hoy = datetime.today().strftime('%Y-%m-%d')

    slack_system_info = f"""
    Eres un intérprete de intenciones avanzado para la API de Slack, pero también debes detectar acciones relacionadas con otras APIs cuando el usuario las mencione en solicitudes múltiples o automatizadas. Tu tarea es analizar el mensaje del usuario, clasificarlo en una categoría general y generar consultas generales. Para GET y POST simples, enfócate solo en Slack. Para solicitudes múltiples y automatizadas, incluye todas las intenciones detectadas (incluso de otras APIs) sin filtrarlas, dejando que un intérprete multitarea las procese. Si el mensaje es ambiguo o no se puede clasificar, solicita aclaración al usuario. Sigue estos pasos:

    1. **Clasificación del Tipo de Solicitud**:
    - **Saludo**: Si el mensaje es un saludo o una interacción social (ej. 'hola', '¿cómo estás?', 'buenos días', 'hey'), clasifica como: `"Es un saludo"`.
    - **Solicitud GET**: Si el usuario pide información con verbos como 'Mándame', 'Pásame', 'Envíame', 'Muéstrame', 'Busca', 'Dame', 'Dime', 'Quiero ver', 'Lista', 'Encuentra', '¿Qué hay?', '¿Cuáles son?' (ej. 'Dame los mensajes del canal #general', 'Busca mensajes de Juan'), clasifica como: `"Es una solicitud GET"`.
    - **Solicitud GET de Contexto (GET_CONTEXT)**: Si el usuario pide detalles sobre un mensaje o canal específico mencionado previamente (ej. 'De qué trata el mensaje de Juan?', 'Qué dice el último mensaje del canal #general?', 'Dame el contenido del mensaje de ayer'), usando frases como 'de qué trata', 'qué dice', 'dame el contenido', 'qué contiene', 'detalle', 'muéstrame el contenido', clasifica como: `"Es una solicitud GET de contexto"`.
    - **Solicitud POST**: Si el usuario pide una acción con verbos como 'Crear', 'Enviar', 'Eliminar', 'Actualizar', 'Escribe', 'Publicar', 'Responde' (ej. 'Enviar mensaje al canal #general', 'Actualizar el mensaje de ayer'), clasifica como: `"Es una solicitud POST"`.
    - **Solicitud Automatizada**: Si el usuario pide algo repetitivo o condicional con frases como 'Cada vez que', 'Siempre que', 'Automáticamente', 'Si pasa X haz Y', 'Cuando ocurra X' (ej. 'Si recibo un mensaje en #general, envía un correo'), clasifica como: `"Es una solicitud automatizada"`.
    - **Solicitud Múltiple**: Si el mensaje combina varias acciones con conjunciones como 'y', 'luego', 'después', o verbos consecutivos (ej. 'Busca mensajes de Juan y envía uno al canal #general', 'Publica un mensaje y sube un archivo a Drive'), clasifica como: `"Es una solicitud múltiple"`.
    - **No Clasificable**: Si el mensaje es demasiado vago, incompleto o no encaja en las categorías anteriores (ej. 'Haz algo', 'Juan', 'Mensaje'), clasifica como: `"No puedo clasificar la solicitud, por favor aclara qué quieres hacer"`.

    2. **Reglas Críticas para Clasificación**:
    - **GET**: Solicitudes de lectura solo para Slack (obtener mensajes, canales, usuarios). Ejemplo: 'Dame los mensajes de #general' → GET.
    - **GET_CONTEXT**: Solicitudes que buscan detalles de un mensaje o canal específico mencionado antes, generalmente usando el historial del chat. Ejemplo: 'De qué trata el mensaje de Juan?' → GET_CONTEXT.
    - **POST**: Acciones de escritura solo para Slack (enviar mensajes, actualizar mensajes, eliminar mensajes). Ejemplo: 'Enviar un mensaje a #general' → POST.
    - **Automatizadas**: Acciones con condiciones, detectando intenciones para Slack y otras APIs mencionadas. Ejemplo: 'Si recibo un mensaje en #general, envía un correo' → Automatizada.
    - **Múltiple**: Detecta conjunciones ('y', 'luego'), verbos consecutivos, o intenciones separadas, incluyendo acciones de cualquier API. Ejemplo: 'Busca mensajes de Juan y envía uno a #general' → Múltiple.
    - **Ambigüedad**: Si un verbo puede ser GET o POST (ej. 'Manda'), analiza el contexto:
        - Si pide información (ej. 'Manda los mensajes de #general'), es GET.
        - Si pide una acción (ej. 'Manda un mensaje a #general'), es POST.
        - Si no hay suficiente contexto, clasifica como "No Clasificable".
    - **Errores del Usuario**: Si falta información clave (ej. 'Busca mensajes' sin especificar dónde), clasifica como "No Clasificable".

    3. **Detección y Generación de Consultas**:
    - Para **GET y POST simples**, genera intenciones solo para Slack:
        - **Slack**: Buscar mensajes, obtener canales, enviar mensajes, actualizar mensajes, eliminar mensajes, responder mensajes.
    - Para **GET_CONTEXT**, genera una intención que describa qué detalle se pide del mensaje o canal (ej. "detalle del mensaje de Juan").
    - Para **Automatizadas y Múltiples**, incluye todas las intenciones detectadas, incluso si involucran otras APIs (ej. Gmail, Drive), sin filtrarlas.
    - Si una acción no encaja con Slack en GET o POST simples, usa 'N/A'.

    4. **Formato de Salida**:
    - Devuelve un string con el tipo de solicitud seguido de un JSON con consultas generales bajo la clave "slack".
    - **GET**: `{{"slack": "<intención>"}}`
    - **GET_CONTEXT**: `{{"slack": "<intención>"}}`
    - **POST**: `{{"slack": "<intención>"}}`
    - **Automatizada**: `{{"slack": [{{"condition": "<condición>", "action": "<acción>"}}, ...]}}`
    - **Múltiple**: `{{"slack": ["<intención 1>", "<intención 2>", ...]}}`
    - **No Clasificable**: `{{"message": "Por favor, aclara qué quieres hacer"}}`
    - **Saludo**: `{{"slack": "N/A"}}`

    5. **Reglas para Consultas Generales**:
    - **GET**: Describe qué obtener en Slack (ej. "obtener mensajes del canal #general"). Si no aplica, clasifica como "No Clasificable".
    - **GET_CONTEXT**: Describe qué detalle se pide (ej. "detalle del mensaje de Juan", "contenido del último mensaje del canal #general"). Si no se especifica un mensaje, usa "detalle del último mensaje mencionado".
    - **POST**: Describe la acción en Slack (ej. "enviar un mensaje al canal #general"). Si no aplica, clasifica como "No Clasificable".
    - **Automatizada**: Divide en condición y acción, incluyendo otras APIs (ej. "condición: recibir un mensaje en #general", "acción: enviar un correo").
    - **Múltiple**: Separa cada intención en una frase clara, incluyendo acciones de otras APIs (ej. "obtener mensajes de Juan", "subir un archivo a Drive").
    - Incluye nombres, canales o datos clave del usuario (ej. "#general", "Juan") si se mencionan.

    6. **Manejo de Casos Especiales**:
    - **Términos Temporales**: Si se mencionan términos como 'hoy', 'mañana', 'ayer', inclúyelos en la intención (ej. 'obtener mensajes de ayer').
    - **Mensajes o Canales Específicos**: Si se pide un mensaje o canal específico (ej. 'el último mensaje de Juan', 'mensajes del canal #general'), inclúyelo en la intención (ej. "obtener el último mensaje de Juan").
    - **Contexto Implícito**: Si el usuario no especifica un mensaje o canal en una solicitud GET_CONTEXT, asume que se refiere al último mensaje o canal mencionado en el historial (ej. 'De qué trata el mensaje?' → "detalle del último mensaje mencionado").

    Ejemplos:
    - "Mandame los mensajes del canal #general" → "Es una solicitud GET" {{"slack": "obtener mensajes del canal #general"}}
    - "Dame los mensajes de Juan" → "Es una solicitud GET" {{"slack": "obtener mensajes de Juan"}}
    - "De qué trata el mensaje de Juan?" → "Es una solicitud GET de contexto" {{"slack": "detalle del mensaje de Juan"}}
    - "Qué dice el último mensaje del canal #general?" → "Es una solicitud GET de contexto" {{"slack": "contenido del último mensaje del canal #general"}}
    - "Enviar mensaje al canal #general" → "Es una solicitud POST" {{"slack": "enviar un mensaje al canal #general"}}
    - "Si recibo un mensaje en #general, envía un correo" → "Es una solicitud automatizada" {{"slack": [{{"condition": "recibir un mensaje en #general", "action": "enviar un correo"}}]}}
    - "Busca mensajes de Juan y envía uno a #general" → "Es una solicitud múltiple" {{"slack": ["obtener mensajes de Juan", "enviar un mensaje a #general"]}}
    - "Hola" → "Es un saludo" {{"slack": "N/A"}}
    - "Sube un archivo a Drive" → "No puedo clasificar la solicitud, por favor aclara qué quieres hacer" {{"message": "Esto no es una acción para Slack, ¿qué quieres hacer con Slack?"}}
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
            if not refresh_tokens_dict or "slack" not in refresh_tokens_dict:
                cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
                return user

            integrations = user.get("integrations", {})
            tokens_to_refresh = {
                "slack": refresh_tokens_dict["slack"]
            } if "slack" in integrations and integrations["slack"].get("refresh_token") not in (None, "n/a") else {}

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

        if data and "mensajes" in message.lower():
            message_info = "\n".join(
                f"De: {item['user']} | Texto: {item['text']}"
                for item in data
            )
            base_text = f"El usuario pidió mensajes y esto encontré:\n{message}\nDetalles:\n{message_info}"
        else:
            base_text = f"El usuario pidió algo y esto obtuve:\n{message}" + (f"\nDetalles: {str(data)}" if data else "")

        prompt = f"""
        Debes responder la petición del usuario: {user_query}
        Eres un asistente de Slack súper amigable y útil, con un tono relajado y natural, como si charlaras con un amigo. Usa emojis sutiles para darle onda, pero sin exagerar. Basándote en esta info, arma una respuesta concisa y en párrafo que resuma los resultados de forma práctica y clara:

        {base_text}

        - Si hay resultados de mensajes, haz un resumen breve y útil, mencionando cuántos mensajes encontré y algo relevante (como quién los mandó o un detalle interesante). No listes todo como tabla, solo destaca lo más importante.
        - Si no hay resultados, di algo amable y sugiere ajustar la búsqueda si hace falta.
        - Habla en primera persona y evita sonar robótico o repetir los datos crudos tal cual.
        NO INCLUYAS LINKS y responde amigable pero FORMALMENTE
        """

        try:
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Eres un asistente de Slack amigable."},
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
            return {"message": "¡Ey! No me diste ninguna query, ¿qué quieres que haga con Slack? 💬"}, 400

    if not email:
        return {"message": "¡Órale! Necesito tu email pa’ trabajar, ¿me lo pasas? 😅"}, 400
    if not user_query:
        return {"message": "¡Ey! No me diste ninguna query, ¿qué quieres que haga con Slack? 💬"}, 400

    user = get_user_with_refreshed_tokens(email)
    if not user:
        return {"message": "No encontré a este usuario, ¿seguro que está registrado? 😕"}, 404

    if "chats" not in user or not any(chat.get("name") == "SlackChat" for chat in user.get("chats", [])):
        mongo.database.usuarios.update_one(
            {"correo": email},
            {"$set": {"chats": [{"name": "SlackChat", "messages": []}]}} if "chats" not in user else {"$push": {"chats": {"name": "SlackChat", "messages": []}}},
            upsert=True
        )
        user = get_user_with_refreshed_tokens(email)
    usuario = mongo.database.usuarios.find_one({"correo": email})
    slack_chat = next(
        (chat for chat in usuario.get("chats", []) if isinstance(chat, dict) and chat.get("name") == "SlackChat"),
        None
    )

    if not slack_chat:
        return {"message": "¡Uy! Algo salió mal al preparar el chat, ¿intentamos otra vez? 😓"}, 500

    timestamp = datetime.utcnow().isoformat()
    user_message = {"role": "user", "content": user_query, "timestamp": timestamp}

    try:
        prompt = f"""
            Interpreta esta query para Slack: "{user_query}"
            Devuelve un JSON con esta estructura:
            {{
            "peticion": "GET" | "POST" | "SALUDO" | "AUTOMATIZADA" | "MULTIPLE" | "NO_CLASIFICABLE" | "GET_CONTEXT",
            "accion": "buscar" | "enviar" | "actualizar" | "eliminar" | "detalle_mensaje" | null (si es saludo o no clasificable),
            "solicitud": "<detalles específicos>" | null (si no aplica) | [array de acciones para MULTIPLE] | [{{"condition": "...", "action": "..."}} para AUTOMATIZADA]
            }}

            Reglas:
            1. Si es un saludo (ej. "hola"), responde un string como "SALUDO".
            2. Para GET, agrupa verbos de lectura como "dame", "mándame", "buscar", "muéstrame", "lista", "encuentra" en "accion": "buscar".
            - Si la query menciona "mensaje", "mensajes" seguido de un término (ej. "#general", "Juan"), asume que es un canal o usuario y usa "solicitud": "mensajes de <término>".
            3. Para GET de contexto (GET_CONTEXT), detecta si el usuario pide detalles sobre un mensaje específico mencionado antes (ej. "De qué trata el mensaje de Juan?", "Qué dice el mensaje del canal #general") usando verbos o frases como "de qué trata", "qué dice", "detalle", "muéstrame el contenido", "qué contiene", "dame el contenido". Usa "peticion": "GET_CONTEXT", "accion": "detalle_mensaje", "solicitud": "<término específico del mensaje>", donde el término es el usuario o canal mencionado (ej. "Juan", "#general"). Si no se menciona un término claro, usa el último mensaje mencionado en el historial.
            4. Para POST, agrupa verbos en estas categorías:
            - "enviar": "enviar", "manda", "envía", "publicar"
            - "actualizar": "actualizar", "modificar", "cambiar"
            - "eliminar": "eliminar", "borrar", "quitar"
            5. Si es AUTOMATIZADA o MULTIPLE, usa arrays según el system prompt.
            6. Si no se entiende, usa "peticion": "NO_CLASIFICABLE", "accion": null, "solicitud": "Por favor, aclara qué quieres hacer".

            Ejemplos:
            - "Holaaaa" → {{"peticion": "SALUDO", "accion": null, "solicitud": null}}
            - "Mándame los mensajes de #general" → {{"peticion": "GET", "accion": "buscar", "solicitud": "mensajes del canal #general"}}
            - "De qué trata el mensaje de Juan?" → {{"peticion": "GET_CONTEXT", "accion": "detalle_mensaje", "solicitud": "Juan"}}
            - "Enviar mensaje al canal #general hola" → {{"peticion": "POST", "accion": "enviar", "solicitud": "mensaje al canal #general hola"}}
            - "Si recibo mensaje en #general, envía correo" → {{"peticion": "AUTOMATIZADA", "accion": null, "solicitud": [{{"condition": "recibo mensaje en #general", "action": "envía correo"}}]}}
            """
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": slack_system_info},
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
            greeting_prompt = f"El usuario dijo '{user_query}', responde de manera cálida y amigable con emojis. Menciona que eres su asistente personalizado de Slack."
            greeting_response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": "Eres su asistente personal de Slack muy amigable."}, {"role": "user", "content": greeting_prompt}],
                max_tokens=200
            )
            result = greeting_response.choices[0].message.content.strip()
            status = 200
        elif "get_context" in peticion.lower():
            context_handler = ContextHandler(mongo.database)
            result, status = context_handler.get_chat_context(
                email=email,
                chat_name="SlackChat",
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
            {"correo": email, "chats.name": "SlackChat"},
            {"$push": {"chats.$.messages": {"$each": [user_message, assistant_message]}}}
        )

        return {"message": result}

    except Exception as e:
        return {"message": f"¡Ay, caray! Algo se rompió: {str(e)} 😓"}, 500

def setup_slack_chat(app, mongo, cache, refresh_functions):
    """Register Slack chat route."""
    @app.route("/api/chat/slack", methods=["POST"])
    def chatSlack():
        email = request.args.get("email")
        data = request.get_json() or {}
        user_query = (
            data.get("messages", [{}])[-1].get("content")
            if data.get("messages")
            else request.args.get("query")
        )
        result = process_slack_chat(email, user_query, mongo, cache, refresh_functions)
        return jsonify(result)

    return chatSlack