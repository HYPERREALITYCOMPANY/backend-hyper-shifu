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

def notion_chat(app, mongo, cache, refresh_functions, query=None):
    hoy = datetime.today().strftime('%Y-%m-%d')

    notion_system_info = f"""
    Eres un intérprete de intenciones avanzado para la API de Notion. Tu tarea es analizar el mensaje del usuario, clasificarlo en una categoría general y generar consultas generales. Para GET y POST simples, enfócate solo en Notion. Para solicitudes múltiples y automatizadas, incluye todas las intenciones detectadas (incluso de otras APIs) sin filtrarlas, dejando que un intérprete multitarea las procese. Si el mensaje es ambiguo o no se puede clasificar, solicita aclaración al usuario. Sigue estos pasos:

    1. **Clasificación del Tipo de Solicitud**:
       - **Saludo**: Si el mensaje es un saludo (ej. 'hola', '¿cómo estás?', 'buenos días'), responde con: `"Es un saludo"`.
       - **Solicitud GET**: Si el usuario pide información con verbos como 'Mándame', 'Pásame', 'Envíame', 'Muéstrame', 'Busca', 'Dame', 'Dime', 'Quiero ver', 'Lista', 'Encuentra' (ej. 'Dame las páginas de mi base'), responde con: `"Es una solicitud GET"`.
       - **Solicitud POST**: Si el usuario pide una acción con verbos como 'Crear', 'Enviar', 'Eliminar', 'Actualizar', 'Agregar', 'Archivar' (ej. 'Crear página Proyecto X'), responde con: `"Es una solicitud POST"`.
       - **Solicitud Automatizada**: Si el usuario pide algo repetitivo o condicional con frases como 'Cada vez que', 'Siempre que', 'Automáticamente', 'Si pasa X haz Y' (ej. 'Si creo una página, notifica a Juan'), responde con: `"Es una solicitud automatizada"`.
       - **Solicitud Múltiple**: Si el mensaje combina varias acciones con conjunciones como 'y', 'luego', 'después', o verbos consecutivos (ej. 'Busca páginas y crea una nueva'), responde con: `"Es una solicitud múltiple"`.
       - **No Clasificable**: Si el mensaje es demasiado vago o incompleto (ej. 'Haz algo', 'Proyecto'), responde con: `"No puedo clasificar la solicitud, por favor aclara qué quieres hacer"`.

    2. **Reglas Críticas para Clasificación**:
       - **GET**: Solicitudes de lectura solo para Notion (obtener páginas, bases de datos, bloques).
       - **POST**: Acciones de escritura solo para Notion (crear páginas, actualizar contenido, eliminar páginas).
       - **Automatizadas**: Acciones con condiciones, detectando intenciones para Notion y otras APIs mencionadas por el usuario.
       - **Múltiple**: Detecta conjunciones ('y', 'luego'), verbos consecutivos, o intenciones separadas, incluyendo acciones de cualquier API mencionada.
       - **Ambigüedad**: Si un verbo podría ser GET o POST (ej. 'Manda'), usa el contexto; si no hay suficiente, clasifica como "No Clasificable".
       - **Errores del Usuario**: Si falta información clave (ej. 'Busca páginas' sin especificar cuáles), clasifica como "No Clasificable".

    3. **Detección y Generación de Consultas**:
       - Para **GET y POST simples**, genera intenciones solo para Notion:
         - **Notion**: Buscar páginas, obtener bases de datos, crear páginas, actualizar páginas, eliminar páginas, agregar bloques.
       - Para **Automatizadas y Múltiples**, incluye todas las intenciones detectadas, incluso si involucran otras APIs (ej. Gmail, Slack), sin filtrarlas.
       - Si una acción no encaja con Notion en GET o POST simples, usa 'N/A'.

    4. **Formato de Salida**:
       - Devuelve un string con el tipo de solicitud seguido de un JSON con consultas generales bajo la clave "notion".
       - **GET y POST simples**: Usa 'N/A' si no aplica a Notion.
       - **Automatizadas**: Lista condiciones y acciones, incluyendo otras APIs si se mencionan.
       - **Múltiples**: Lista todas las intenciones detectadas como un array, sin filtrar por Notion.
       - **No Clasificable**: `{{"message": "Por favor, aclara qué quieres hacer"}}`.

    5. **Estructura del JSON**:
       - **GET**: `{{"notion": "<intención>"}}`
       - **POST**: `{{"notion": "<intención>"}}`
       - **Automatizada**: `{{"notion": [{{"condition": "<condición>", "action": "<acción>"}}, ...]}}`
       - **Múltiple**: `{{"notion": ["<intención 1>", "<intención 2>", ...]}}`
       - **No Clasificable**: `{{"message": "Por favor, aclara qué quieres hacer"}}`

    6. **Reglas para Consultas Generales**:
       - **GET**: Describe qué obtener en Notion (ej. "obtener páginas de la base Proyecto X"). Si no aplica, "No Clasificable".
       - **POST**: Describe la acción en Notion (ej. "crear página Proyecto X"). Si no aplica, "No Clasificable".
       - **Automatizada**: Divide en condición y acción, incluyendo otras APIs (ej. "cuando cree una página" y "notificar a Slack").
       - **Múltiple**: Separa cada intención en una frase clara, incluyendo acciones de otras APIs (ej. "enviar correo a Juan").
       - Incluye nombres o datos clave del usuario (ej. "Proyecto X", "mañana") si se mencionan.

    Ejemplos:
    - "Dame las páginas de mi base" → "Es una solicitud GET" {{"notion": "obtener páginas de mi base"}}
    - "Crear página Proyecto X" → "Es una solicitud POST" {{"notion": "crear página Proyecto X"}}
    - "Si creo una página, notifica a Juan" → "Es una solicitud automatizada" {{"notion": [{{"condition": "crear una página", "action": "notificar a Juan"}}]}}
    - "Busca páginas y envía un correo" → "Es una solicitud múltiple" {{"notion": ["obtener páginas", "enviar un correo"]}}
    - "Hola" → "Es un saludo" {{"notion": "N/A"}}
    - "Sube un archivo a Drive" → "No puedo clasificar la solicitud, por favor aclara qué quieres hacer" {{"message": "Esto no es una acción para Notion, ¿qué quieres hacer con Notion?"}}
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
            if not refresh_tokens_dict or "notion" not in refresh_tokens_dict:
                cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
                return user

            integrations = user.get("integrations", {})
            tokens_to_refresh = {
                "notion": refresh_tokens_dict["notion"]
            } if "notion" in integrations and integrations["notion"].get("refresh_token") not in (None, "n/a") else {}

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

    def handle_get_request(intencion, email):
        user = get_user_with_refreshed_tokens(email)
        if not user:
            return {"solicitud": "GET", "result": {"error": "¡Órale! No te encontré, compa 😕"}}, 404

        notion_token = user.get('integrations', {}).get('notion', {}).get('token')
        if not notion_token:
            return {"solicitud": "GET", "result": {"error": "¡Ey! No tengo tu token de Notion, ¿me das permisos? 🔑"}}, 400

        headers = {'Authorization': f"Bearer {notion_token}", 'Notion-Version': '2022-06-28', 'Content-Type': 'application/json'}
        url = "https://api.notion.com/v1/search"

        query = intencion["notion"]
        if not query or query == "N/A":
            return {"solicitud": "GET", "result": {"error": "¡Falta algo, papu! ¿Qué quieres buscar en Notion? 🤔"}}, 400

        try:
            if "obtener páginas" in query.lower():
                search_term = query.split("de")[-1].strip() if "de" in query else ""
                payload = {"query": search_term} if search_term else {}
                response = requests.post(url, headers=headers, json=payload)
                response.raise_for_status()
                results = response.json().get('results', [])
                pages = [
                    {"page_name": page["properties"]["title"]["title"][0]["plain_text"], "url": page["url"]}
                    for page in results if page["object"] == "page" and page["properties"].get("title")
                ]
                if not pages:
                    return {"solicitud": "GET", "result": {"message": "📭 No encontré páginas con eso, ¿probamos otra cosa?"}}, 200
                return {"solicitud": "GET", "result": {"message": f"¡Órale! Encontré {len(pages)} páginas 📄", "data": pages}}, 200
            else:
                return {"solicitud": "GET", "result": {"error": "¡Uy! Solo puedo buscar páginas por ahora, ¿qué tal eso? 😅"}}, 400
        except requests.RequestException as e:
            return {"solicitud": "GET", "result": {"error": f"¡Ay, qué mala onda! Error con Notion: {str(e)}"}}, 500

    def handle_post_request(intencion, email):
        user = get_user_with_refreshed_tokens(email)
        if not user:
            return {"solicitud": "POST", "result": {"error": "¡Órale! No te encontré, compa 😕"}}, 404

        notion_token = user.get('integrations', {}).get('notion', {}).get('token')
        if not notion_token:
            return {"solicitud": "POST", "result": {"error": "¡Ey! No tengo tu token de Notion, ¿me das permisos? 🔑"}}, 400

        headers = {'Authorization': f"Bearer {notion_token}", 'Notion-Version': '2022-06-28', 'Content-Type': 'application/json'}

        query = intencion["notion"]
        if isinstance(query, list) and all(isinstance(item, str) for item in query):  # Solicitud múltiple
            return {"solicitud": "POST", "result": {"message": "Solicitud múltiple detectada, pasando al intérprete multitarea", "actions": query}}, 200
        if isinstance(query, list) and all(isinstance(item, dict) and "condition" in item for item in query):  # Automatización
            return {"solicitud": "POST", "result": {"message": "Solicitud automatizada detectada, pasando al intérprete multitarea", "actions": query}}, 200

        try:
            # Crear página
            if "crear página" in query.lower():
                match = re.search(r'crear\s*página\s*(.+)', query, re.IGNORECASE)
                if not match:
                    return {"solicitud": "POST", "result": {"error": "¡Ey! ¿Cómo se llama la página que quieres crear? 📝"}}, 400
                page_name = match.group(1).strip()
                url = "https://api.notion.com/v1/pages"
                payload = {
                    "parent": {"database_id": "some_default_database_id"},  # Esto debería venir de config o contexto
                    "properties": {"title": {"title": [{"text": {"content": page_name}}]}}
                }
                response = requests.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return {"solicitud": "POST", "result": {"message": f"📄 Página '{page_name}' creada con éxito 🚀"}}, 200

            # Actualizar página
            elif "actualizar página" in query.lower():
                match = re.search(r'actualizar\s*página\s*"(.+?)"\s*con\s*(.+)', query, re.IGNORECASE)
                if not match:
                    return {"solicitud": "POST", "result": {"error": "¡Ey! ¿Qué página y qué cambio quieres hacer? 🤔"}}, 400
                page_name = match.group(1).strip()
                update_content = match.group(2).strip()
                # Simulación: buscar página primero
                search_url = "https://api.notion.com/v1/search"
                response = requests.post(search_url, headers=headers, json={"query": page_name})
                response.raise_for_status()
                pages = response.json().get('results', [])
                page_id = next((p["id"] for p in pages if p["properties"]["title"]["title"][0]["plain_text"].lower() == page_name.lower()), None)
                if not page_id:
                    return {"solicitud": "POST", "result": {"message": f"📭 No encontré la página '{page_name}'"}}, 200
                url = f"https://api.notion.com/v1/pages/{page_id}"
                payload = {"properties": {"title": {"title": [{"text": {"content": f"{page_name} - {update_content}"}}]}}}
                response = requests.patch(url, headers=headers, json=payload)
                response.raise_for_status()
                return {"solicitud": "POST", "result": {"message": f"✨ Página '{page_name}' actualizada con '{update_content}'"}}, 200

            # Eliminar página
            elif "eliminar página" in query.lower():
                match = re.search(r'eliminar\s*página\s*"(.+?)"', query, re.IGNORECASE)
                if not match:
                    return {"solicitud": "POST", "result": {"error": "¡Ey! ¿Qué página quieres eliminar? 🗑️"}}, 400
                page_name = match.group(1).strip()
                search_url = "https://api.notion.com/v1/search"
                response = requests.post(search_url, headers=headers, json={"query": page_name})
                response.raise_for_status()
                pages = response.json().get('results', [])
                page_id = next((p["id"] for p in pages if p["properties"]["title"]["title"][0]["plain_text"].lower() == page_name.lower()), None)
                if not page_id:
                    return {"solicitud": "POST", "result": {"message": f"📭 No encontré la página '{page_name}'"}}, 200
                url = f"https://api.notion.com/v1/pages/{page_id}"
                payload = {"archived": True}  # En Notion, "eliminar" es archivar
                response = requests.patch(url, headers=headers, json=payload)
                response.raise_for_status()
                return {"solicitud": "POST", "result": {"message": f"🗑️ Página '{page_name}' eliminada con éxito"}}, 200

            return {"solicitud": "POST", "result": {"error": "¡Uy! Acción no soportada en Notion, ¿qué tal crear o actualizar una página? 😅"}}, 400

        except requests.RequestException as e:
            return {"solicitud": "POST", "result": {"error": f"¡Ay, qué mala onda! Error con Notion: {str(e)}"}}, 500
        except Exception as e:
            return {"solicitud": "POST", "result": {"error": f"¡Se puso feo! Error inesperado: {str(e)}"}}, 500

    @app.route("/api/chat/notion", methods=["POST"])
    def chatNotion():
        email = request.args.get("email")
        data = request.get_json()
        user_query = data.get("messages", [{}])[-1].get("content") if data.get("messages") else None
        if not email:
            return jsonify({"error": "¡Órale! Necesito tu email, compa 😅"}), 400
        if not user_query:
            return jsonify({"error": "¡Ey! Dame algo pa’ trabajar, ¿qué quieres hacer con Notion? 🤔"}), 400

        user = get_user_with_refreshed_tokens(email)
        if not user:
            return jsonify({"error": "¡Uy! No te encontré en el sistema, ¿seguro que estás registrado? 😕"}), 404

        if "chats" not in user or not any(chat["name"] == "NotionChat" for chat in user.get("chats", [])):
            mongo.database.usuarios.update_one(
                {"correo": email},
                {"$set": {"chats": [{"name": "NotionChat", "messages": []}]}} if "chats" not in user else {"$push": {"chats": {"name": "NotionChat", "messages": []}}},
                upsert=True
            )
            user = get_user_with_refreshed_tokens(email)

        notion_chat = next((chat for chat in user["chats"] if chat["name"] == "NotionChat"), None)
        if not notion_chat:
            return jsonify({"error": "¡Qué mala onda! Error al inicializar el chat 😓"}), 500

        timestamp = datetime.utcnow().isoformat()
        user_message = {"role": "user", "content": user_query, "timestamp": timestamp}

        try:
            prompt = f"""
            Interpreta esta query para Notion: "{user_query}"
            Si es un saludo (como "hola", "holaaaa"), responde: "Es un saludo" {{"notion": "N/A"}}
            Si es otra cosa, clasifica como GET, POST, etc., según las reglas del system prompt anterior.
            Devuelve el resultado en formato: "TIPO" {{"clave": "valor"}}
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

            request_type_match = re.match(r'^"([^"]+)"\s*(\{.*\})', ia_response, re.DOTALL)
            if not request_type_match:
                result = {"message": "¡Uy! Algo salió mal, ¿puedes intentarlo otra vez? 😅"}
            else:
                request_type = request_type_match.group(1)
                json_str = request_type_match.group(2)
                parsed_response = json.loads(json_str)

                if request_type == "Es un saludo":
                    greeting_prompt = f"El usuario dijo {user_query}. Responde de manera cálida y amigable con emojis a un saludo simple. Menciona que eres su asistente personalizado de Notion."
                    greeting_response = openai.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "system", "content": "Eres su asistente personal de Notion muy amigable."}, {"role": "user", "content": greeting_prompt}],
                        max_tokens=200
                    )
                    result = {"message": greeting_response.choices[0].message.content.strip()}
                elif request_type == "Es una solicitud GET":
                    result = handle_get_request(parsed_response, email)
                elif request_type in ["Es una solicitud POST", "Es una solicitud automatizada", "Es una solicitud múltiple"]:
                    result = handle_post_request(parsed_response, email)
                else:
                    result = {"solicitud": "ERROR", "result": {"error": parsed_response.get("message", "¡No entendí qué quieres hacer con Notion! 😕")}}

            assistant_message = {"role": "assistant", "content": json.dumps(result), "timestamp": datetime.utcnow().isoformat()}
            mongo.database.usuarios.update_one(
                {"correo": email, "chats.name": "NotionChat"},
                {"$push": {"chats.$.messages": {"$each": [user_message, assistant_message]}}}
            )

            return jsonify(result)

        except Exception as e:
            return jsonify({"solicitud": "ERROR", "result": {"error": f"¡Se puso feo! Error inesperado: {str(e)} 😓"}}), 500

    return chatNotion