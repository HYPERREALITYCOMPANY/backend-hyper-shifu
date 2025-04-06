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

def slack_chat(app, mongo, cache, refresh_functions, query=None):
    hoy = datetime.today().strftime('%Y-%m-%d')

    slack_system_info = f"""
    Eres un intérprete de intenciones avanzado para la API de Slack. Tu tarea es analizar el mensaje del usuario, clasificarlo en una categoría general y generar consultas generales. Para GET y POST simples, enfócate solo en Slack. Para solicitudes múltiples y automatizadas, incluye todas las intenciones detectadas (incluso de otras APIs) sin filtrarlas, dejando que un intérprete multitarea las procese. Si el mensaje es ambiguo o no se puede clasificar, solicita aclaración al usuario. Sigue estos pasos:

    1. **Clasificación del Tipo de Solicitud**:
       - **Saludo**: Si el mensaje es un saludo (ej. 'hola', '¿cómo estás?', 'buenos días'), responde con: `"Es un saludo"`.
       - **Solicitud GET**: Si el usuario pide información con verbos como 'Mándame', 'Pásame', 'Envíame', 'Muéstrame', 'Busca', 'Dame', 'Dime', 'Quiero ver', 'Lista', 'Encuentra' (ej. 'Dame los mensajes del canal #general'), responde con: `"Es una solicitud GET"`.
       - **Solicitud POST**: Si el usuario pide una acción con verbos como 'Enviar', 'Publicar', 'Crear', 'Eliminar', 'Actualizar' (ej. 'Enviar mensaje al canal #general'), responde con: `"Es una solicitud POST"`.
       - **Solicitud Automatizada**: Si el usuario pide algo repetitivo o condicional con frases como 'Cada vez que', 'Siempre que', 'Automáticamente', 'Si pasa X haz Y' (ej. 'Si recibo un mensaje, notifica a Juan'), responde con: `"Es una solicitud automatizada"`.
       - **Solicitud Múltiple**: Si el mensaje combina varias acciones con conjunciones como 'y', 'luego', 'después', o verbos consecutivos (ej. 'Busca mensajes y envía uno nuevo'), responde con: `"Es una solicitud múltiple"`.
       - **No Clasificable**: Si el mensaje es demasiado vago o incompleto (ej. 'Haz algo', 'Mensaje'), responde con: `"No puedo clasificar la solicitud, por favor aclara qué quieres hacer"`.

    2. **Reglas Críticas para Clasificación**:
       - **GET**: Solicitudes de lectura solo para Slack (obtener mensajes, canales, usuarios).
       - **POST**: Acciones de escritura solo para Slack (enviar mensajes, actualizar mensajes, eliminar mensajes).
       - **Automatizadas**: Acciones con condiciones, detectando intenciones para Slack y otras APIs mencionadas por el usuario Ascendancy también puede incluir otras APIs.
       - **Múltiple**: Detecta conjunciones ('y', 'luego'), verbos consecutivos, o intenciones separadas, incluyendo acciones de cualquier API mencionada.
       - **Ambigüedad**: Si un verbo podría ser GET o POST (ej. 'Manda'), usa el contexto; si no hay suficiente, clasifica como "No Clasificable".
       - **Errores del Usuario**: Si falta información clave (ej. 'Busca mensajes' sin especificar dónde), clasifica como "No Clasificable".

    3. **Detección y Generación de Consultas**:
       - Para **GET y POST simples**, genera intenciones solo para Slack:
         - **Slack**: Buscar mensajes, obtener canales, enviar mensajes, actualizar mensajes, eliminar mensajes.
       - Para **Automatizadas y Múltiples**, incluye todas las intenciones detectadas, incluso si involucran otras APIs (ej. Dropbox, Gmail), sin filtrarlas.
       - Si una acción no encaja con Slack en GET o POST simples, usa 'N/A'.

    4. **Formato de Salida**:
       - Devuelve un string con el tipo de solicitud seguido de un JSON con consultas generales bajo la clave "slack".
       - **GET y POST simples**: Usa 'N/A' si no aplica a Slack.
       - **Automatizadas**: Lista condiciones y acciones, incluyendo otras APIs si se mencionan.
       - **Múltiples**: Lista todas las intenciones detectadas como un array, sin filtrar por Slack.
       - **No Clasificable**: `{{"message": "Por favor, aclara qué quieres hacer"}}`.

    5. **Estructura del JSON**:
       - **GET**: `{{"slack": "<intención>"}}`
       - **POST**: `{{"slack": "<intención>"}}`
       - **Automatizada**: `{{"slack": [{{"condition": "<condición>", "action": "<acción>"}}, ...]}}`
       - **Múltiple**: `{{"slack": ["<intención 1>", "<intención 2>", ...]}}`
       - **No Clasificable**: `{{"message": "Por favor, aclara qué quieres hacer"}}`

    6. **Reglas para Consultas Generales**:
       - **GET**: Describe qué obtener en Slack (ej. "obtener mensajes del canal #general"). Si no aplica, "No Clasificable".
       - **POST**: Describe la acción en Slack (ej. "enviar mensaje al canal #general"). Si no aplica, "No Clasificable".
       - **Automatizada**: Divide en condición y acción, incluyendo otras APIs (ej. "cuando reciba un mensaje" y "notificar a Juan").
       - **Múltiple**: Separa cada intención en una frase clara, incluyendo acciones de otras APIs (ej. "subir archivo a Dropbox").
       - Incluye nombres o datos clave del usuario (ej. "#general", "Juan") si se mencionan.

    Ejemplos:
    - "Dame los mensajes del canal #general" → "Es una solicitud GET" {{"slack": "obtener mensajes del canal #general"}}
    - "Enviar mensaje al canal #general" → "Es una solicitud POST" {{"slack": "enviar mensaje al canal #general"}}
    - "Si recibo un mensaje, notifica a Juan" → "Es una solicitud automatizada" {{"slack": [{{"condition": "recibir un mensaje", "action": "notificar a Juan"}}]}}
    - "Busca mensajes y envía uno nuevo" → "Es una solicitud múltiple" {{"slack": ["obtener mensajes", "enviar un mensaje nuevo"]}}
    - "Hola" → "Es un saludo" {{"slack": "N/A"}}
    - "Subir archivo a Dropbox" → "No puedo clasificar la solicitud, por favor aclara qué quieres hacer" {{"message": "Esto no es una acción para Slack, ¿qué quieres hacer con Slack?"}}
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

    def handle_get_request(intencion, email):
        user = get_user_with_refreshed_tokens(email)
        if not user:
            return {"solicitud": "GET", "result": {"error": "¡Órale! No te encontré, compa 😕"}}, 404

        slack_token = user.get('integrations', {}).get('slack', {}).get('token')
        if not slack_token:
            return {"solicitud": "GET", "result": {"error": "¡Ey! No tengo tu token de Slack, ¿me das permisos? 🔑"}}, 400

        headers = {'Authorization': f"Bearer {slack_token}", 'Content-Type': 'application/json'}
        url = "https://slack.com/api/conversations.history"

        query = intencion["slack"]
        if not query or query == "N/A":
            return {"solicitud": "GET", "result": {"error": "¡Falta algo, papu! ¿Qué quieres buscar en Slack? 🤔"}}, 400

        try:
            if "obtener mensajes" in query.lower():
                channel_match = re.search(r'del canal\s*#?(\w+)', query, re.IGNORECASE)
                channel_name = channel_match.group(1) if channel_match else None
                if not channel_name:
                    return {"solicitud": "GET", "result": {"error": "¡Ey! ¿De qué canal quieres los mensajes? Usa #nombre 😄"}}, 400
                # Simulación: obtener ID del canal (en realidad, necesitarías /conversations.list)
                channel_id = f"C{channel_name.upper()}"  # Placeholder
                params = {"channel": channel_id, "limit": 10}
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()
                messages = response.json().get('messages', [])
                results = [{"text": msg["text"], "user": msg.get("user", "Unknown")} for msg in messages]
                if not results:
                    return {"solicitud": "GET", "result": {"message": "📭 No encontré mensajes en ese canal, ¿probamos otro?"}}, 200
                return {"solicitud": "GET", "result": {"message": f"¡Órale! Encontré {len(results)} mensajes en #{channel_name} 💬", "data": results}}, 200
            else:
                return {"solicitud": "GET", "result": {"error": "¡Uy! Solo puedo buscar mensajes por ahora, ¿qué tal eso? 😅"}}, 400
        except requests.RequestException as e:
            return {"solicitud": "GET", "result": {"error": f"¡Ay, qué mala onda! Error con Slack: {str(e)}"}}, 500

    def handle_post_request(intencion, email):
        user = get_user_with_refreshed_tokens(email)
        if not user:
            return {"solicitud": "POST", "result": {"error": "¡Órale! No te encontré, compa 😕"}}, 404

        slack_token = user.get('integrations', {}).get('slack', {}).get('token')
        if not slack_token:
            return {"solicitud": "POST", "result": {"error": "¡Ey! No tengo tu token de Slack, ¿me das permisos? 🔑"}}, 400

        headers = {'Authorization': f"Bearer {slack_token}", 'Content-Type': 'application/json'}

        query = intencion["slack"]
        if isinstance(query, list) and all(isinstance(item, str) for item in query):
            return {"solicitud": "POST", "result": {"message": "Solicitud múltiple detectada, pasando al intérprete multitarea", "actions": query}}, 200
        if isinstance(query, list) and all(isinstance(item, dict) and "condition" in item for item in query):
            return {"solicitud": "POST", "result": {"message": "Solicitud automatizada detectada, pasando al intérprete multitarea", "actions": query}}, 200

        try:
            # Enviar mensaje
            if "enviar mensaje" in query.lower():
                match = re.search(r'enviar\s*mensaje\s*(?:al canal\s*#?(\w+))?\s*(.+)?', query, re.IGNORECASE)
                if not match:
                    return {"solicitud": "POST", "result": {"error": "¡Ey! ¿A qué canal y qué mensaje quieres enviar? Usa 'enviar mensaje al canal #nombre texto' 😄"}}, 400
                channel_name = match.group(1) or None
                message_text = match.group(2) or None
                if not channel_name or not message_text:
                    return {"solicitud": "POST", "result": {"error": "¡Falta algo! Necesito el canal (#nombre) y el texto del mensaje 📝"}}, 400
                # Simulación: obtener ID del canal (en realidad, necesitarías /conversations.list)
                channel_id = f"C{channel_name.upper()}"  # Placeholder
                url = "https://slack.com/api/chat.postMessage"
                payload = {"channel": channel_id, "text": message_text}
                response = requests.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return {"solicitud": "POST", "result": {"message": f"💬 Mensaje enviado al canal #{channel_name} con éxito 🚀"}}, 200

            # Actualizar mensaje (simulado, requiere timestamp del mensaje original)
            elif "actualizar mensaje" in query.lower():
                match = re.search(r'actualizar\s*mensaje\s*en\s*#?(\w+)\s*con\s*(.+)', query, re.IGNORECASE)
                if not match:
                    return {"solicitud": "POST", "result": {"error": "¡Ey! ¿Qué mensaje y en qué canal (#nombre) quieres actualizar? 🤔"}}, 400
                channel_name = match.group(1).strip()
                new_text = match.group(2).strip()
                channel_id = f"C{channel_name.upper()}"  # Placeholder
                # Simulación: necesitarías el ts (timestamp) del mensaje original
                url = "https://slack.com/api/chat.update"
                payload = {"channel": channel_id, "ts": "simulated_ts", "text": new_text}
                response = requests.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return {"solicitud": "POST", "result": {"message": f"✨ Mensaje actualizado en #{channel_name} con '{new_text}'"}}, 200

            # Eliminar mensaje (simulado, requiere timestamp)
            elif "eliminar mensaje" in query.lower():
                match = re.search(r'eliminar\s*mensaje\s*en\s*#?(\w+)', query, re.IGNORECASE)
                if not match:
                    return {"solicitud": "POST", "result": {"error": "¡Ey! ¿Qué mensaje y en qué canal (#nombre) quieres eliminar? 🗑️"}}, 400
                channel_name = match.group(1).strip()
                channel_id = f"C{channel_name.upper()}"  # Placeholder
                url = "https://slack.com/api/chat.delete"
                payload = {"channel": channel_id, "ts": "simulated_ts"}
                response = requests.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return {"solicitud": "POST", "result": {"message": f"🗑️ Mensaje eliminado en #{channel_name} con éxito"}}, 200

            return {"solicitud": "POST", "result": {"error": "¡Uy! Acción no soportada en Slack, ¿qué tal enviar o actualizar un mensaje? 😅"}}, 400

        except requests.RequestException as e:
            return {"solicitud": "POST", "result": {"error": f"¡Ay, qué mala onda! Error con Slack: {str(e)}"}}, 500
        except Exception as e:
            return {"solicitud": "POST", "result": {"error": f"¡Se puso feo! Error inesperado: {str(e)}"}}, 500

    @app.route("/api/chat/slack", methods=["POST"])
    def chatSlack():
        email = request.args.get("email")
        data = request.get_json()
        user_query = data.get("messages", [{}])[-1].get("content") if data.get("messages") else None
        if not email:
            return jsonify({"error": "¡Órale! Necesito tu email, compa 😅"}), 400
        if not user_query:
            return jsonify({"error": "¡Ey! Dame algo pa’ trabajar, ¿qué quieres hacer con Slack? 🤔"}), 400

        user = get_user_with_refreshed_tokens(email)
        if not user:
            return jsonify({"error": "¡Uy! No te encontré en el sistema, ¿seguro que estás registrado? 😕"}), 404

        if "chats" not in user or not any(chat["name"] == "SlackChat" for chat in user.get("chats", [])):
            mongo.database.usuarios.update_one(
                {"correo": email},
                {"$set": {"chats": [{"name": "SlackChat", "messages": []}]}} if "chats" not in user else {"$push": {"chats": {"name": "SlackChat", "messages": []}}},
                upsert=True
            )
            user = get_user_with_refreshed_tokens(email)

        slack_chat = next((chat for chat in user["chats"] if chat["name"] == "SlackChat"), None)
        if not slack_chat:
            return jsonify({"error": "¡Qué mala onda! Error al inicializar el chat 😓"}), 500

        timestamp = datetime.utcnow().isoformat()
        user_message = {"role": "user", "content": user_query, "timestamp": timestamp}

        try:
            prompt = f"""
            Interpreta esta query para Slack: "{user_query}"
            Si es un saludo (como "hola", "holaaaa"), responde: "Es un saludo" {{"slack": "N/A"}}
            Si es otra cosa, clasifica como GET, POST, etc., según las reglas del system prompt anterior.
            Devuelve el resultado en formato: "TIPO" {{"clave": "valor"}}
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

            request_type_match = re.match(r'^"([^"]+)"\s*(\{.*\})', ia_response, re.DOTALL)
            if not request_type_match:
                result = {"message": "¡Uy! Algo salió mal, ¿puedes intentarlo otra vez? 😅"}
            else:
                request_type = request_type_match.group(1)
                json_str = request_type_match.group(2)
                parsed_response = json.loads(json_str)

                if request_type == "Es un saludo":
                    greeting_prompt = f"El usuario dijo {user_query}. Responde de manera cálida y amigable con emojis a un saludo simple. Menciona que eres su asistente personalizado de Slack."
                    greeting_response = openai.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "system", "content": "Eres su asistente personal de Slack muy amigable."}, {"role": "user", "content": greeting_prompt}],
                        max_tokens=200
                    )
                    result = {"message": greeting_response.choices[0].message.content.strip()}
                elif request_type == "Es una solicitud GET":
                    result = handle_get_request(parsed_response, email)
                elif request_type in ["Es una solicitud POST", "Es una solicitud automatizada", "Es una solicitud múltiple"]:
                    result = handle_post_request(parsed_response, email)
                else:
                    result = {"solicitud": "ERROR", "result": {"error": parsed_response.get("message", "¡No entendí qué quieres hacer con Slack! 😕")}}

            assistant_message = {"role": "assistant", "content": json.dumps(result), "timestamp": datetime.utcnow().isoformat()}
            mongo.database.usuarios.update_one(
                {"correo": email, "chats.name": "SlackChat"},
                {"$push": {"chats.$.messages": {"$each": [user_message, assistant_message]}}}
            )

            return jsonify(result)

        except Exception as e:
            return jsonify({"solicitud": "ERROR", "result": {"error": f"¡Se puso feo! Error inesperado: {str(e)} 😓"}}), 500

    return chatSlack