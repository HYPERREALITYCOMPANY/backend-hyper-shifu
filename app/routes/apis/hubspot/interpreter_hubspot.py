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
from .getFunctionHubspot import handle_get_request
from .postFunctionHubspot import handle_post_request
from app.routes.core.context.ContextHandler import ContextHandler

def process_hubspot_chat(email, user_query=None, mongo=None, cache=None, refresh_functions=None):
    """Core logic for processing HubSpot chat requests."""
    hoy = datetime.today().strftime('%Y-%m-%d')

    hubspot_system_info = f"""
    Eres un intérprete de intenciones avanzado para la API de HubSpot, pero también debes detectar acciones relacionadas con otras APIs cuando el usuario las mencione en solicitudes múltiples o automatizadas. Tu tarea es analizar el mensaje del usuario, clasificarlo en una categoría general y generar consultas generales. Para GET y POST simples, enfócate solo en HubSpot. Para solicitudes múltiples y automatizadas, incluye todas las intenciones detectadas (incluso de otras APIs) sin filtrarlas, dejando que un intérprete multitarea las procese. Si el mensaje es ambiguo o no se puede clasificar, solicita aclaración al usuario. Sigue estos pasos:

    1. **Clasificación del Tipo de Solicitud**:
    - **Saludo**: Si el mensaje es un saludo o interacción social (ej. 'hola', '¿cómo estás?', 'buenos días', 'hey'), clasifica como: `"Es un saludo"`.
    - **Solicitud GET**: Si el usuario pide información con verbos como 'Mándame', 'Pásame', 'Envíame', 'Muéstrame', 'Busca', 'Dame', 'Dime', 'Quiero ver', 'Lista', 'Encuentra', '¿Qué hay?', '¿Cuáles son?' (ej. 'Dame los contactos de mi lista', 'Busca deals de Juan'), clasifica como: `"Es una solicitud GET"`.
    - **Solicitud GET de Contexto (GET_CONTEXT)**: Si el usuario pide detalles sobre un contacto, deal o compañía específica mencionada previamente (ej. 'Qué dice el contacto Juan?', 'Dame los detalles del deal Proyecto X'), usando frases como 'qué dice', 'dame los detalles', 'qué contiene', 'detalle', 'muéstrame los detalles', clasifica como: `"Es una solicitud GET de contexto"`.
    - **Solicitud POST**: Si el usuario pide una acción con verbos como 'Crear', 'Enviar', 'Eliminar', 'Actualizar', 'Agregar', 'Escribe', 'Modificar' (ej. 'Crear contacto Juan', 'Actualizar deal Proyecto X'), clasifica como: `"Es una solicitud POST"`.
    - **Solicitud Automatizada**: Si el usuario pide algo repetitivo o condicional con frases como 'Cada vez que', 'Siempre que', 'Automáticamente', 'Si pasa X haz Y', 'Cuando ocurra X' (ej. 'Si creo un contacto, envía un correo'), clasifica como: `"Es una solicitud automatizada"`.
    - **Solicitud Múltiple**: Si el mensaje combina varias acciones con conjunciones como 'y', 'luego', 'después', o verbos consecutivos (ej. 'Busca contactos y crea uno nuevo', 'Actualiza un deal y envía un correo'), clasifica como: `"Es una solicitud múltiple"`.
    - **No Clasificable**: Si el mensaje es demasiado vago, incompleto o no encaja en las categorías anteriores (ej. 'Haz algo', 'Contacto'), clasifica como: `"No puedo clasificar la solicitud, por favor aclara qué quieres hacer"`.

    2. **Reglas Críticas para Clasificación**:
    - **GET**: Solicitudes de lectura solo para HubSpot (obtener contactos, deals, compañías). Ejemplo: 'Dame los contactos de mi lista' → GET.
    - **GET_CONTEXT**: Solicitudes que buscan detalles de un contacto, deal o compañía específica mencionada antes, usando el historial si aplica. Ejemplo: 'Qué dice el contacto Juan?' → GET_CONTEXT.
    - **POST**: Acciones de escritura solo para HubSpot (crear contactos, actualizar deals, eliminar compañías). Ejemplo: 'Crear contacto Juan' → POST.
    - **Automatizadas**: Acciones con condiciones, detectando intenciones para HubSpot y otras APIs. Ejemplo: 'Si creo un contacto, envía un correo' → Automatizada.
    - **Múltiple**: Detecta conjunciones ('y', 'luego'), incluyendo acciones de cualquier API. Ejemplo: 'Busca contactos y crea uno nuevo' → Múltiple.
    - **Ambigüedad**: Si un verbo puede ser GET o POST (ej. 'Manda'), analiza el contexto:
        - Si pide información (ej. 'Manda los contactos de mi lista'), es GET.
        - Si pide una acción (ej. 'Manda un contacto a HubSpot'), es POST.
        - Si no hay suficiente contexto, clasifica como "No Clasificable".
    - **Errores del Usuario**: Si falta información clave (ej. 'Busca contactos' sin especificar cuáles), clasifica como "No Clasificable".

    3. **Detección y Generación de Consultas**:
    - Para **GET y POST simples**, genera intenciones solo para HubSpot:
        - **HubSpot**: Buscar contactos, obtener deals, crear contactos, actualizar deals, eliminar contactos, etc.
    - Para **GET_CONTEXT**, genera una intención que describa qué detalle se pide del contacto, deal o compañía (ej. "detalle del contacto Juan").
    - Para **Automatizadas y Múltiples**, incluye todas las intenciones detectadas, incluso si involucran otras APIs (ej. Gmail, Slack), sin filtrarlas.
    - Si una acción no encaja con HubSpot en GET o POST simples, usa 'N/A'.

    4. **Formato de Salida**:
    - Devuelve un string con el tipo de solicitud seguido de un JSON con consultas generales bajo la clave "hubspot".
    - **GET**: `{{"hubspot": "<intención>"}}`
    - **GET_CONTEXT**: `{{"hubspot": "<intención>"}}`
    - **POST**: `{{"hubspot": "<intención>"}}`
    - **Automatizada**: `{{"hubspot": [{{"condition": "<condición>", "action": "<acción>"}}, ...]}}`
    - **Múltiple**: `{{"hubspot": ["<intención 1>", "<intención 2>", ...]}}`
    - **No Clasificable**: `{{"message": "Por favor, aclara qué quieres hacer"}}`
    - **Saludo**: `{{"hubspot": "N/A"}}`

    5. **Reglas para Consultas Generales**:
    - **GET**: Describe qué obtener en HubSpot (ej. "obtener contactos de mi lista"). Si no aplica, clasifica como "No Clasificable".
    - **GET_CONTEXT**: Describe qué detalle se pide (ej. "detalle del contacto Juan", "detalle del deal Proyecto X"). Si no se especifica un elemento claro, usa "detalle del último elemento mencionado".
    - **POST**: Describe la acción en HubSpot (ej. "crear contacto Juan"). Si no aplica, clasifica como "No Clasificable".
    - **Automatizada**: Divide en condición y acción, incluyendo otras APIs (ej. "condición: crear un contacto", "acción: enviar un correo").
    - **Múltiple**: Separa cada intención en una frase clara, incluyendo acciones de otras APIs (ej. "obtener contactos", "enviar un correo").
    - Incluye nombres o datos clave del usuario (ej. "Juan", "mañana") si se mencionan.

    6. **Manejo de Casos Especiales**:
    - **Términos Temporales**: Si se mencionan términos como 'hoy', 'mañana', 'ayer', inclúyelos en la intención (ej. 'obtener deals de hoy').
    - **Contactos o Elementos Específicos**: Si se pide un contacto, deal o compañía específica (ej. 'el contacto Juan', 'el deal Proyecto X'), inclúyelo en la intención (ej. "obtener el contacto Juan").
    - **Contexto Implícito**: Si el usuario no especifica un contacto o elemento en una solicitud GET_CONTEXT, asume que se refiere al último elemento mencionado en el historial (ej. 'Qué dice el contacto?' → "detalle del último contacto mencionado").

    Ejemplos:
    - "Dame los contactos de mi lista" → "Es una solicitud GET" {{"hubspot": "obtener contactos de mi lista"}}
    - "Busca deals de Juan" → "Es una solicitud GET" {{"hubspot": "obtener deals de Juan"}}
    - "Qué dice el contacto Juan?" → "Es una solicitud GET de contexto" {{"hubspot": "detalle del contacto Juan"}}
    - "Crear contacto Juan" → "Es una solicitud POST" {{"hubspot": "crear contacto Juan"}}
    - "Si creo un contacto, envía un correo" → "Es una solicitud automatizada" {{"hubspot": [{{"condition": "crear un contacto", "action": "enviar un correo"}}]}}
    - "Busca contactos y crea uno nuevo" → "Es una solicitud múltiple" {{"hubspot": ["ob

tener contactos", "crear un contacto nuevo"]}}
    - "Hola" → "Es un saludo" {{"hubspot": "N/A"}}
    - "Subir archivo a Drive" → "No puedo clasificar la solicitud, por favor aclara qué quieres hacer" {{"message": "Esto no es una acción para HubSpot, ¿qué quieres hacer con HubSpot?"}}
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
            if not refresh_tokens_dict or "hubspot" not in refresh_tokens_dict:
                cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
                return user

            integrations = user.get("integrations", {})
            tokens_to_refresh = {
                "hubspot": refresh_tokens_dict["hubspot"]
            } if "hubspot" in integrations and integrations["hubspot"].get("refresh_token") not in (None, "n/a") else {}

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

        if data and "contactos" in message.lower():
            contact_info = "\n".join(
                f"Nombre: {item['contact_name']} | ID: {item['id']}"
                for item in data
            )
            base_text = f"El usuario pidió contactos y esto encontré:\n{message}\nDetalles:\n{contact_info}"
        else:
            base_text = f"El usuario pidió algo y esto obtuve:\n{message}" + (f"\nDetalles: {str(data)}" if data else "")

        prompt = f"""
        Debes responder la petición del usuario: {user_query}
        Eres un asistente de HubSpot súper amigable y útil, con un tono relajado y natural, como si charlaras con un amigo. Usa emojis sutiles para darle onda, pero sin exagerar. Basándote en esta info, arma una respuesta concisa y en párrafo que resuma los resultados de forma práctica y clara:

        {base_text}

        - Si hay resultados de contactos, haz un resumen breve y útil, mencionando cuántos contactos encontré y algo relevante (como nombres). No listes todo como tabla, solo destaca lo más importante.
        - Si no hay resultados, di algo amable y sugiere ajustar la búsqueda si hace falta.
        - Habla en primera persona y evita sonar robótico o repetir los datos crudos tal cual.
        NO INCLUYAS LINKS y responde amigable pero FORMALMENTE
        """

        try:
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Eres un asistente de HubSpot amigable."},
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
            return {"message": "¡Ey! Dame algo pa’ trabajar, ¿qué quieres hacer con HubSpot? 🤔"}, 400

    if not email:
        return {"message": "¡Órale! Necesito tu email, compa 😅"}, 400
    if not user_query:
        return {"message": "¡Ey! Dame algo pa’ trabajar, ¿qué quieres hacer con HubSpot? 🤔"}, 400

    user = get_user_with_refreshed_tokens(email)
    if not user:
        return {"message": "¡Uy! No te encontré en el sistema, ¿seguro que estás registrado? 😕"}, 404

    if "chats" not in user or not any(chat.get("name") == "HubSpotChat" for chat in user.get("chats", [])):
        mongo.database.usuarios.update_one(
            {"correo": email},
            {"$set": {"chats": [{"name": "HubSpotChat", "messages": []}]}} if "chats" not in user else {"$push": {"chats": {"name": "HubSpotChat", "messages": []}}},
            upsert=True
        )
        user = get_user_with_refreshed_tokens(email)

    usuario = mongo.database.usuarios.find_one({"correo": email})
    hubspot_chat = next(
        (chat for chat in usuario.get("chats", []) if isinstance(chat, dict) and chat.get("name") == "HubSpotChat"),
        None
    )

    if not hubspot_chat:
        return {"message": "¡Qué mala onda! Error al inicializar el chat 😓"}, 500

    timestamp = datetime.utcnow().isoformat()
    user_message = {"role": "user", "content": user_query, "timestamp": timestamp}

    try:
        prompt = f"""
                    Interpreta esta query para HubSpot: "{user_query}"
                    Devuelve un JSON con esta estructura:
                    {{
                    "peticion": "GET" | "POST" | "SALUDO" | "AUTOMATIZADA" | "MULTIPLE" | "NO_CLASIFICABLE" | "GET_CONTEXT",
                    "accion": "buscar" | "crear" | "actualizar" | "eliminar" | "detalle_contacto" | null,
                    "solicitud": "<detalles específicos>" | null | [array de acciones para MULTIPLE] | [{{"condition": "...", "action": "..."}} para AUTOMATIZADA]
                    }}

                    Reglas:
                    1. Si es un saludo (ej. "hola"), responde con "SALUDO".
                    2. Para GET, agrupa verbos de lectura como "dame", "mándame", "busca", "lista" en "accion": "buscar".
                    - Si la query menciona "contactos", "deals" o "compañías" seguido de un término (ej. "mi lista", "Juan"), asume que es un filtro y usa "solicitud": "contactos de <término>".
                    3. Para GET_CONTEXT, detecta si el usuario pide detalles sobre un contacto, deal o compañía específica mencionada antes (ej. "Qué dice el contacto Juan?", "Dame los detalles del deal Proyecto X") usando verbos o frases como "qué dice", "dame los detalles", "detalle", "muéstrame los detalles". Usa "peticion": "GET_CONTEXT", "accion": "detalle_contacto", "solicitud": "<término específico>", donde el término es el nombre del contacto, deal o compañía (ej. "Juan", "Proyecto X"). Si no se menciona un término claro, usa "último elemento mencionado".
                    4. Para POST, agrupa verbos en estas categorías:
                    - "crear": "crear", "añadir", "agregar", "escribe"
                    - "actualizar": "actualizar", "modificar", "cambiar"
                    - "eliminar": "eliminar", "borrar", "quitar"
                    5. Si es AUTOMATIZADA o MULTIPLE, usa arrays según el system prompt.
                    6. Si no se entiende, usa "peticion": "NO_CLASIFICABLE", "accion": null, "solicitud": "Por favor, aclara qué quieres hacer".

                    Ejemplos:
                    - "Holaaaa" → {{"peticion": "SALUDO", "accion": null, "solicitud": null}}
                    - "Dame los contactos de mi lista" → {{"peticion": "GET", "accion": "buscar", "solicitud": "contactos de mi lista"}}
                    - "Qué dice el contacto Juan?" → {{"peticion": "GET_CONTEXT", "accion": "detalle_contacto", "solicitud": "Juan"}}
                    - "Crear contacto Juan" → {{"peticion": "POST", "accion": "crear", "solicitud": "contacto Juan"}}
                    - "Si creo un contacto, envía un correo" → {{"peticion": "AUTOMATIZADA", "accion": null, "solicitud": [{{"condition": "creo un contacto", "action": "envía un correo"}}]}}
                    """
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": hubspot_system_info},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500
        )
        ia_response = response.choices[0].message.content.strip()

        match = re.search(r'\{.*\}', ia_response, re.DOTALL)
        if match:
            parsed_response = json.loads(match.group(0))
            peticion = parsed_response.get("peticion")
            accion = parsed_response.get("accion")
            solicitud = parsed_response.get("solicitud")
        else:
            parsed_response = {"peticion": "NO_CLASIFICABLE", "accion": None, "solicitud": "Por favor, aclara qué quieres hacer"}
            peticion = parsed_response["peticion"]
            accion = parsed_response["accion"]
            solicitud = parsed_response["solicitud"]

        if "saludo" in peticion.lower():
            greeting_prompt = f"El usuario dijo '{user_query}', responde de manera cálida y amigable con emojis. Menciona que eres su asistente personalizado de HubSpot."
            greeting_response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": "Eres su asistente personal de HubSpot muy amigable."}, {"role": "user", "content": greeting_prompt}],
                max_tokens=200
            )
            result = greeting_response.choices[0].message.content.strip()
            status = 200
        elif "get_context" in peticion.lower():
            context_handler = ContextHandler(mongo.database)
            result, status = context_handler.get_chat_context(
                email=email,
                chat_name="HubSpotChat",
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
            {"correo": email, "chats.name": "HubSpotChat"},
            {"$push": {"chats.$.messages": {"$each": [user_message, assistant_message]}}}
        )

        return {"message": result}

    except Exception as e:
        return {"message": f"¡Se puso feo! Error inesperado: {str(e)} 😓"}, 500

def setup_hubspot_chat(app, mongo, cache, refresh_functions):
    """Register HubSpot chat route."""
    @app.route("/api/chat/hubspot", methods=["POST"])
    def chatHubSpot():
        email = request.args.get("email")
        data = request.get_json() or {}
        user_query = (
            data.get("messages", [{}])[-1].get("content")
            if data.get("messages")
            else request.args.get("query")
        )
        result = process_hubspot_chat(email, user_query, mongo, cache, refresh_functions)
        return jsonify(result)

    return chatHubSpot