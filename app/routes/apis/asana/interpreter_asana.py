from datetime import datetime, timedelta
from flask import request, jsonify
from config import Config
import json
import re
import openai
openai.api_key = Config.CHAT_API_KEY
from app.utils.utils import get_user_from_db
from flask_caching import Cache
from .getFunctionAsana import handle_get_request
from .postFunctionAsana import handle_post_request
from app.routes.core.context.ContextHandler import ContextHandler

def process_asana_chat(email, user_query=None, mongo=None, cache=None, refresh_functions=None):
    """Core logic for processing Asana chat requests."""
    hoy = datetime.today().strftime('%Y-%m-%d')
    print("hola asana")

    # If user_query is not provided, extract from request
    if not user_query:
        try:
            data = request.get_json() or {}
            user_query = (
                data.get("messages", [{}])[-1].get("content")
                if data.get("messages")
                else request.args.get("query")
            )
        except Exception:
            return {"error": "¡Ey! No me diste ninguna query, ¿qué quieres que haga?"}, 400

    asana_system_info = f"""
    Eres un intérprete de intenciones avanzado para la API de Asana, pero también debes detectar acciones relacionadas con otras APIs cuando el usuario las mencione en solicitudes múltiples o automatizadas. Tu tarea es analizar el mensaje del usuario, clasificarlo en una categoría general y generar consultas generales. Para GET y POST simples, enfócate solo en Asana. Para solicitudes múltiples y automatizadas, incluye todas las intenciones detectadas (incluso de otras APIs) sin filtrarlas, dejando que un intérprete multitarea las procese. Si el mensaje es ambiguo o no se puede clasificar, solicita aclaración al usuario. Sigue estos pasos:

    1. **Clasificación del Tipo de Solicitud**:
    - **Saludo**: Si el mensaje es un saludo o interacción social (ej. 'hola', '¿qué tal?', 'hey'), clasifica como: `"Es un saludo"`.
    - **Solicitud GET**: Si el usuario pide información con verbos como 'Mándame', 'Pásame', 'Busca', 'Dame', 'Dime', 'Quiero ver', 'Lista', 'Encuentra', '¿Qué hay?', '¿Cuáles son?' (ej. 'Dame las tareas de Proyectos', 'Busca tareas de Juan'), clasifica como: `"Es una solicitud GET"`.
    - **Solicitud GET de Contexto (GET_CONTEXT)**: Si el usuario pide detalles sobre una tarea específica mencionada previamente (ej. '¿Qué dice la tarea Reunión?', 'Dame el contenido de la tarea Proyectos'), usando frases como 'qué dice', 'dame el contenido', 'qué contiene', 'detalle', 'muéstrame el contenido', clasifica como: `"Es una solicitud GET de contexto"`.
    - **Solicitud POST**: Si el usuario pide una acción con verbos como 'Crear', 'Añadir', 'Agregar', 'Escribe', 'Actualizar', 'Eliminar' (ej. 'Crear tarea en Proyectos', 'Eliminar tarea Reunión'), clasifica como: `"Es una solicitud POST"`.
    - **Solicitud Automatizada**: Si el usuario pide algo repetitivo o condicional con frases como 'Cada vez que', 'Siempre que', 'Automáticamente', 'Si pasa X haz Y', 'Cuando ocurra X' (ej. 'Si creo una tarea en Proyectos, envía un correo'), clasifica como: `"Es una solicitud automatizada"`.
    - **Solicitud Múltiple**: Si el mensaje combina varias acciones con conjunciones como 'y', 'luego', 'después', o verbos consecutivos (ej. 'Busca tareas en Proyectos y crea una nueva', 'Crea una tarea y envía un mensaje'), clasifica como: `"Es una solicitud múltiple"`.
    - **No Clasificable**: Si el mensaje es vago o incompleto (ej. 'Haz algo', 'Tarea'), clasifica como: `"No puedo clasificar la solicitud, por favor aclara qué quieres hacer"`.

    2. **Reglas Críticas para Clasificación**:
    - **GET**: Solicitudes de lectura solo para Asana (obtener tareas, proyectos). Ejemplo: 'Dame las tareas de Proyectos' → GET.
    - **GET_CONTEXT**: Solicitudes que buscan detalles de una tarea específica mencionada antes, usando el historial si aplica. Ejemplo: 'Qué dice la tarea Reunión?' → GET_CONTEXT.
    - **POST**: Acciones de escritura solo para Asana (crear tareas, eliminar tareas). Ejemplo: 'Crear tarea en Proyectos' → POST.
    - **Automatizadas**: Acciones con condiciones, detectando intenciones para Asana y otras APIs. Ejemplo: 'Si creo una tarea en Proyectos, envía un correo' → Automatizada.
    - **Múltiple**: Detecta conjunciones ('y', 'luego'), incluyendo acciones de cualquier API. Ejemplo: 'Busca tareas en Proyectos y crea una nueva' → Múltiple.
    - **Ambigüedad**: Si un verbo puede ser GET o POST (ej. 'Manda'), analiza el contexto:
        - Si pide información (ej. 'Manda las tareas de Proyectos'), es GET.
        - Si pide una acción (ej. 'Manda una tarea a Proyectos'), es POST.
        - Si no hay suficiente contexto, clasifica como "No Clasificable".
    - **Errores del Usuario**: Si falta información clave (ej. 'Busca tareas' sin especificar dónde), clasifica como "No Clasificable".

    3. **Detección y Generación de Consultas**:
    - Para **GET y POST simples**, genera intenciones solo para Asana:
        - **Asana**: Buscar tareas, obtener proyectos, crear tareas, actualizar tareas, eliminar tareas.
    - Para **GET_CONTEXT**, genera una intención que describa qué detalle se pide de la tarea (ej. "detalle de la tarea Reunión").
    - Para **Automatizadas y Múltiples**, incluye todas las intenciones detectadas, incluso si involucran otras APIs (ej. Gmail, Slack), sin filtrarlas.
    - Si una acción no encaja con Asana en GET o POST simples, usa 'N/A'.

    4. **Formato de Salida**:
    - Devuelve un string con el tipo de solicitud seguido de un JSON con consultas generales bajo la clave "asana".
    - **GET**: `{{"asana": "<intención>"}}`
    - **GET_CONTEXT**: `{{"asana": "<intención>"}}`
    - **POST**: `{{"asana": "<intención>"}}`
    - **Automatizada**: `{{"asana": [{{"condition": "<condición>", "action": "<acción>"}}, ...]}}`
    - **Múltiple**: `{{"asana": ["<intención 1>", "<intención 2>", ...]}}`
    - **No Clasificable**: `{{"message": "Por favor, aclara qué quieres hacer"}}`
    - **Saludo**: `{{"asana": "N/A"}}`

    5. **Reglas para Consultas Generales**:
    - **GET**: Describe qué obtener en Asana (ej. "obtener tareas en Proyectos"). Si no aplica, clasifica como "No Clasificable".
    - **GET_CONTEXT**: Describe qué detalle se pide (ej. "detalle de la tarea Reunión", "contenido de la tarea en Proyectos"). Si no se especifica una tarea, usa "detalle de la última tarea mencionada".
    - **POST**: Describe la acción en Asana (ej. "crear tarea en Proyectos"). Si no aplica, clasifica como "No Clasificable".
    - **Automatizada**: Divide en condición y acción, incluyendo otras APIs (ej. "condición: crear una tarea en Proyectos", "acción: enviar un correo").
    - **Múltiple**: Separa cada intención en una frase clara, incluyendo acciones de otras APIs (ej. "obtener tareas en Proyectos", "enviar un mensaje en Slack").
    - Incluye nombres de tareas o proyectos clave del usuario (ej. "Reunión", "Proyectos") si se mencionan.

    6. **Manejo de Casos Especiales**:
    - **Términos Temporales**: Si se mencionan términos como 'hoy', 'mañana', 'ayer', inclúyelos en la intención (ej. 'obtener tareas de hoy').
    - **Tareas o Proyectos Específicos**: Si se pide una tarea o proyecto específico (ej. 'la tarea Reunión'), inclúyelo en la intención (ej. "obtener la tarea Reunión").
    - **Contexto Implícito**: Si el usuario no especifica una tarea o proyecto en una solicitud GET_CONTEXT, asume que se refiere a la última tarea o proyecto mencionado en el historial (ej. 'Qué dice la tarea?' → "detalle de la última tarea mencionada").

    Ejemplos:
    - "Mandame las tareas en Proyectos" → "Es una solicitud GET" {{"asana": "obtener tareas en Proyectos"}}
    - "Dame las tareas de Juan" → "Es una solicitud GET" {{"asana": "obtener tareas de Juan"}}
    - "Qué dice la tarea Reunión?" → "Es una solicitud GET de contexto" {{"asana": "detalle de la tarea Reunión"}}
    - "Crear tarea en Proyectos" → "Es una solicitud POST" {{"asana": "crear tarea en Proyectos"}}
    - "Si creo una tarea en Proyectos, envía un correo" → "Es una solicitud automatizada" {{"asana": [{{"condition": "crear una tarea en Proyectos", "action": "enviar un correo"}}]}}
    - "Busca tareas en Proyectos y crea una nueva" → "Es una solicitud múltiple" {{"asana": ["obtener tareas en Proyectos", "crear tarea"]}}
    - "Hola" → "Es un saludo" {{"asana": "N/A"}}
    - "Enviar mensaje a Slack" → "No puedo clasificar la solicitud, por favor aclara qué quieres hacer" {{"message": "Esto no es una acción para Asana, ¿qué quieres hacer con Asana?"}}
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
                "asana": refresh_tokens_dict["asana"]
            } if "asana" in integrations and integrations["asana"].get("refresh_token") not in (None, "n/a") else {}

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


    print("Hola Asana, estoy procesando la solicitud...")
    def generate_prompt(get_result):
        result = get_result.get("result", {})
        message = result.get("message", "No se pudo procesar la solicitud, algo salió mal.")
        data = result.get("data", None)

        if data and "tareas" in message.lower():
            task_info = "\n".join(
                f"Título: {item['name']} | ID: {item['id']}"
                for item in data
            )
            base_text = f"El usuario pidió tareas y esto encontré:\n{message}\nDetalles:\n{task_info}"
        else:
            base_text = f"El usuario pidió algo y esto obtuve:\n{message}" + (f"\nDetalles: {str(data)}" if data else "")

        prompt = f"""
        Debes responder la petición del usuario: {user_query}
        Eres un asistente de Asana súper amigable y útil, con un tono relajado y natural, como si charlaras con un amigo. Usa emojis sutiles para darle onda, pero sin exagerar. Basándote en esta info, arma una respuesta concisa y en párrafo que resuma los resultados de forma práctica y clara:

        {base_text}

        - Si hay resultados de tareas, haz un resumen breve y útil, mencionando cuántas tareas encontré y algo relevante (como nombres). No listes todo como tabla, solo destaca lo más importante.
        - Si no hay resultados, di algo amable y sugiere ajustar la búsqueda si hace falta.
        - Habla en primera persona y evita sonar robótico o repetir los datos crudos tal cual.
        NO INCLUYAS LINKS y responde amigable pero FORMALMENTE
        """

        try:
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Eres un asistente de Asana amigable."},
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

    user = get_user_from_db(email, cache, mongo)
    if not user:
        return {"error": "No encontré a este usuario, ¿seguro que está registrado?"}, 404

    if "chats" not in user or not any(chat.get("name") == "AsanaChat" for chat in user.get("chats", [])):
        mongo.database.usuarios.update_one(
            {"correo": email},
            {"$set": {"chats": [{"name": "AsanaChat", "messages": []}]}} if "chats" not in user else {"$push": {"chats": {"name": "AsanaChat", "messages": []}}},
            upsert=True
        )
        user = get_user_from_db(email, cache, mongo)
    usuario = mongo.database.usuarios.find_one({"correo": email})
    asana_chat = next(
        (chat for chat in usuario.get("chats", []) if isinstance(chat, dict) and chat.get("name") == "AsanaChat"),
        None
    )

    if not asana_chat:
        return {"error": "¡Uy! Algo salió mal al preparar el chat, ¿intentamos otra vez?"}, 500

    timestamp = datetime.utcnow().isoformat()
    user_message = {"role": "user", "content": user_query, "timestamp": timestamp}

    try:
        prompt = f"""
            Interpreta esta query para Asana: "{user_query}"
            Devuelve un JSON con esta estructura:
            {{
            "peticion": "GET" | "POST" | "SALUDO" | "AUTOMATIZADA" | "MULTIPLE" | "NO_CLASIFICABLE" | "GET_CONTEXT",
            "accion": "buscar" | "crear" | "detalle_tarea" | null,
            "solicitud": "<detalles específicos>" | null | [array de acciones para MULTIPLE] | [{{"condition": "...", "action": "..."}} para AUTOMATIZADA]
            }}

            Reglas:
            1. Si es un saludo (ej. "hola"), responde con "SALUDO".
            2. Para GET, agrupa verbos de lectura como "dame", "mándame", "busca", "lista" en "accion": "buscar".
            - Si la query menciona "tarea", "tareas" seguido de un término (ej. "Proyectos", "Juan"), asume que es un proyecto o nombre y usa "solicitud": "tareas en <término>".
            3. Para GET_CONTEXT, detecta si el usuario pide detalles sobre una tarea específica mencionada antes (ej. "Qué dice la tarea Reunión?", "Dame el contenido de la tarea Proyectos") usando verbos o frases como "qué dice", "dame el contenido", "detalle", "muéstrame el contenido". Usa "peticion": "GET_CONTEXT", "accion": "detalle_tarea", "solicitud": "<término específico de la tarea>", donde el término es el nombre de la tarea o proyecto mencionado (ej. "Reunión", "Proyectos"). Si no se menciona un término claro, usa "última tarea mencionada".
            4. Para POST, agrupa verbos en estas categorías:
            - "crear": "crear", "añadir", "agregar", "escribe"
            - "actualizar": "actualizar", "modificar", "cambiar"
            - "eliminar": "eliminar", "borrar", "quitar"
            5. Si es AUTOMATIZADA o MULTIPLE, usa arrays según el system prompt.
            6. Si no se entiende, usa "peticion": "NO_CLASIFICABLE", "accion": null, "solicitud": "Por favor, aclara qué quieres hacer".

            Ejemplos:
            - "Holaaaa" → {{"peticion": "SALUDO", "accion": null, "solicitud": null}}
            - "Mándame las tareas en Proyectos" → {{"peticion": "GET", "accion": "buscar", "solicitud": "tareas en Proyectos"}}
            - "Qué dice la tarea Reunión?" → {{"peticion": "GET_CONTEXT", "accion": "detalle_tarea", "solicitud": "Reunión"}}
            - "Crear tarea en Proyectos" → {{"peticion": "POST", "accion": "crear", "solicitud": "tarea en Proyectos"}}
            - "Si creo una tarea en Proyectos, envía correo" → {{"peticion": "AUTOMATIZADA", "accion": null, "solicitud": [{{"condition": "creo una tarea en Proyectos", "action": "envía correo"}}]}}
            """
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": asana_system_info},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500
        )
        ia_response = response.choices[0].message.content.strip()
        print(ia_response)
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
            parsed_response = {"peticion": "NO_CLASIFICABLE", "accion": None, "solicitud": "Por favor, aclara qué quieres hacer"}
            peticion = parsed_response["peticion"]
            accion = parsed_response["accion"]
            solicitud = parsed_response["solicitud"]
        
        print(peticion)
        if "saludo" in peticion.lower():
            greeting_prompt = f"El usuario dijo '{user_query}', responde de manera cálida y amigable con emojis. Menciona que eres su asistente personalizado de Asana."
            greeting_response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": "Eres su asistente personal de Asana muy amigable."}, {"role": "user", "content": greeting_prompt}],
                max_tokens=200
            )
            result = greeting_response.choices[0].message.content.strip()
            status = 200
        elif "get_context" in peticion.lower():
            context_handler = ContextHandler(mongo.database)
            result, status = context_handler.get_chat_context(
                email=email,
                chat_name="AsanaChat",
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
            {"correo": email, "chats.name": "AsanaChat"},
            {"$push": {"chats.$.messages": {"$each": [user_message, assistant_message]}}}
        )

        return {"message": result}

    except Exception as e:
        return {"message": {"solicitud": "ERROR", "result": {"error": f"¡Ay, caray! Algo se rompió: {str(e)}"}}}, 500

def setup_asana_chat(app, mongo, cache, refresh_functions):
    """Register Asana chat route."""
    @app.route("/api/chat/asana", methods=["POST"])
    def chatAsana():
        email = request.args.get("email")
        data = request.get_json() or {}
        user_query = (
            data.get("messages", [{}])[-1].get("content")
            if data.get("messages")
            else request.args.get("query")
        )
        result = process_asana_chat(email, user_query, mongo, cache, refresh_functions)
        return jsonify(result)

    return chatAsana