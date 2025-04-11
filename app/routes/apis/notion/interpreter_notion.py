from datetime import datetime
from flask import request, jsonify
from config import Config
import json
import re
import openai
openai.api_key = Config.CHAT_API_KEY
from app.utils.utils import get_user_from_db
from flask_caching import Cache
from .getFunctionNotion import handle_get_request
from .postFunctionNotion import handle_post_request
from app.routes.core.context.ContextHandler import ContextHandler

def process_notion_chat(email, user_query=None, mongo=None, cache=None, refresh_functions=None):
    """Core logic for processing Notion chat requests."""
    notion_system_info = f"""
    Eres un intérprete de intenciones avanzado para la API de Notion. Tu tarea es analizar el mensaje del usuario, clasificarlo y generar consultas generales. Si el mensaje es ambiguo, pide aclaración. Sigue estos pasos:

    1. **Clasificación del Tipo de Solicitud**:
       - **Saludo**: Si es un saludo (ej. 'hola', '¿qué tal?'), responde con: `"Es un saludo"`.
       - **Solicitud GET**: Si pide información con verbos como 'Mándame', 'Busca', 'Dame', 'Dime', 'Quiero ver', 'Lista' (ej. 'Dame las páginas de mi base de datos Proyectos'), responde con: `"Es una solicitud GET"`.
       - **Solicitud GET de Contexto (GET_CONTEXT)**: Si pide detalles sobre una página o base de datos específica mencionada previamente (ej. '¿Qué dice la página de Reunión?', 'Dame el contenido de la página Proyectos'), usando frases como 'qué dice', 'dame el contenido', 'qué contiene', 'detalle', 'muéstrame el contenido', responde con: `"Es una solicitud GET de contexto"`.
       - **Solicitud POST**: Si pide una acción con verbos como 'Crear', 'Añadir', 'Agregar', 'Escribe' (ej. 'Crear página en Proyectos'), responde con: `"Es una solicitud POST"`.
       - **Solicitud Automatizada**: Si es repetitiva o condicional (ej. 'Si creo una página, avísame'), responde con: `"Es una solicitud automatizada"`.
       - **Solicitud Múltiple**: Si combina acciones (ej. 'Busca páginas de Proyectos y crea una nueva'), responde con: `"Es una solicitud múltiple"`.
       - **No Clasificable**: Si es vago (ej. 'Haz algo'), responde con: `"No puedo clasificar la solicitud, por favor aclara qué quieres hacer"`.

    2. **Aclaraciones**:
       - Si falta información clave (ej. base de datos en 'Crear página'), clasifica como "ACLARACION" y sugiere qué falta.

    3. **Contexto**:
       - Usa mensajes previos para completar datos faltantes (ej. base de datos o página mencionada antes).
       - Para GET_CONTEXT, si no se especifica una página o base de datos, asume que se refiere a la última mencionada en el historial.

    4. **Formato de Salida**:
       - **GET**: `{{"notion": "<intención>"}}`
       - **GET_CONTEXT**: `{{"notion": "<intención>"}}`
       - **POST**: `{{"notion": "<intención>"}}`
       - **Automatizada**: `{{"notion": [{{"condition": "<condición>", "action": "<acción>"}}, ...]}}`
       - **Múltiple**: `{{"notion": ["<intención 1>", "<intención 2>", ...]}}`
       - **Aclaración**: `{{"message": "Por favor, dime <qué falta>"}}`
       - **No Clasificable**: `{{"message": "Por favor, aclara qué quieres hacer"}}`

    Ejemplos:
    - "Dame las páginas de Proyectos" → "Es una solicitud GET" {{"notion": "Obtener páginas de la base de datos Proyectos"}}
    - "Qué dice la página de Reunión?" → "Es una solicitud GET de contexto" {{"notion": "contenido de la página Reunión"}}
    - "Crear página en Tareas" → "Es una solicitud POST" {{"notion": "Crear página en la base de datos Tareas"}}
    - "Crear página" → "ACLARACION" {{"message": "Por favor, dime en qué base de datos crear la página"}}
    - "Busca páginas y crea una nueva" → "Es una solicitud múltiple" {{"notion": ["Obtener páginas", "Crear página"]}}
    """

    def generate_prompt(get_result):
        result = get_result.get("result", {})
        message = result.get("message", "No se pudo procesar la solicitud, algo salió mal.")
        data = result.get("data", None)

        if data and "páginas" in message.lower():
            page_info = "\n".join(
                f"Título: {item['title']} | ID: {item['id']}"
                for item in data
            )
            base_text = f"El usuario pidió páginas y esto encontré:\n{message}\nDetalles:\n{page_info}"
        elif data and "bases de datos" in message.lower():
            db_info = "\n".join(
                f"Título: {item['title']} | ID: {item['id']}"
                for item in data
            )
            base_text = f"El usuario pidió bases de datos y esto encontré:\n{message}\nDetalles:\n{db_info}"
        else:
            base_text = f"El usuario pidió algo y esto obtuve:\n{message}" + (f"\nDetalles: {str(data)}" if data else "")

        prompt = f"""
        Debes responder la petición del usuario: {user_query}
        Eres un asistente de Notion súper amigable y útil, con un tono relajado y natural, como si charlaras con un amigo. Usa emojis sutiles para darle onda, pero sin exagerar. Basándote en esta info, arma una respuesta concisa y en párrafo que resuma los resultados de forma práctica y clara:

        {base_text}

        - Si hay resultados de páginas, haz un resumen breve y útil, mencionando cuántas páginas encontré y algo relevante (como el título o un detalle interesante). No listes todo como tabla, solo destaca lo más importante.
        - Si hay resultados de bases de datos, menciona cuántas encontré y algo relevante (como el nombre).
        - Si no hay resultados, di algo amable y sugiere ajustar la búsqueda si hace falta.
        - Habla en primera persona y evita sonar robótico o repetir los datos crudos tal cual.
        NO INCLUYAS LINKS y responde amigable pero FORMALMENTE
        """

        try:
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Eres un asistente de Notion amigable."},
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
            return {"message": {"error": "No me indicaste qué hacer, ¿en qué puedo ayudarte con Notion?"}}, 400

    if not email:
        return {"message": {"error": "Necesito el email del usuario para continuar, ¿me lo puedes proporcionar?"}}, 400
    if not user_query:
        return {"message": {"error": "No me indicaste qué hacer, ¿en qué puedo ayudarte con Notion?"}}, 400

    user = get_user_from_db(email, cache, mongo)
    if not user:
        return {"message": {"error": "No encontré a este usuario, ¿estás seguro de que está registrado?"}}, 404

    if "chats" not in user or not any(chat.get("name") == "NotionChat" for chat in user.get("chats", [])):
        mongo.database.usuarios.update_one(
            {"correo": email},
            {"$set": {"chats": [{"name": "NotionChat", "messages": []}]}} if "chats" not in user else {"$push": {"chats": {"name": "NotionChat", "messages": []}}},
            upsert=True
        )
        user = get_user_from_db(email, cache, mongo)
    usuario = mongo.database.usuarios.find_one({"correo": email})
    notion_chat = next(
        (chat for chat in usuario.get("chats", []) if isinstance(chat, dict) and chat.get("name") == "NotionChat"),
        None
    )

    if not notion_chat:
        return {"message": {"error": "¡Uy! Algo salió mal al preparar el chat, ¿intentamos otra vez?"}}, 500

    timestamp = datetime.utcnow().isoformat()
    user_message = {"role": "user", "content": user_query, "timestamp": timestamp}

    try:
        prompt = f"""
            Interpreta esta query para Notion: "{user_query}"
            Devuelve un JSON con esta estructura:
            {{
            "peticion": "GET" | "POST" | "SALUDO" | "AUTOMATIZADA" | "MULTIPLE" | "ACLARACION" | "NO_CLASIFICABLE" | "GET_CONTEXT",
            "accion": "buscar" | "crear" | "detalle_pagina" | null,
            "solicitud": "<detalles>" | null | [array para MULTIPLE] | "mensaje de aclaración" | "<título o referencia de página>"
            }}
            Reglas:
            1. Si es un saludo (ej. "hola"), usa "peticion": "SALUDO".
            2. Para GET, agrupa verbos como "dame", "mándame", "busca", "dime", "quiero ver", "lista" en "accion": "buscar".
               - Si menciona "páginas" o "bases de datos" seguido de un término (ej. "Proyectos"), usa "solicitud": "páginas de <término>" o "bases de datos".
            3. Para GET_CONTEXT, detecta si pide detalles de una página o base de datos con frases como "qué dice", "dame el contenido", "qué contiene", "detalle", "muéstrame el contenido".
               - Usa "peticion": "GET_CONTEXT", "accion": "detalle_pagina", "solicitud": "<título o referencia de página>".
               - Si no se especifica, usa "última página mencionada".
            4. Para POST, agrupa verbos como "crear", "añadir", "agregar", "escribe" en "accion": "crear".
            5. Si es AUTOMATIZADA o MULTIPLE, usa arrays según el system prompt.
            6. Si falta info clave (ej. base de datos en "crear página"), usa "peticion": "ACLARACION".
            7. Si no se entiende, usa "peticion": "NO_CLASIFICABLE".

            Ejemplos:
            - "Dame las páginas de Proyectos" → {{"peticion": "GET", "accion": "buscar", "solicitud": "páginas de Proyectos"}}
            - "Qué dice la página de Reunión?" → {{"peticion": "GET_CONTEXT", "accion": "detalle_pagina", "solicitud": "Reunión"}}
            - "Crear página en Tareas" → {{"peticion": "POST", "accion": "crear", "solicitud": "página en Tareas"}}
            - "Crear página" → {{"peticion": "ACLARACION", "accion": null, "solicitud": "Por favor, dime en qué base de datos crear la página"}}
            """
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": notion_system_info},
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
            greeting_prompt = f"El usuario dijo '{user_query}', responde de manera cálida y amigable con emojis. Menciona que eres su asistente personalizado de Notion."
            greeting_response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": "Eres su asistente personal de Notion muy amigable."}, {"role": "user", "content": greeting_prompt}],
                max_tokens=200
            )
            result = greeting_response.choices[0].message.content.strip()
            status = 200
        elif "get_context" in peticion.lower():
            context_handler = ContextHandler(mongo.database)
            result, status = context_handler.get_chat_context(
                email=email,
                chat_name="NotionChat",
                query=user_query,
                solicitud=solicitud
            )
        elif "get" in peticion.lower():
            result, status = handle_get_request(accion, solicitud, email, user)
            result, prompt = generate_prompt(result)
        elif "post" in peticion.lower():
            result, status = handle_post_request(accion, solicitud, email, user)
            result = result.get("result", {}).get("message", "No se encontró mensaje")
        elif "aclaracion" in peticion.lower():
            result = solicitud
            status = 200
        else:
            result = {"error": solicitud}
            status = 400

        assistant_message = {"role": "assistant", "content": result if isinstance(result, str) else json.dumps(result), "timestamp": datetime.utcnow().isoformat()}
        mongo.database.usuarios.update_one(
            {"correo": email, "chats.name": "NotionChat"},
            {"$push": {"chats.$.messages": {"$each": [user_message, assistant_message]}}}
        )

        return {"message": result}

    except Exception as e:
        return {"message": {"error": f"Lo siento, algo salió mal: {str(e)}"}}, 500

def setup_notion_chat(app, mongo, cache, refresh_functions):
    """Register Notion chat route."""
    @app.route("/api/chat/notion", methods=["POST"])
    def chatNotion():
        email = request.args.get("email")
        data = request.get_json() or {}
        user_query = (
            data.get("messages", [{}])[-1].get("content")
            if data.get("messages")
            else request.args.get("query")
        )
        result = process_notion_chat(email, user_query, mongo, cache, refresh_functions)
        return jsonify(result)

    return chatNotion