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

def hubspot_chat(app, mongo, cache, refresh_functions, query=None):
    hoy = datetime.today().strftime('%Y-%m-%d')

    hubspot_system_info = f"""
    Eres un intérprete de intenciones avanzado para la API de HubSpot. Tu tarea es analizar el mensaje del usuario, clasificarlo en una categoría general y generar consultas generales. Para GET y POST simples, enfócate solo en HubSpot. Para solicitudes múltiples y automatizadas, incluye todas las intenciones detectadas (incluso de otras APIs) sin filtrarlas, dejando que un intérprete multitarea las procese. Si el mensaje es ambiguo o no se puede clasificar, solicita aclaración al usuario. Sigue estos pasos:

    1. **Clasificación del Tipo de Solicitud**:
       - **Saludo**: Si el mensaje es un saludo (ej. 'hola', '¿cómo estás?', 'buenos días'), responde con: `"Es un saludo"`.
       - **Solicitud GET**: Si el usuario pide información con verbos como 'Mándame', 'Pásame', 'Envíame', 'Muéstrame', 'Busca', 'Dame', 'Dime', 'Quiero ver', 'Lista', 'Encuentra' (ej. 'Dame los contactos de mi lista'), responde con: `"Es una solicitud GET"`.
       - **Solicitud POST**: Si el usuario pide una acción con verbos como 'Crear', 'Enviar', 'Eliminar', 'Actualizar', 'Agregar' (ej. 'Crear contacto Juan'), responde con: `"Es una solicitud POST"`.
       - **Solicitud Automatizada**: Si el usuario pide algo repetitivo o condicional con frases como 'Cada vez que', 'Siempre que', 'Automáticamente', 'Si pasa X haz Y' (ej. 'Si creo un contacto, envía un correo'), responde con: `"Es una solicitud automatizada"`.
       - **Solicitud Múltiple**: Si el mensaje combina varias acciones con conjunciones como 'y', 'luego', 'después', o verbos consecutivos (ej. 'Busca contactos y crea uno nuevo'), responde con: `"Es una solicitud múltiple"`.
       - **No Clasificable**: Si el mensaje es demasiado vago o incompleto (ej. 'Haz algo', 'Contacto'), responde con: `"No puedo clasificar la solicitud, por favor aclara qué quieres hacer"`.

    2. **Reglas Críticas para Clasificación**:
       - **GET**: Solicitudes de lectura solo para HubSpot (obtener contactos, deals, compañías).
       - **POST**: Acciones de escritura solo para HubSpot (crear contactos, actualizar contactos, eliminar contactos).
       - **Automatizadas**: Acciones con condiciones, detectando intenciones para HubSpot y otras APIs mencionadas por el usuario.
       - **Múltiple**: Detecta conjunciones ('y', 'luego'), verbos consecutivos, o intenciones separadas, incluyendo acciones de cualquier API mencionada.
       - **Ambigüedad**: Si un verbo podría ser GET o POST (ej. 'Manda'), usa el contexto; si no hay suficiente, clasifica como "No Clasificable".
       - **Errores del Usuario**: Si falta información clave (ej. 'Busca contactos' sin especificar cuáles), clasifica como "No Clasificable".

    3. **Detección y Generación de Consultas**:
       - Para **GET y POST simples**, genera intenciones solo para HubSpot:
         - **HubSpot**: Buscar contactos, obtener deals, crear contactos, actualizar contactos, eliminar contactos.
       - Para **Automatizadas y Múltiples**, incluye todas las intenciones detectadas, incluso si involucran otras APIs (ej. Gmail, Slack), sin filtrarlas.
       - Si una acción no encaja con HubSpot en GET o POST simples, usa 'N/A'.

    4. **Formato de Salida**:
       - Devuelve un string con el tipo de solicitud seguido de un JSON con consultas generales bajo la clave "hubspot".
       - **GET y POST simples**: Usa 'N/A' si no aplica a HubSpot.
       - **Automatizadas**: Lista condiciones y acciones, incluyendo otras APIs si se mencionan.
       - **Múltiples**: Lista todas las intenciones detectadas como un array, sin filtrar por HubSpot.
       - **No Clasificable**: `{{"message": "Por favor, aclara qué quieres hacer"}}`.

    5. **Estructura del JSON**:
       - **GET**: `{{"hubspot": "<intención>"}}`
       - **POST**: `{{"hubspot": "<intención>"}}`
       - **Automatizada**: `{{"hubspot": [{{"condition": "<condición>", "action": "<acción>"}}, ...]}}`
       - **Múltiple**: `{{"hubspot": ["<intención 1>", "<intención 2>", ...]}}`
       - **No Clasificable**: `{{"message": "Por favor, aclara qué quieres hacer"}}`

    6. **Reglas para Consultas Generales**:
       - **GET**: Describe qué obtener en HubSpot (ej. "obtener contactos de mi lista"). Si no aplica, "No Clasificable".
       - **POST**: Describe la acción en HubSpot (ej. "crear contacto Juan"). Si no aplica, "No Clasificable".
       - **Automatizada**: Divide en condición y acción, incluyendo otras APIs (ej. "cuando cree un contacto" y "enviar correo").
       - **Múltiple**: Separa cada intención en una frase clara, incluyendo acciones de otras APIs (ej. "subir archivo a Drive").
       - Incluye nombres o datos clave del usuario (ej. "Juan", "mañana") si se mencionan.

    Ejemplos:
    - "Dame los contactos de mi lista" → "Es una solicitud GET" {{"hubspot": "obtener contactos de mi lista"}}
    - "Crear contacto Juan" → "Es una solicitud POST" {{"hubspot": "crear contacto Juan"}}
    - "Si creo un contacto, envía un correo" → "Es una solicitud automatizada" {{"hubspot": [{{"condition": "crear un contacto", "action": "enviar un correo"}}]}}
    - "Busca contactos y crea uno nuevo" → "Es una solicitud múltiple" {{"hubspot": ["obtener contactos", "crear un contacto nuevo"]}}
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

    def handle_get_request(intencion, email):
        user = get_user_with_refreshed_tokens(email)
        if not user:
            return {"solicitud": "GET", "result": {"error": "¡Órale! No te encontré, compa 😕"}}, 404

        hubspot_token = user.get('integrations', {}).get('hubspot', {}).get('token')
        if not hubspot_token:
            return {"solicitud": "GET", "result": {"error": "¡Ey! No tengo tu token de HubSpot, ¿me das permisos? 🔑"}}, 400

        headers = {'Authorization': f"Bearer {hubspot_token}", 'Content-Type': 'application/json'}
        url = "https://api.hubapi.com/crm/v3/objects/contacts"

        query = intencion["hubspot"]
        if not query or query == "N/A":
            return {"solicitud": "GET", "result": {"error": "¡Falta algo, papu! ¿Qué quieres buscar en HubSpot? 🤔"}}, 400

        try:
            if "obtener contactos" in query.lower():
                list_name = query.split("de")[-1].strip() if "de" in query else ""
                params = {"filter": {"propertyName": "email", "operator": "CONTAINS", "value": list_name}} if list_name else {}
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()
                contacts = response.json().get('results', [])
                results = [{"contact_name": f"{c['properties'].get('firstname', '')} {c['properties'].get('lastname', '')}".strip(), "id": c["id"]} for c in contacts]
                if not results:
                    return {"solicitud": "GET", "result": {"message": "📭 No encontré contactos con eso, ¿probamos otra cosa?"}}, 200
                return {"solicitud": "GET", "result": {"message": f"¡Órale! Encontré {len(results)} contactos 📇", "data": results}}, 200
            else:
                return {"solicitud": "GET", "result": {"error": "¡Uy! Solo puedo buscar contactos por ahora, ¿qué tal eso? 😅"}}, 400
        except requests.RequestException as e:
            return {"solicitud": "GET", "result": {"error": f"¡Ay, qué mala onda! Error con HubSpot: {str(e)}"}}, 500

    def handle_post_request(intencion, email):
        user = get_user_with_refreshed_tokens(email)
        if not user:
            return {"solicitud": "POST", "result": {"error": "¡Órale! No te encontré, compa 😕"}}, 404

        hubspot_token = user.get('integrations', {}).get('hubspot', {}).get('token')
        if not hubspot_token:
            return {"solicitud": "POST", "result": {"error": "¡Ey! No tengo tu token de HubSpot, ¿me das permisos? 🔑"}}, 400

        headers = {'Authorization': f"Bearer {hubspot_token}", 'Content-Type': 'application/json'}

        query = intencion["hubspot"]
        if isinstance(query, list) and all(isinstance(item, str) for item in query):
            return {"solicitud": "POST", "result": {"message": "Solicitud múltiple detectada, pasando al intérprete multitarea", "actions": query}}, 200
        if isinstance(query, list) and all(isinstance(item, dict) and "condition" in item for item in query):
            return {"solicitud": "POST", "result": {"message": "Solicitud automatizada detectada, pasando al intérprete multitarea", "actions": query}}, 200

        try:
            # Crear contacto
            if "crear contacto" in query.lower():
                match = re.search(r'crear\s*contacto\s*(.+)', query, re.IGNORECASE)
                if not match:
                    return {"solicitud": "POST", "result": {"error": "¡Ey! ¿Cómo se llama el contacto que quieres crear? 📇"}}, 400
                contact_name = match.group(1).strip()
                url = "https://api.hubapi.com/crm/v3/objects/contacts"
                name_parts = contact_name.split(" ", 1)
                payload = {
                    "properties": {
                        "firstname": name_parts[0],
                        "lastname": name_parts[1] if len(name_parts) > 1 else ""
                    }
                }
                response = requests.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return {"solicitud": "POST", "result": {"message": f"📇 Contacto '{contact_name}' creado con éxito 🚀"}}, 200

            # Actualizar contacto
            elif "actualizar contacto" in query.lower():
                match = re.search(r'actualizar\s*contacto\s*"(.+?)"\s*con\s*(.+)', query, re.IGNORECASE)
                if not match:
                    return {"solicitud": "POST", "result": {"error": "¡Ey! ¿Qué contacto y qué cambio quieres hacer? 🤔"}}, 400
                contact_name = match.group(1).strip()
                update_content = match.group(2).strip()
                search_url = "https://api.hubapi.com/crm/v3/objects/contacts"
                response = requests.get(search_url, headers=headers)
                response.raise_for_status()
                contacts = response.json().get('results', [])
                contact_id = next((c["id"] for c in contacts if f"{c['properties'].get('firstname', '')} {c['properties'].get('lastname', '')}".strip().lower() == contact_name.lower()), None)
                if not contact_id:
                    return {"solicitud": "POST", "result": {"message": f"📭 No encontré el contacto '{contact_name}'"}}, 200
                url = f"https://api.hubapi.com/crm/v3/objects/contacts/{contact_id}"
                payload = {"properties": {"company": update_content}}  # Ejemplo: actualiza el campo "company"
                response = requests.patch(url, headers=headers, json=payload)
                response.raise_for_status()
                return {"solicitud": "POST", "result": {"message": f"✨ Contacto '{contact_name}' actualizado con '{update_content}'"}}, 200

            # Eliminar contacto
            elif "eliminar contacto" in query.lower():
                match = re.search(r'eliminar\s*contacto\s*"(.+?)"', query, re.IGNORECASE)
                if not match:
                    return {"solicitud": "POST", "result": {"error": "¡Ey! ¿Qué contacto quieres eliminar? 🗑️"}}, 400
                contact_name = match.group(1).strip()
                search_url = "https://api.hubapi.com/crm/v3/objects/contacts"
                response = requests.get(search_url, headers=headers)
                response.raise_for_status()
                contacts = response.json().get('results', [])
                contact_id = next((c["id"] for c in contacts if f"{c['properties'].get('firstname', '')} {c['properties'].get('lastname', '')}".strip().lower() == contact_name.lower()), None)
                if not contact_id:
                    return {"solicitud": "POST", "result": {"message": f"📭 No encontré el contacto '{contact_name}'"}}, 200
                url = f"https://api.hubapi.com/crm/v3/objects/contacts/{contact_id}"
                response = requests.delete(url, headers=headers)
                response.raise_for_status()
                return {"solicitud": "POST", "result": {"message": f"🗑️ Contacto '{contact_name}' eliminado con éxito"}}, 200

            return {"solicitud": "POST", "result": {"error": "¡Uy! Acción no soportada en HubSpot, ¿qué tal crear o actualizar un contacto? 😅"}}, 400

        except requests.RequestException as e:
            return {"solicitud": "POST", "result": {"error": f"¡Ay, qué mala onda! Error con HubSpot: {str(e)}"}}, 500
        except Exception as e:
            return {"solicitud": "POST", "result": {"error": f"¡Se puso feo! Error inesperado: {str(e)}"}}, 500

    @app.route("/api/chat/hubspot", methods=["POST"])
    def chatHubSpot():
        email = request.args.get("email")
        data = request.get_json()
        user_query = data.get("messages", [{}])[-1].get("content") if data.get("messages") else None
        if not email:
            return jsonify({"error": "¡Órale! Necesito tu email, compa 😅"}), 400
        if not user_query:
            return jsonify({"error": "¡Ey! Dame algo pa’ trabajar, ¿qué quieres hacer con HubSpot? 🤔"}), 400

        user = get_user_with_refreshed_tokens(email)
        if not user:
            return jsonify({"error": "¡Uy! No te encontré en el sistema, ¿seguro que estás registrado? 😕"}), 404

        if "chats" not in user or not any(chat["name"] == "HubSpotChat" for chat in user.get("chats", [])):
            mongo.database.usuarios.update_one(
                {"correo": email},
                {"$set": {"chats": [{"name": "HubSpotChat", "messages": []}]}} if "chats" not in user else {"$push": {"chats": {"name": "HubSpotChat", "messages": []}}},
                upsert=True
            )
            user = get_user_with_refreshed_tokens(email)

        hubspot_chat = next((chat for chat in user["chats"] if chat["name"] == "HubSpotChat"), None)
        if not hubspot_chat:
            return jsonify({"error": "¡Qué mala onda! Error al inicializar el chat 😓"}), 500

        timestamp = datetime.utcnow().isoformat()
        user_message = {"role": "user", "content": user_query, "timestamp": timestamp}

        try:
            prompt = f"""
            Interpreta esta query para HubSpot: "{user_query}"
            Si es un saludo (como "hola", "holaaaa"), responde: "Es un saludo" {{"hubspot": "N/A"}}
            Si es otra cosa, clasifica como GET, POST, etc., según las reglas del system prompt anterior.
            Devuelve el resultado en formato: "TIPO" {{"clave": "valor"}}
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

            request_type_match = re.match(r'^"([^"]+)"\s*(\{.*\})', ia_response, re.DOTALL)
            if not request_type_match:
                result = {"message": "¡Uy! Algo salió mal, ¿puedes intentarlo otra vez? 😅"}
            else:
                request_type = request_type_match.group(1)
                json_str = request_type_match.group(2)
                parsed_response = json.loads(json_str)

                if request_type == "Es un saludo":
                    greeting_prompt = f"El usuario dijo {user_query}. Responde de manera cálida y amigable con emojis a un saludo simple. Menciona que eres su asistente personalizado de HubSpot."
                    greeting_response = openai.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "system", "content": "Eres su asistente personal de HubSpot muy amigable."}, {"role": "user", "content": greeting_prompt}],
                        max_tokens=200
                    )
                    result = {"message": greeting_response.choices[0].message.content.strip()}
                elif request_type == "Es una solicitud GET":
                    result = handle_get_request(parsed_response, email)
                elif request_type in ["Es una solicitud POST", "Es una solicitud automatizada", "Es una solicitud múltiple"]:
                    result = handle_post_request(parsed_response, email)
                else:
                    result = {"solicitud": "ERROR", "result": {"error": parsed_response.get("message", "¡No entendí qué quieres hacer con HubSpot! 😕")}}

            assistant_message = {"role": "assistant", "content": json.dumps(result), "timestamp": datetime.utcnow().isoformat()}
            mongo.database.usuarios.update_one(
                {"correo": email, "chats.name": "HubSpotChat"},
                {"$push": {"chats.$.messages": {"$each": [user_message, assistant_message]}}}
            )

            return jsonify(result)

        except Exception as e:
            return jsonify({"solicitud": "ERROR", "result": {"error": f"¡Se puso feo! Error inesperado: {str(e)} 😓"}}), 500

    return chatHubSpot