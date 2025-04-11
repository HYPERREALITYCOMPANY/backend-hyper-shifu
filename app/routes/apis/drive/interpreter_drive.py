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
from .getFunctionDrive import handle_get_request
from .postFunctionDrive import handle_post_request
from app.routes.core.context.ContextHandler import ContextHandler

def process_drive_chat(email, user_query=None, mongo=None, cache=None, refresh_functions=None):
    """Core logic for processing Google Drive chat requests."""
    hoy = datetime.today().strftime('%Y-%m-%d')

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

    drive_system_info = f"""
    Eres un intérprete de intenciones avanzado para la API de Google Drive, pero también debes detectar acciones relacionadas con otras APIs cuando el usuario las mencione en solicitudes múltiples o automatizadas. Tu tarea es analizar el mensaje del usuario, clasificarlo en una categoría general y generar consultas generales. Para GET y POST simples, enfócate solo en Google Drive. Para solicitudes múltiples y automatizadas, incluye todas las intenciones detectadas (incluso de otras APIs) sin filtrarlas, dejando que un intérprete multitarea las procese. Si el mensaje es ambiguo o no se puede clasificar, solicita aclaración al usuario. Sigue estos pasos:

    1. **Clasificación del Tipo de Solicitud**:
    - **Saludo**: Si el mensaje es un saludo o interacción social (ej. 'hola', '¿cómo estás?', 'hey'), clasifica como: `"Es un saludo"`.
    - **Solicitud GET**: Si el usuario pide información con verbos como 'Mándame', 'Pásame', 'Busca', 'Dame', 'Dime', 'Quiero ver', 'Lista', 'Encuentra', '¿Qué hay?', '¿Cuáles son?' (ej. 'Dame los archivos en Proyecto X', 'Busca archivos de Juan'), clasifica como: `"Es una solicitud GET"`.
    - **Solicitud GET de Contexto (GET_CONTEXT)**: Si el usuario pide detalles sobre un archivo específico mencionado previamente (ej. 'De qué trata el archivo doc1.txt?', 'Qué contiene el archivo en Proyecto X?', 'Dame el contenido del archivo de ayer'), usando frases como 'de qué trata', 'qué contiene', 'dame el contenido', 'detalle', 'muéstrame el contenido', clasifica como: `"Es una solicitud GET de contexto"`.
    - **Solicitud POST**: Si el usuario pide una acción con verbos como 'Subir', 'Crear', 'Eliminar', 'Actualizar', 'Mover', 'Escribe' (ej. 'Subir archivo doc1.txt a Proyecto X', 'Eliminar archivo doc1.txt'), clasifica como: `"Es una solicitud POST"`.
    - **Solicitud Automatizada**: Si el usuario pide algo repetitivo o condicional con frases como 'Cada vez que', 'Siempre que', 'Automáticamente', 'Si pasa X haz Y', 'Cuando ocurra X' (ej. 'Si subo un archivo a Proyecto X, envía un correo'), clasifica como: `"Es una solicitud automatizada"`.
    - **Solicitud Múltiple**: Si el mensaje combina varias acciones con conjunciones como 'y', 'luego', 'después', o verbos consecutivos (ej. 'Busca archivos en Proyecto X y sube uno a Drive', 'Sube un archivo y envía un mensaje'), clasifica como: `"Es una solicitud múltiple"`.
    - **No Clasificable**: Si el mensaje es vago o incompleto (ej. 'Haz algo', 'Archivo'), clasifica como: `"No puedo clasificar la solicitud, por favor aclara qué quieres hacer"`.

    2. **Reglas Críticas para Clasificación**:
    - **GET**: Solicitudes de lectura solo para Google Drive (obtener archivos, carpetas). Ejemplo: 'Dame los archivos en Proyecto X' → GET.
    - **GET_CONTEXT**: Solicitudes que buscan detalles de un archivo específico mencionado antes, usando el historial si aplica. Ejemplo: 'De qué trata el archivo doc1.txt?' → GET_CONTEXT.
    - **POST**: Acciones de escritura solo para Google Drive (subir archivos, crear carpetas, eliminar archivos). Ejemplo: 'Subir archivo doc1.txt' → POST.
    - **Automatizadas**: Acciones con condiciones, detectando intenciones para Drive y otras APIs. Ejemplo: 'Si subo un archivo a Proyecto X, envía un correo' → Automatizada.
    - **Múltiple**: Detecta conjunciones ('y', 'luego'), incluyendo acciones de cualquier API. Ejemplo: 'Busca archivos en Proyecto X y sube uno' → Múltiple.
    - **Ambigüedad**: Si un verbo puede ser GET o POST (ej. 'Manda'), analiza el contexto:
        - Si pide información (ej. 'Manda los archivos de Proyecto X'), es GET.
        - Si pide una acción (ej. 'Manda un archivo a Proyecto X'), es POST.
        - Si no hay suficiente contexto, clasifica como "No Clasificable".
    - **Errores del Usuario**: Si falta información clave (ej. 'Busca archivos' sin especificar dónde), clasifica como "No Clasificable".

    3. **Detección y Generación de Consultas**:
    - Para **GET y POST simples**, genera intenciones solo para Google Drive:
        - **Drive**: Buscar archivos, obtener carpetas, subir archivos, actualizar archivos, eliminar archivos.
    - Para **GET_CONTEXT**, genera una intención que describa qué detalle se pide del archivo (ej. "detalle del archivo doc1.txt").
    - Para **Automatizadas y Múltiples**, incluye todas las intenciones detectadas, incluso si involucran otras APIs (ej. Gmail, Slack), sin filtrarlas.
    - Si una acción no encaja con Drive en GET o POST simples, usa 'N/A'.

    4. **Formato de Salida**:
    - Devuelve un string con el tipo de solicitud seguido de un JSON con consultas generales bajo la clave "drive".
    - **GET**: `{{"drive": "<intención>"}}`
    - **GET_CONTEXT**: `{{"drive": "<intención>"}}`
    - **POST**: `{{"drive": "<intención>"}}`
    - **Automatizada**: `{{"drive": [{{"condition": "<condición>", "action": "<acción>"}}, ...]}}`
    - **Múltiple**: `{{"drive": ["<intención 1>", "<intención 2>", ...]}}`
    - **No Clasificable**: `{{"message": "Por favor, aclara qué quieres hacer"}}`
    - **Saludo**: `{{"drive": "N/A"}}`

    5. **Reglas para Consultas Generales**:
    - **GET**: Describe qué obtener en Drive (ej. "obtener archivos en Proyecto X"). Si no aplica, clasifica como "No Clasificable".
    - **GET_CONTEXT**: Describe qué detalle se pide (ej. "detalle del archivo doc1.txt", "contenido del archivo en Proyecto X"). Si no se especifica un archivo, usa "detalle del último archivo mencionado".
    - **POST**: Describe la acción en Drive (ej. "subir archivo doc1.txt a Proyecto X"). Si no aplica, clasifica como "No Clasificable".
    - **Automatizada**: Divide en condición y acción, incluyendo otras APIs (ej. "condición: subir un archivo a Proyecto X", "acción: enviar un correo").
    - **Múltiple**: Separa cada intención en una frase clara, incluyendo acciones de otras APIs (ej. "obtener archivos en Proyecto X", "enviar un mensaje en Slack").
    - Incluye nombres de archivos o carpetas clave del usuario (ej. "doc1.txt", "Proyecto X") si se mencionan.

    6. **Manejo de Casos Especiales**:
    - **Términos Temporales**: Si se mencionan términos como 'hoy', 'mañana', 'ayer', inclúyelos en la intención (ej. 'obtener archivos de ayer').
    - **Archivos o Carpetas Específicos**: Si se pide un archivo o carpeta específica (ej. 'el archivo doc1.txt'), inclúyelo en la intención (ej. "obtener el archivo doc1.txt").
    - **Contexto Implícito**: Si el usuario no especifica un archivo o carpeta en una solicitud GET_CONTEXT, asume que se refiere al último archivo o carpeta mencionada en el historial (ej. 'De qué trata el archivo?' → "detalle del último archivo mencionado").

    Ejemplos:
    - "Mandame los archivos en Proyecto X" → "Es una solicitud GET" {{"drive": "obtener archivos en Proyecto X"}}
    - "Dame los archivos de Juan" → "Es una solicitud GET" {{"drive": "obtener archivos de Juan"}}
    - "De qué trata el archivo doc1.txt?" → "Es una solicitud GET de contexto" {{"drive": "detalle del archivo doc1.txt"}}
    - "Qué contiene el archivo en Proyecto X?" → "Es una solicitud GET de contexto" {{"drive": "contenido del archivo en Proyecto X"}}
    - "Subir archivo doc1.txt a Proyecto X" → "Es una solicitud POST" {{"drive": "subir archivo doc1.txt a Proyecto X"}}
    - "Si subo un archivo a Proyecto X, envía un correo" → "Es una solicitud automatizada" {{"drive": [{{"condition": "subir un archivo a Proyecto X", "action": "enviar un correo"}}]}}
    - "Busca archivos en Proyecto X y sube uno" → "Es una solicitud múltiple" {{"drive": ["obtener archivos en Proyecto X", "subir un archivo"]}}
    - "Hola" → "Es un saludo" {{"drive": "N/A"}}
    - "Enviar mensaje a Slack" → "No puedo clasificar la solicitud, por favor aclara qué quieres hacer" {{"message": "Esto no es una acción para Drive, ¿qué quieres hacer con Drive?"}}
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
            if not refresh_tokens_dict or "drive" not in refresh_tokens_dict:
                cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
                return user

            integrations = user.get("integrations", {})
            tokens_to_refresh = {
                "drive": refresh_tokens_dict["drive"]
            } if "drive" in integrations and integrations["drive"].get("refresh_token") not in (None, "n/a") else {}

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

        if data and "archivos" in message.lower():
            file_info = "\n".join(
                f"Nombre: {item['file_name']} | URL: {item['url']}"
                for item in data
            )
            base_text = f"El usuario pidió archivos y esto encontré:\n{message}\nDetalles:\n{file_info}"
        else:
            base_text = f"El usuario pidió algo y esto obtuve:\n{message}" + (f"\nDetalles: {str(data)}" if data else "")

        prompt = f"""
        Debes responder la petición del usuario: {user_query}
        Eres un asistente de Google Drive súper amigable y útil, con un tono relajado y natural, como si charlaras con un amigo. Usa emojis sutiles para darle onda, pero sin exagerar. Basándote en esta info, arma una respuesta concisa y en párrafo que resuma los resultados de forma práctica y clara:

        {base_text}

        - Si hay resultados de archivos, haz un resumen breve y útil, mencionando cuántos archivos encontré y algo relevante (como nombres). No listes todo como tabla, solo destaca lo más importante.
        - Si no hay resultados, di algo amable y sugiere ajustar la búsqueda si hace falta.
        - Habla en primera persona y evita sonar robótico o repetir los datos crudos tal cual.
        NO INCLUYAS LINKS y responde amigable pero FORMALMENTE
        """

        try:
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Eres un asistente de Google Drive amigable."},
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

    if "chats" not in user or not any(chat.get("name") == "DriveChat" for chat in user.get("chats", [])):
        mongo.database.usuarios.update_one(
            {"correo": email},
            {"$set": {"chats": [{"name": "DriveChat", "messages": []}]}} if "chats" not in user else {"$push": {"chats": {"name": "DriveChat", "messages": []}}},
            upsert=True
        )
        user = get_user_with_refreshed_tokens(email)
    usuario = mongo.database.usuarios.find_one({"correo": email})
    drive_chat = next(
        (chat for chat in usuario.get("chats", []) if isinstance(chat, dict) and chat.get("name") == "DriveChat"),
        None
    )

    if not drive_chat:
        return {"error": "¡Uy! Algo salió mal al preparar el chat, ¿intentamos otra vez?"}, 500

    timestamp = datetime.utcnow().isoformat()
    user_message = {"role": "user", "content": user_query, "timestamp": timestamp}

    try:
        prompt = f"""
                    Interpreta esta query para Google Drive: "{user_query}"
                    Devuelve un JSON con esta estructura:
                    {{
                    "peticion": "GET" | "POST" | "SALUDO" | "AUTOMATIZADA" | "MULTIPLE" | "NO_CLASIFICABLE" | "GET_CONTEXT",
                    "accion": "buscar" | "subir" | "crear" | "eliminar" | "actualizar" | "detalle_archivo" | null,
                    "solicitud": "<detalles específicos>" | null | [array de acciones para MULTIPLE] | [{{"condition": "...", "action": "..."}} para AUTOMATIZADA]
                    }}

                    Reglas:
                    1. Si es un saludo (ej. "hola"), responde un string como "SALUDO".
                    2. Para GET, agrupa verbos de lectura como "dame", "mándame", "buscar", "lista" en "accion": "buscar".
                    - Si la query menciona "archivo", "archivos" seguido de un término (ej. "Proyecto X", "Juan"), asume que es una carpeta o nombre y usa "solicitud": "archivos en <término>".
                    3. Para GET de contexto (GET_CONTEXT), detecta si el usuario pide detalles sobre un archivo específico mencionado antes (ej. "De qué trata el archivo doc1.txt?", "Qué contiene el archivo en Proyecto X") usando verbos o frases como "de qué trata", "qué contiene", "detalle", "dame el contenido". Usa "peticion": "GET_CONTEXT", "accion": "detalle_archivo", "solicitud": "<término específico del archivo>", donde el término es el nombre del archivo o carpeta mencionada (ej. "doc1.txt", "Proyecto X"). Si no se menciona un término claro, usa el último archivo mencionado en el historial.
                    4. Para POST, agrupa verbos en estas categorías:
                    - "subir": "subir", "envía", "carga"
                    - "crear": "crear", "nueva carpeta"
                    - "eliminar": "eliminar", "borrar", "quitar"
                    - "actualizar": "actualizar", "modificar", "cambiar"
                    5. Si es AUTOMATIZADA o MULTIPLE, usa arrays según el system prompt.
                    6. Si no se entiende, usa "peticion": "NO_CLASIFICABLE", "accion": null, "solicitud": "Por favor, aclara qué quieres hacer".

                    Ejemplos:
                    - "Holaaaa" → {{"peticion": "SALUDO", "accion": null, "solicitud": null}}
                    - "Mándame los archivos en Proyecto X" → {{"peticion": "GET", "accion": "buscar", "solicitud": "archivos en Proyecto X"}}
                    - "De qué trata el archivo doc1.txt?" → {{"peticion": "GET_CONTEXT", "accion": "detalle_archivo", "solicitud": "doc1.txt"}}
                    - "Subir archivo doc1.txt a Proyecto X" → {{"peticion": "POST", "accion": "subir", "solicitud": "archivo doc1.txt a Proyecto X"}}
                    - "Si subo un archivo a Proyecto X, envía correo" → {{"peticion": "AUTOMATIZADA", "accion": null, "solicitud": [{{"condition": "subo un archivo a Proyecto X", "action": "envía correo"}}]}}
                    """
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": drive_system_info},
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
            parsed_response = {"peticion": "NO_CLASIFICABLE", "accion": None, "solicitud": "Por favor, aclara qué quieres hacer"}
            peticion = parsed_response["peticion"]
            accion = parsed_response["accion"]
            solicitud = parsed_response["solicitud"]

        if "saludo" in peticion.lower():
            greeting_prompt = f"El usuario dijo '{user_query}', responde de manera cálida y amigable con emojis. Menciona que eres su asistente personalizado de Google Drive."
            greeting_response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": "Eres su asistente personal de Google Drive muy amigable."}, {"role": "user", "content": greeting_prompt}],
                max_tokens=200
            )
            result = greeting_response.choices[0].message.content.strip()
            status = 200
        elif "get_context" in peticion.lower():
            context_handler = ContextHandler(mongo.database)
            result, status = context_handler.get_chat_context(
                email=email,
                chat_name="DriveChat",
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
            {"correo": email, "chats.name": "DriveChat"},
            {"$push": {"chats.$.messages": {"$each": [user_message, assistant_message]}}}
        )

        return {"message": result}

    except Exception as e:
        return {"message": {"solicitud": "ERROR", "result": {"error": f"¡Ay, caray! Algo se rompió: {str(e)}"}}}, 500

def setup_drive_chat(app, mongo, cache, refresh_functions):
    """Register Google Drive chat route."""
    @app.route("/api/chat/drive", methods=["POST"])
    def chatDrive():
        email = request.args.get("email")
        data = request.get_json() or {}
        user_query = (
            data.get("messages", [{}])[-1].get("content")
            if data.get("messages")
            else request.args.get("query")
        )
        result = process_drive_chat(email, user_query, mongo, cache, refresh_functions)
        print(result)
        return jsonify(result)

    return chatDrive