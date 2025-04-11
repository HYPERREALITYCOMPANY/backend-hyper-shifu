from datetime import datetime
from flask import request, jsonify
from config import Config
import json
import re
import openai
openai.api_key = Config.CHAT_API_KEY
from app.utils.utils import get_user_from_db
from flask_caching import Cache
from .getFunctionDropbox import handle_get_request
from .postFunctionDropbox import handle_post_request
from app.routes.core.context.ContextHandler import ContextHandler

def process_dropbox_chat(email, user_query=None, mongo=None, cache=None, refresh_functions=None):
    """Core logic for processing Dropbox chat requests."""
    dropbox_system_info = f"""
    Eres un intérprete de intenciones avanzado para la API de Dropbox, pero también debes detectar acciones relacionadas con otras APIs cuando el usuario las mencione en solicitudes múltiples o automatizadas. Tu tarea es analizar el mensaje del usuario, clasificarlo en una categoría general y generar consultas generales. Para GET y POST simples, enfócate solo en Dropbox. Para solicitudes múltiples y automatizadas, incluye todas las intenciones detectadas (incluso de otras APIs) sin filtrarlas, dejando que un intérprete multitarea las procese. Si el mensaje es ambiguo o no se puede clasificar, solicita aclaración al usuario. Sigue estos pasos:

    1. **Clasificación del Tipo de Solicitud**:
    - **Saludo**: Si el mensaje es un saludo o interacción social (ej. 'hola', '¿cómo estás?', 'hey'), clasifica como: `"Es un saludo"`.
    - **Solicitud GET**: Si el usuario pide información con verbos como 'Mándame', 'Pásame', 'Busca', 'Dame', 'Dime', 'Quiero ver', 'Lista', 'Encuentra', '¿Qué hay?', '¿Cuáles son?' (ej. 'Dame los archivos en Proyectos', 'Busca archivos de Juan'), clasifica como: `"Es una solicitud GET"`.
    - **Solicitud GET de Contexto (GET_CONTEXT)**: Si el usuario pide detalles sobre un archivo específico mencionado previamente (ej. 'De qué trata el archivo doc1.txt?', 'Qué contiene el archivo en Proyectos?', 'Dame el contenido del archivo de ayer'), usando frases como 'de qué trata', 'qué contiene', 'dame el contenido', 'detalle', 'muéstrame el contenido', clasifica como: `"Es una solicitud GET de contexto"`.
    - **Solicitud POST**: Si el usuario pide una acción con verbos como 'Subir', 'Crear', 'Eliminar', 'Mover', 'Escribe' (ej. 'Subir archivo doc1.txt a Proyectos', 'Eliminar archivo doc1.txt'), clasifica como: `"Es una solicitud POST"`.
    - **Solicitud Automatizada**: Si el usuario pide algo repetitivo o condicional con frases como 'Cada vez que', 'Siempre que', 'Automáticamente', 'Si pasa X haz Y', 'Cuando ocurra X' (ej. 'Si subo un archivo a Proyectos, envía un correo'), clasifica como: `"Es una solicitud automatizada"`.
    - **Solicitud Múltiple**: Si el mensaje combina varias acciones con conjunciones como 'y', 'luego', 'después', o verbos consecutivos (ej. 'Busca archivos en Proyectos y sube uno a Drive', 'Sube un archivo y envía un mensaje'), clasifica como: `"Es una solicitud múltiple"`.
    - **No Clasificable**: Si el mensaje es vago o incompleto (ej. 'Haz algo', 'Archivo'), clasifica como: `"No puedo clasificar la solicitud, por favor aclara qué quieres hacer"`.

    2. **Reglas Críticas para Clasificación**:
    - **GET**: Solicitudes de lectura solo para Dropbox (obtener archivos, carpetas). Ejemplo: 'Dame los archivos en Proyectos' → GET.
    - **GET_CONTEXT**: Solicitudes que buscan detalles de un archivo específico mencionado antes, usando el historial si aplica. Ejemplo: 'De qué trata el archivo doc1.txt?' → GET_CONTEXT.
    - **POST**: Acciones de escritura solo para Dropbox (subir archivos, crear carpetas, eliminar archivos). Ejemplo: 'Subir archivo doc1.txt' → POST.
    - **Automatizadas**: Acciones con condiciones, detectando intenciones para Dropbox y otras APIs. Ejemplo: 'Si subo un archivo a Proyectos, envía un correo' → Automatizada.
    - **Múltiple**: Detecta conjunciones ('y', 'luego'), incluyendo acciones de cualquier API. Ejemplo: 'Busca archivos en Proyectos y sube uno' → Múltiple.
    - **Ambigüedad**: Si un verbo puede ser GET o POST (ej. 'Manda'), analiza el contexto:
        - Si pide información (ej. 'Manda los archivos de Proyectos'), es GET.
        - Si pide una acción (ej. 'Manda un archivo a Proyectos'), es POST.
        - Si no hay suficiente contexto, clasifica como "No Clasificable".
    - **Errores del Usuario**: Si falta información clave (ej. 'Busca archivos' sin especificar dónde), clasifica como "No Clasificable".

    3. **Detección y Generación de Consultas**:
    - Para **GET y POST simples**, genera intenciones solo para Dropbox:
        - **Dropbox**: Buscar archivos, obtener carpetas, subir archivos, crear carpetas, eliminar archivos.
    - Para **GET_CONTEXT**, genera una intención que describa qué detalle se pide del archivo (ej. "detalle del archivo doc1.txt").
    - Para **Automatizadas y Múltiples**, incluye todas las intenciones detectadas, incluso si involucran otras APIs (ej. Slack, Gmail), sin filtrarlas.
    - Si una acción no encaja con Dropbox en GET o POST simples, usa 'N/A'.

    4. **Formato de Salida**:
    - Devuelve un string con el tipo de solicitud seguido de un JSON con consultas generales bajo la clave "dropbox".
    - **GET**: `{{"dropbox": "<intención>"}}`
    - **GET_CONTEXT**: `{{"dropbox": "<intención>"}}`
    - **POST**: `{{"dropbox": "<intención>"}}`
    - **Automatizada**: `{{"dropbox": [{{"condition": "<condición>", "action": "<acción>"}}, ...]}}`
    - **Múltiple**: `{{"dropbox": ["<intención 1>", "<intención 2>", ...]}}`
    - **No Clasificable**: `{{"message": "Por favor, aclara qué quieres hacer"}}`
    - **Saludo**: `{{"dropbox": "N/A"}}`

    5. **Reglas para Consultas Generales**:
    - **GET**: Describe qué obtener en Dropbox (ej. "obtener archivos en Proyectos"). Si no aplica, clasifica como "No Clasificable".
    - **GET_CONTEXT**: Describe qué detalle se pide (ej. "detalle del archivo doc1.txt", "contenido del archivo en Proyectos"). Si no se especifica un archivo, usa "detalle del último archivo mencionado".
    - **POST**: Describe la acción en Dropbox (ej. "subir archivo doc1.txt a Proyectos"). Si no aplica, clasifica como "No Clasificable".
    - **Automatizada**: Divide en condición y acción, incluyendo otras APIs (ej. "condición: subir un archivo a Proyectos", "acción: enviar un correo").
    - **Múltiple**: Separa cada intención en una frase clara, incluyendo acciones de otras APIs (ej. "obtener archivos en Proyectos", "enviar un mensaje en Slack").
    - Incluye nombres de archivos o carpetas clave del usuario (ej. "doc1.txt", "Proyectos") si se mencionan.

    6. **Manejo de Casos Especiales**:
    - **Términos Temporales**: Si se mencionan términos como 'hoy', 'mañana', 'ayer', inclúyelos en la intención (ej. 'obtener archivos de ayer').
    - **Archivos o Carpetas Específicos**: Si se pide un archivo o carpeta específica (ej. 'el archivo doc1.txt'), inclúyelo en la intención (ej. "obtener el archivo doc1.txt").
    - **Contexto Implícito**: Si el usuario no especifica un archivo o carpeta en una solicitud GET_CONTEXT, asume que se refiere al último archivo o carpeta mencionada en el historial (ej. 'De qué trata el archivo?' → "detalle del último archivo mencionado").

    Ejemplos:
    - "Mandame los archivos en Proyectos" → "Es una solicitud GET" {{"dropbox": "obtener archivos en Proyectos"}}
    - "Dame los archivos de Juan" → "Es una solicitud GET" {{"dropbox": "obtener archivos de Juan"}}
    - "De qué trata el archivo doc1.txt?" → "Es una solicitud GET de contexto" {{"dropbox": "detalle del archivo doc1.txt"}}
    - "Qué contiene el archivo en Proyectos?" → "Es una solicitud GET de contexto" {{"dropbox": "contenido del archivo en Proyectos"}}
    - "Subir archivo doc1.txt a Proyectos" → "Es una solicitud POST" {{"dropbox": "subir archivo doc1.txt a Proyectos"}}
    - "Si subo un archivo a Proyectos, envía un correo" → "Es una solicitud automatizada" {{"dropbox": [{{"condition": "subir un archivo a Proyectos", "action": "enviar un correo"}}]}}
    - "Busca archivos en Proyectos y sube uno" → "Es una solicitud múltiple" {{"dropbox": ["obtener archivos en Proyectos", "subir un archivo"]}}
    - "Hola" → "Es un saludo" {{"dropbox": "N/A"}}
    - "Enviar mensaje a Slack" → "No puedo clasificar la solicitud, por favor aclara qué quieres hacer" {{"message": "Esto no es una acción para Dropbox, ¿qué quieres hacer con Dropbox?"}}
    """


    def generate_prompt(get_result):
        result = get_result.get("result", {})
        message = result.get("message", "No se pudo procesar la solicitud, algo salió mal.")
        data = result.get("data", None)

        if data and "archivos" in message.lower():
            file_info = "\n".join(
                f"Nombre: {item['name']} | Última modificación: {item['last_modified']}"
                for item in data
            )
            base_text = f"El usuario pidió archivos y esto encontré:\n{message}\nDetalles:\n{file_info}"
        else:
            base_text = f"El usuario pidió algo y esto obtuve:\n{message}" + (f"\nDetalles: {str(data)}" if data else "")

        prompt = f"""
        Debes responder la petición del usuario: {user_query}
        Eres un asistente de Dropbox súper amigable y útil, con un tono relajado y natural, como si charlaras con un amigo. Usa emojis sutiles para darle onda, pero sin exagerar. Basándote en esta info, arma una respuesta concisa y en párrafo que resuma los resultados de forma práctica y clara:

        {base_text}

        - Si hay resultados de archivos, haz un resumen breve y útil, mencionando cuántos archivos encontré y algo relevante (como nombres o fechas). No listes todo como tabla, solo destaca lo más importante.
        - Si no hay resultados, di algo amable y sugiere ajustar la búsqueda si hace falta.
        - Habla en primera persona y evita sonar robótico o repetir los datos crudos tal cual.
        NO INCLUYAS LINKS y responde amigable pero FORMALMENTE
        """

        try:
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Eres un asistente de Dropbox amigable."},
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
            return {"message": "¡Ey! No me dijiste qué hacer. ¿En qué te ayudo con Dropbox? 📂"}, 400

    if not email:
        return {"message": "¡Hola! Necesito tu email para empezar. ¿Me lo pasas, por favor? 😊"}, 400
    if not user_query:
        return {"message": "¡Ey! No me dijiste qué hacer. ¿En qué te ayudo con Dropbox? 📂"}, 400

    user = get_user_from_db(email, cache, mongo)
    if not user:
        return {"message": "No te encontré en el sistema. ¿Estás registrado? 😅"}, 404

    if "chats" not in user or not any(chat.get("name") == "DropboxChat" for chat in user.get("chats", [])):
        mongo.database.usuarios.update_one(
            {"correo": email},
            {"$set": {"chats": [{"name": "DropboxChat", "messages": []}]}} if "chats" not in user else {"$push": {"chats": {"name": "DropboxChat", "messages": []}}},
            upsert=True
        )
        user = get_user_from_db(email, cache, mongo)
    usuario = mongo.database.usuarios.find_one({"correo": email})
    dropbox_chat = next(
        (chat for chat in usuario.get("chats", []) if isinstance(chat, dict) and chat.get("name") == "DropboxChat"),
        None
    )

    if not dropbox_chat:
        return {"message": "¡Uy! Algo salió mal al preparar el chat, ¿intentamos otra vez?"}, 500

    timestamp = datetime.utcnow().isoformat()
    user_message = {"role": "user", "content": user_query, "timestamp": timestamp}

    try:
        prompt = f"""
            Interpreta esta query para Dropbox: "{user_query}"
            Devuelve un JSON con esta estructura:
            {{
            "peticion": "GET" | "POST" | "SALUDO" | "AUTOMATIZADA" | "MULTIPLE" | "NO_CLASIFICABLE" | "GET_CONTEXT",
            "accion": "buscar" | "subir" | "crear" | "eliminar" | "detalle_archivo" | null,
            "solicitud": "<detalles específicos>" | null | [array de acciones para MULTIPLE] | [{{"condition": "...", "action": "..."}} para AUTOMATIZADA]
            }}

            Reglas:
            1. Si es un saludo (ej. "hola"), responde un string como "SALUDO".
            2. Para GET, agrupa verbos de lectura como "dame", "mándame", "buscar", "lista" en "accion": "buscar".
            - Si la query menciona "archivo", "archivos" seguido de un término (ej. "Proyectos", "Juan"), asume que es una carpeta o nombre y usa "solicitud": "archivos en <término>".
            3. Para GET de contexto (GET_CONTEXT), detecta si el usuario pide detalles sobre un archivo específico mencionado antes (ej. "De qué trata el archivo doc1.txt?", "Qué contiene el archivo en Proyectos") usando verbos o frases como "de qué trata", "qué contiene", "detalle", "dame el contenido". Usa "peticion": "GET_CONTEXT", "accion": "detalle_archivo", "solicitud": "<término específico del archivo>", donde el término es el nombre del archivo o carpeta mencionada (ej. "doc1.txt", "Proyectos"). Si no se menciona un término claro, usa el último archivo mencionado en el historial.
            4. Para POST, agrupa verbos en estas categorías:
            - "subir": "subir", "envía", "carga"
            - "crear": "crear", "nueva carpeta"
            - "eliminar": "eliminar", "borrar", "quitar"
            5. Si es AUTOMATIZADA o MULTIPLE, usa arrays según el system prompt.
            6. Si no se entiende, usa "peticion": "NO_CLASIFICABLE", "accion": null, "solicitud": "Por favor, aclara qué quieres hacer".

            Ejemplos:
            - "Holaaaa" → {{"peticion": "SALUDO", "accion": null, "solicitud": null}}
            - "Mándame los archivos en Proyectos" → {{"peticion": "GET", "accion": "buscar", "solicitud": "archivos en Proyectos"}}
            - "De qué trata el archivo doc1.txt?" → {{"peticion": "GET_CONTEXT", "accion": "detalle_archivo", "solicitud": "doc1.txt"}}
            - "Subir archivo doc1.txt a Proyectos" → {{"peticion": "POST", "accion": "subir", "solicitud": "archivo doc1.txt a Proyectos"}}
            - "Si subo un archivo a Proyectos, envía correo" → {{"peticion": "AUTOMATIZADA", "accion": null, "solicitud": [{{"condition": "subo un archivo a Proyectos", "action": "envía correo"}}]}}
            """
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": dropbox_system_info},
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
            greeting_prompt = f"El usuario dijo '{user_query}', responde de manera cálida y amigable con emojis. Menciona que eres su asistente personalizado de Dropbox."
            greeting_response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": "Eres su asistente personal de Dropbox muy amigable."}, {"role": "user", "content": greeting_prompt}],
                max_tokens=200
            )
            result = greeting_response.choices[0].message.content.strip()
            status = 200
        elif "get_context" in peticion.lower():
            context_handler = ContextHandler(mongo.database)
            result, status = context_handler.get_chat_context(
                email=email,
                chat_name="DropboxChat",
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
            {"correo": email, "chats.name": "DropboxChat"},
            {"$push": {"chats.$.messages": {"$each": [user_message, assistant_message]}}}
        )

        return {"message": result}, status

    except Exception as e:
        return {"message": f"¡Ay, qué pena! Algo salió mal: {str(e)}. ¿Intentamos de nuevo? 🙏"}, 500

def setup_dropbox_chat(app, mongo, cache, refresh_functions):
    """Register Dropbox chat route."""
    @app.route("/api/chat/dropbox", methods=["POST"])
    def chatDropbox():
        email = request.args.get("email")
        data = request.get_json() or {}
        user_query = (
            data.get("messages", [{}])[-1].get("content")
            if data.get("messages")
            else request.args.get("query")
        )
        result, status = process_dropbox_chat(email, user_query, mongo, cache, refresh_functions)
        return jsonify(result), status

    return chatDropbox