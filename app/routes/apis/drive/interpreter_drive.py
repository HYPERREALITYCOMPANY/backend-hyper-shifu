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

def drive_chat(app, mongo, cache, refresh_functions, query=None):
    hoy = datetime.today().strftime('%Y-%m-%d')

    drive_system_info = f"""
    Eres un intérprete de intenciones avanzado para la API de Google Drive. Tu tarea es analizar el mensaje del usuario, clasificarlo en una categoría general y generar consultas generales. Para GET y POST simples, enfócate solo en Google Drive. Para solicitudes múltiples y automatizadas, incluye todas las intenciones detectadas (incluso de otras APIs) sin filtrarlas, dejando que un intérprete multitarea las procese. Si el mensaje es ambiguo o no se puede clasificar, solicita aclaración al usuario. Sigue estos pasos:

    1. **Clasificación del Tipo de Solicitud**:
       - **Saludo**: Si el mensaje es un saludo (ej. 'hola', '¿cómo estás?', 'buenos días'), responde con: `"Es un saludo"`.
       - **Solicitud GET**: Si el usuario pide información con verbos como 'Mándame', 'Pásame', 'Envíame', 'Muéstrame', 'Busca', 'Dame', 'Dime', 'Quiero ver', 'Lista', 'Encuentra' (ej. 'Dame los archivos de mi carpeta'), responde con: `"Es una solicitud GET"`.
       - **Solicitud POST**: Si el usuario pide una acción con verbos como 'Crear', 'Subir', 'Eliminar', 'Actualizar', 'Agregar', 'Mover' (ej. 'Subir archivo Proyecto X'), responde con: `"Es una solicitud POST"`.
       - **Solicitud Automatizada**: Si el usuario pide algo repetitivo o condicional con frases como 'Cada vez que', 'Siempre que', 'Automáticamente', 'Si pasa X haz Y' (ej. 'Si subo un archivo, notifica a Juan'), responde con: `"Es una solicitud automatizada"`.
       - **Solicitud Múltiple**: Si el mensaje combina varias acciones con conjunciones como 'y', 'luego', 'después', o verbos consecutivos (ej. 'Busca archivos y sube uno nuevo'), responde con: `"Es una solicitud múltiple"`.
       - **No Clasificable**: Si el mensaje es demasiado vago o incompleto (ej. 'Haz algo', 'Archivo'), responde con: `"No puedo clasificar la solicitud, por favor aclara qué quieres hacer"`.

    2. **Reglas Críticas para Clasificación**:
       - **GET**: Solicitudes de lectura solo para Google Drive (obtener archivos, carpetas, listar contenido).
       - **POST**: Acciones de escritura solo para Google Drive (subir archivos, actualizar nombres, eliminar archivos).
       - **Automatizadas**: Acciones con condiciones, detectando intenciones para Drive y otras APIs mencionadas por el usuario.
       - **Múltiple**: Detecta conjunciones ('y', 'luego'), verbos consecutivos, o intenciones separadas, incluyendo acciones de cualquier API mencionada.
       - **Ambigüedad**: Si un verbo podría ser GET o POST (ej. 'Manda'), usa el contexto; si no hay suficiente, clasifica como "No Clasificable".
       - **Errores del Usuario**: Si falta información clave (ej. 'Busca archivos' sin especificar dónde), clasifica como "No Clasificable".

    3. **Detección y Generación de Consultas**:
       - Para **GET y POST simples**, genera intenciones solo para Google Drive:
         - **Drive**: Buscar archivos, obtener carpetas, subir archivos, actualizar archivos, eliminar archivos.
       - Para **Automatizadas y Múltiples**, incluye todas las intenciones detectadas, incluso si involucran otras APIs (ej. Gmail, Slack), sin filtrarlas.
       - Si una acción no encaja con Drive en GET o POST simples, usa 'N/A'.

    4. **Formato de Salida**:
       - Devuelve un string con el tipo de solicitud seguido de un JSON con consultas generales bajo la clave "drive".
       - **GET y POST simples**: Usa 'N/A' si no aplica a Drive.
       - **Automatizadas**: Lista condiciones y acciones, incluyendo otras APIs si se mencionan.
       - **Múltiples**: Lista todas las intenciones detectadas como un array, sin filtrar por Drive.
       - **No Clasificable**: `{{"message": "Por favor, aclara qué quieres hacer"}}`.

    5. **Estructura del JSON**:
       - **GET**: `{{"drive": "<intención>"}}`
       - **POST**: `{{"drive": "<intención>"}}`
       - **Automatizada**: `{{"drive": [{{"condition": "<condición>", "action": "<acción>"}}, ...]}}`
       - **Múltiple**: `{{"drive": ["<intención 1>", "<intención 2>", ...]}}`
       - **No Clasificable**: `{{"message": "Por favor, aclara qué quieres hacer"}}`

    6. **Reglas para Consultas Generales**:
       - **GET**: Describe qué obtener en Drive (ej. "obtener archivos de la carpeta Proyecto X"). Si no aplica, "No Clasificable".
       - **POST**: Describe la acción en Drive (ej. "subir archivo Proyecto X"). Si no aplica, "No Clasificable".
       - **Automatizada**: Divide en condición y acción, incluyendo otras APIs (ej. "cuando suba un archivo" y "notificar a Juan").
       - **Múltiple**: Separa cada intención en una frase clara, incluyendo acciones de otras APIs (ej. "enviar correo a Juan").
       - Incluye nombres o datos clave del usuario (ej. "Proyecto X", "mañana") si se mencionan.

    Ejemplos:
    - "Dame los archivos de mi carpeta" → "Es una solicitud GET" {{"drive": "obtener archivos de mi carpeta"}}
    - "Subir archivo Proyecto X" → "Es una solicitud POST" {{"drive": "subir archivo Proyecto X"}}
    - "Si subo un archivo, notifica a Juan" → "Es una solicitud automatizada" {{"drive": [{{"condition": "subir un archivo", "action": "notificar a Juan"}}]}}
    - "Busca archivos y sube uno nuevo" → "Es una solicitud múltiple" {{"drive": ["obtener archivos", "subir un archivo nuevo"]}}
    - "Hola" → "Es un saludo" {{"drive": "N/A"}}
    - "Crear tarea en Asana" → "No puedo clasificar la solicitud, por favor aclara qué quieres hacer" {{"message": "Esto no es una acción para Drive, ¿qué quieres hacer con Drive?"}}
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

    def handle_get_request(intencion, email):
        user = get_user_with_refreshed_tokens(email)
        if not user:
            return {"solicitud": "GET", "result": {"error": "¡Órale! No te encontré, compa 😕"}}, 404

        drive_token = user.get('integrations', {}).get('drive', {}).get('token')
        if not drive_token:
            return {"solicitud": "GET", "result": {"error": "¡Ey! No tengo tu token de Google Drive, ¿me das permisos? 🔑"}}, 400

        headers = {'Authorization': f"Bearer {drive_token}", 'Content-Type': 'application/json'}
        url = "https://www.googleapis.com/drive/v3/files"

        query = intencion["drive"]
        if not query or query == "N/A":
            return {"solicitud": "GET", "result": {"error": "¡Falta algo, papu! ¿Qué quieres buscar en Drive? 🤔"}}, 400

        try:
            if "obtener archivos" in query.lower():
                folder_name = query.split("de")[-1].strip() if "de" in query else ""
                params = {"q": f"'root' in parents {folder_name}" if folder_name else "'root' in parents", "fields": "files(id,name,webViewLink)"}
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()
                files = response.json().get('files', [])
                results = [{"file_name": file["name"], "url": file["webViewLink"]} for file in files]
                if not results:
                    return {"solicitud": "GET", "result": {"message": "📭 No encontré archivos con eso, ¿probamos otra cosa?"}}, 200
                return {"solicitud": "GET", "result": {"message": f"¡Órale! Encontré {len(results)} archivos 📁", "data": results}}, 200
            else:
                return {"solicitud": "GET", "result": {"error": "¡Uy! Solo puedo buscar archivos por ahora, ¿qué tal eso? 😅"}}, 400
        except requests.RequestException as e:
            return {"solicitud": "GET", "result": {"error": f"¡Ay, qué mala onda! Error con Drive: {str(e)}"}}, 500

    def handle_post_request(intencion, email):
        user = get_user_with_refreshed_tokens(email)
        if not user:
            return {"solicitud": "POST", "result": {"error": "¡Órale! No te encontré, compa 😕"}}, 404

        drive_token = user.get('integrations', {}).get('drive', {}).get('token')
        if not drive_token:
            return {"solicitud": "POST", "result": {"error": "¡Ey! No tengo tu token de Google Drive, ¿me das permisos? 🔑"}}, 400

        headers = {'Authorization': f"Bearer {drive_token}", 'Content-Type': 'application/json'}

        query = intencion["drive"]
        if isinstance(query, list) and all(isinstance(item, str) for item in query):
            return {"solicitud": "POST", "result": {"message": "Solicitud múltiple detectada, pasando al intérprete multitarea", "actions": query}}, 200
        if isinstance(query, list) and all(isinstance(item, dict) and "condition" in item for item in query):
            return {"solicitud": "POST", "result": {"message": "Solicitud automatizada detectada, pasando al intérprete multitarea", "actions": query}}, 200

        try:
            # Subir archivo
            if "subir archivo" in query.lower():
                match = re.search(r'subir\s*archivo\s*(.+)', query, re.IGNORECASE)
                if not match:
                    return {"solicitud": "POST", "result": {"error": "¡Ey! ¿Cómo se llama el archivo que quieres subir? 📤"}}, 400
                file_name = match.group(1).strip()
                url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"
                # Simulación: en un entorno real, necesitarías el archivo binario
                metadata = {"name": file_name}
                headers['Content-Type'] = 'multipart/related; boundary=foo_bar_baz'
                payload = (
                    b'--foo_bar_baz\r\n'
                    b'Content-Type: application/json; charset=UTF-8\r\n\r\n' +
                    json.dumps(metadata).encode('utf-8') +
                    b'\r\n--foo_bar_baz\r\n'
                    b'Content-Type: text/plain\r\n\r\n'
                    b"Contenido simulado del archivo\r\n"
                    b'--foo_bar_baz--'
                )
                response = requests.post(url, headers=headers, data=payload)
                response.raise_for_status()
                return {"solicitud": "POST", "result": {"message": f"📤 Archivo '{file_name}' subido con éxito 🚀"}}, 200

            # Actualizar archivo
            elif "actualizar archivo" in query.lower():
                match = re.search(r'actualizar\s*archivo\s*"(.+?)"\s*con\s*(.+)', query, re.IGNORECASE)
                if not match:
                    return {"solicitud": "POST", "result": {"error": "¡Ey! ¿Qué archivo y qué cambio quieres hacer? 🤔"}}, 400
                file_name = match.group(1).strip()
                update_content = match.group(2).strip()
                # Simulación: buscar archivo primero
                search_url = "https://www.googleapis.com/drive/v3/files"
                response = requests.get(search_url, headers=headers, params={"q": file_name, "fields": "files(id,name)"})
                response.raise_for_status()
                files = response.json().get('files', [])
                file_id = next((f["id"] for f in files if f["name"].lower() == file_name.lower()), None)
                if not file_id:
                    return {"solicitud": "POST", "result": {"message": f"📭 No encontré el archivo '{file_name}'"}}, 200
                url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
                payload = {"name": f"{file_name} - {update_content}"}
                response = requests.patch(url, headers=headers, json=payload)
                response.raise_for_status()
                return {"solicitud": "POST", "result": {"message": f"✨ Archivo '{file_name}' actualizado con '{update_content}'"}}, 200

            # Eliminar archivo
            elif "eliminar archivo" in query.lower():
                match = re.search(r'eliminar\s*archivo\s*"(.+?)"', query, re.IGNORECASE)
                if not match:
                    return {"solicitud": "POST", "result": {"error": "¡Ey! ¿Qué archivo quieres eliminar? 🗑️"}}, 400
                file_name = match.group(1).strip()
                search_url = "https://www.googleapis.com/drive/v3/files"
                response = requests.get(search_url, headers=headers, params={"q": file_name, "fields": "files(id,name)"})
                response.raise_for_status()
                files = response.json().get('files', [])
                file_id = next((f["id"] for f in files if f["name"].lower() == file_name.lower()), None)
                if not file_id:
                    return {"solicitud": "POST", "result": {"message": f"📭 No encontré el archivo '{file_name}'"}}, 200
                url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
                response = requests.delete(url, headers=headers)
                response.raise_for_status()
                return {"solicitud": "POST", "result": {"message": f"🗑️ Archivo '{file_name}' eliminado con éxito"}}, 200

            return {"solicitud": "POST", "result": {"error": "¡Uy! Acción no soportada en Drive, ¿qué tal subir o actualizar un archivo? 😅"}}, 400

        except requests.RequestException as e:
            return {"solicitud": "POST", "result": {"error": f"¡Ay, qué mala onda! Error con Drive: {str(e)}"}}, 500
        except Exception as e:
            return {"solicitud": "POST", "result": {"error": f"¡Se puso feo! Error inesperado: {str(e)}"}}, 500

    @app.route("/api/chat/drive", methods=["POST"])
    def chatDrive():
        email = request.args.get("email")
        data = request.get_json()
        user_query = data.get("messages", [{}])[-1].get("content") if data.get("messages") else None
        if not email:
            return jsonify({"error": "¡Órale! Necesito tu email, compa 😅"}), 400
        if not user_query:
            return jsonify({"error": "¡Ey! Dame algo pa’ trabajar, ¿qué quieres hacer con Drive? 🤔"}), 400

        user = get_user_with_refreshed_tokens(email)
        if not user:
            return jsonify({"error": "¡Uy! No te encontré en el sistema, ¿seguro que estás registrado? 😕"}), 404

        if "chats" not in user or not any(chat["name"] == "DriveChat" for chat in user.get("chats", [])):
            mongo.database.usuarios.update_one(
                {"correo": email},
                {"$set": {"chats": [{"name": "DriveChat", "messages": []}]}} if "chats" not in user else {"$push": {"chats": {"name": "DriveChat", "messages": []}}},
                upsert=True
            )
            user = get_user_with_refreshed_tokens(email)

        drive_chat = next((chat for chat in user["chats"] if chat["name"] == "DriveChat"), None)
        if not drive_chat:
            return jsonify({"error": "¡Qué mala onda! Error al inicializar el chat 😓"}), 500

        timestamp = datetime.utcnow().isoformat()
        user_message = {"role": "user", "content": user_query, "timestamp": timestamp}

        try:
            prompt = f"""
            Interpreta esta query para Google Drive: "{user_query}"
            Si es un saludo (como "hola", "holaaaa"), responde: "Es un saludo" {{"drive": "N/A"}}
            Si es otra cosa, clasifica como GET, POST, etc., según las reglas del system prompt anterior.
            Devuelve el resultado en formato: "TIPO" {{"clave": "valor"}}
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

            request_type_match = re.match(r'^"([^"]+)"\s*(\{.*\})', ia_response, re.DOTALL)
            if not request_type_match:
                result = {"message": "¡Uy! Algo salió mal, ¿puedes intentarlo otra vez? 😅"}
            else:
                request_type = request_type_match.group(1)
                json_str = request_type_match.group(2)
                parsed_response = json.loads(json_str)

                if request_type == "Es un saludo":
                    greeting_prompt = f"El usuario dijo {user_query}. Responde de manera cálida y amigable con emojis a un saludo simple. Menciona que eres su asistente personalizado de Google Drive."
                    greeting_response = openai.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "system", "content": "Eres su asistente personal de Google Drive muy amigable."}, {"role": "user", "content": greeting_prompt}],
                        max_tokens=200
                    )
                    result = {"message": greeting_response.choices[0].message.content.strip()}
                elif request_type == "Es una solicitud GET":
                    result = handle_get_request(parsed_response, email)
                elif request_type in ["Es una solicitud POST", "Es una solicitud automatizada", "Es una solicitud múltiple"]:
                    result = handle_post_request(parsed_response, email)
                else:
                    result = {"solicitud": "ERROR", "result": {"error": parsed_response.get("message", "¡No entendí qué quieres hacer con Drive! 😕")}}

            assistant_message = {"role": "assistant", "content": json.dumps(result), "timestamp": datetime.utcnow().isoformat()}
            mongo.database.usuarios.update_one(
                {"correo": email, "chats.name": "DriveChat"},
                {"$push": {"chats.$.messages": {"$each": [user_message, assistant_message]}}}
            )

            return jsonify(result)

        except Exception as e:
            return jsonify({"solicitud": "ERROR", "result": {"error": f"¡Se puso feo! Error inesperado: {str(e)} 😓"}}), 500

    return chatDrive