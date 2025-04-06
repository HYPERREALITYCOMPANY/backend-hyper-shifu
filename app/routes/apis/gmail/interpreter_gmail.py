from datetime import datetime, timedelta, time
from flask import request, jsonify
from config import Config
import json
import re
from zoneinfo import ZoneInfo
import openai
from email.mime.text import MIMEText
import base64
import requests
openai.api_key = Config.CHAT_API_KEY
from app.utils.utils import get_user_from_db
from flask_caching import Cache
from .getFunctionGmail import handle_get_request
from .postFunctionGmail import handle_post_request
def gmail_chat(app, mongo, cache, refresh_functions, query=None):
    hoy = datetime.today().strftime('%Y-%m-%d')

    gmail_system_info = f"""
    Eres un intérprete de intenciones avanzado para la API de Gmail y Google Calendar, pero también debes detectar acciones relacionadas con otras APIs cuando el usuario las mencione en solicitudes múltiples o automatizadas. Tu tarea es analizar el mensaje del usuario, clasificarlo en una categoría general y generar consultas generales. Para GET y POST simples, enfócate solo en Gmail/Google Calendar. Para solicitudes múltiples y automatizadas, incluye todas las intenciones detectadas (incluso de otras APIs) sin filtrarlas, dejando que un intérprete multitarea las procese. Si el mensaje es ambiguo o no se puede clasificar, solicita aclaración al usuario. Sigue estos pasos:

    1. **Clasificación del Tipo de Solicitud**:
       - **Saludo**: Si el mensaje es un saludo (ej. 'hola', '¿cómo estás?', 'buenos días'), responde con: `"Es un saludo"`.
       - **Solicitud GET**: Si el usuario pide información para sí mismo con verbos como 'Mándame', 'Pásame', 'Envíame', 'Muéstrame', 'Busca', 'Dame', 'Dime', 'Quiero ver', 'Lista', 'Encuentra' (ej. 'Dame los correos de Juan'), responde con: `"Es una solicitud GET"`.
       - **Solicitud POST**: Si el usuario pide una acción con verbos como 'Crear', 'Enviar', 'Eliminar', 'Mover', 'Marcar', 'Archivar', 'Agendar', 'Escribe' (ej. 'Enviar correo a Juan'), responde con: `"Es una solicitud POST"`.
       - **Solicitud Automatizada**: Si el usuario pide algo repetitivo o condicional con frases como 'Cada vez que', 'Siempre que', 'Automáticamente', 'Si pasa X haz Y' (ej. 'Si recibo un correo de Juan, envía un mensaje a Slack'), responde con: `"Es una solicitud automatizada"`.
       - **Solicitud Múltiple**: Si el mensaje combina varias acciones con conjunciones como 'y', 'luego', 'después', o verbos consecutivos (ej. 'Busca correos de Ana y sube un archivo a Drive'), responde con: `"Es una solicitud múltiple"`.
       - **No Clasificable**: Si el mensaje es demasiado vago o incompleto (ej. 'Haz algo', 'Juan'), responde con: `"No puedo clasificar la solicitud, por favor aclara qué quieres hacer"`.

    2. **Reglas Críticas para Clasificación**:
       - **GET**: Solicitudes de lectura solo para Gmail/Google Calendar (obtener correos o eventos).
       - **POST**: Acciones de escritura solo para Gmail/Google Calendar (enviar correos, crear eventos, etc.).
       - **Automatizadas**: Acciones con condiciones, detectando intenciones para Gmail y otras APIs mencionadas por el usuario.
       - **Múltiple**: Detecta conjunciones ('y', 'luego'), verbos consecutivos, o intenciones separadas, incluyendo acciones de cualquier API mencionada.
       - **Ambigüedad**: Si un verbo podría ser GET o POST (ej. 'Manda'), usa el contexto; si no hay suficiente, clasifica como "No Clasificable".
       - **Errores del Usuario**: Si falta información clave (ej. 'Busca el correo' sin especificar de quién), clasifica como "No Clasificable".

    3. **Detección y Generación de Consultas**:
       - Para **GET y POST simples**, genera intenciones solo para Gmail/Google Calendar:
         - **Gmail**: Buscar correos, enviar correos, eliminar correos, mover a spam/papelera, crear borradores, marcar como leído/no leído, archivar correos.
         - **Google Calendar**: Agendar reuniones, buscar eventos, eliminar eventos, modificar eventos.
       - Para **Automatizadas y Múltiples**, incluye todas las intenciones detectadas, incluso si involucran otras APIs (ej. Slack, Drive, ClickUp), sin filtrarlas.
       - Si una acción no encaja con Gmail/Google Calendar en GET o POST simples, usa 'N/A'.

    4. **Formato de Salida**:
       - Devuelve un string con el tipo de solicitud seguido de un JSON con consultas generales bajo la clave "gmail".
       - **GET y POST simples**: Usa 'N/A' si no aplica a Gmail/Google Calendar.
       - **Automatizadas**: Lista condiciones y acciones, incluyendo otras APIs si se mencionan.
       - **Múltiples**: Lista todas las intenciones detectadas como un array, sin filtrar por Gmail.
       - **No Clasificable**: `{{"message": "Por favor, aclara qué quieres hacer"}}`.

    5. **Estructura del JSON**:
       - **GET**: `{{"gmail": "<intención>"}}`
       - **POST**: `{{"gmail": "<intención>"}}`
       - **Automatizada**: `{{"gmail": [{{"condition": "<condición>", "action": "<acción>"}}, ...]}}`
       - **Múltiple**: `{{"gmail": ["<intención 1>", "<intención 2>", ...]}}`
       - **No Clasificable**: `{{"message": "Por favor, aclara qué quieres hacer"}}`

    6. **Reglas para Consultas Generales**:
       - **GET**: Describe qué obtener en Gmail (ej. "obtener correos de Juan"). Si no aplica, "No Clasificable".
       - **POST**: Describe la acción en Gmail (ej. "enviar un correo a Juan"). Si no aplica, "No Clasificable".
       - **Automatizada**: Divide en condición y acción, incluyendo otras APIs (ej. "cuando reciba un correo de Juan" y "enviar un mensaje a Slack").
       - **Múltiple**: Separa cada intención en una frase clara, incluyendo acciones de otras APIs (ej. "subir un archivo a Drive").
       - Incluye nombres o datos clave del usuario (ej. "Juan", "mañana") si se mencionan.

    Ejemplos:
    - "Mandame el correo de Hyper" -> "Es una solicitud GET {{"gmail": "Obtener correos de Hyper"}}
    - "Dame los correos de Juan" → "Es una solicitud GET" {{"gmail": "obtener correos de Juan"}}
    - "Enviar correo a Juan" → "Es una solicitud POST" {{"gmail": "enviar un correo a Juan"}}
    - "Si recibo un correo de Juan, envía un mensaje a Slack" → "Es una solicitud automatizada" {{"gmail": [{{"condition": "recibir un correo de Juan", "action": "enviar un mensaje a Slack"}}]}}
    - "Busca correos de Ana y sube un archivo a Drive" → "Es una solicitud múltiple" {{"gmail": ["obtener correos de Ana", "subir un archivo a Drive"]}}
    - "Hola" → "Es un saludo" {{"gmail": "N/A"}}
    - "Sube un archivo a Drive" → "No puedo clasificar la solicitud, por favor aclara qué quieres hacer" {{"message": "Esto no es una acción para Gmail, ¿qué quieres hacer con Gmail?"}}
    - "Busca el correo" → "No puedo clasificar la solicitud, por favor aclara qué quieres hacer" {{"message": "Por favor, aclara qué correo quieres buscar y de quién"}}
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
                "gmail": refresh_tokens_dict["gmail"]
            } if "gmail" in integrations and integrations["gmail"].get("refresh_token") not in (None, "n/a") else {}

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
        dataUser = request.get_json()
        
        user_query = query or dataUser.get("messages", [{}])[-1].get("content") if dataUser.get("messages") else None
        message = result.get("message", "No se pudo procesar la solicitud, algo salió mal.")
        data = result.get("data", None)

        # Armar el texto base con los resultados
        if data and "correos" in message.lower():
            correo_info = "\n".join(
                f"De: {item['from']} | Asunto: {item['subject']} | Fecha: {item['date']}"
                for item in data
            )
            base_text = f"El usuario pidió correos y esto encontré:\n{message}\nDetalles:\n{correo_info}"
        elif data and "eventos" in message.lower():
            evento_info = "\n".join(
                f"Evento: {item['summary']} | Inicio: {item['start']}"
                for item in data
            )
            base_text = f"El usuario pidió eventos y esto encontré:\n{message}\nDetalles:\n{evento_info}"
        else:
            base_text = f"El usuario pidió algo y esto obtuve:\n{message}" + (f"\nDetalles: {str(data)}" if data else "")

        # Prompt para la IA
        prompt = f"""
        Debes responder la peticion del usuario: {user_query}
        Eres un asistente de Gmail súper amigable y útil, con un tono relajado y natural, como si charlaras con un amigo. Usa emojis sutiles para darle onda, pero sin exagerar. Basándote en esta info, arma una respuesta concisa y en párrafo que resuma los resultados de forma práctica y clara:

        {base_text}

        - Si hay resultados, haz un resumen breve y útil, mencionando cuántos correos o eventos encontré y algo relevante (como quién los mandó o de qué tratan), sin listar todo como tabla.
        - Si no hay resultados, di algo amable y sugiere ajustar la búsqueda si hace falta.
        - Habla en primera persona y evita sonar robótico o repetir los datos crudos tal cual. Y pon emojis
        NO INCLUYAS LINKS y responde amigable pero FORMALMENTE
        """

        # Llamada a la IA
        try:
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",  # O "gpt-4o-mini" si prefieres
                messages=[
                    {"role": "system", "content": "Eres un asistente de Gmail amigable."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=400  # Reduje un poco para respuestas más cortas y naturales
            )
            ia_response = response.choices[0].message.content.strip()
            return ia_response
        except Exception as e:
            return f"¡Ups! Algo salió mal al armar la respuesta: {str(e)}"
        
    @app.route("/api/chat/gmail", methods=["POST"])
    def chatGmail():
        email = request.args.get("email")
        data = request.get_json()
        user_query = query or data.get("messages", [{}])[-1].get("content") if data.get("messages") else None
        if not email:
            return jsonify({"message": {"error": "¡Órale! Necesito el email del usuario pa’ trabajar, ¿me lo pasas?"}}), 400
        if not user_query:
            return jsonify({"message": {"error": "¡Ey! No me diste ninguna query, ¿qué quieres que haga?"}}), 400

        user = get_user_with_refreshed_tokens(email)
        if not user:
            return jsonify({"message": {"error": "No encontré a este usuario, ¿seguro que está registrado?"}}), 404

        # Inicializar el chat si no existe
        if "chats" not in user or not any(chat["name"] == "GmailChat" for chat in user.get("chats", [])):
            mongo.database.usuarios.update_one(
                {"correo": email},
                {"$set": {"chats": [{"name": "GmailChat", "messages": []}]}} if "chats" not in user else {"$push": {"chats": {"name": "GmailChat", "messages": []}}},
                upsert=True
            )
            user = get_user_with_refreshed_tokens(email)

        gmail_chat = next((chat for chat in user["chats"] if chat["name"] == "GmailChat"), None)
        if not gmail_chat:
            return jsonify({"message": {"error": "¡Uy! Algo salió mal al preparar el chat, ¿intentamos otra vez?"}}), 500

        timestamp = datetime.utcnow().isoformat()
        user_message = {"role": "user", "content": user_query, "timestamp": timestamp}

        try:
            # Prompt ajustado pa’ englobar acciones en categorías
            prompt = f"""
            Interpreta esta query para Gmail: "{user_query}"
            Devuelve un JSON con esta estructura:
            {{
            "peticion": "GET" | "POST" | "SALUDO" | "AUTOMATIZADA" | "MULTIPLE" | "NO_CLASIFICABLE",
            "accion": "buscar" | "enviar" | "crear" | "eliminar" | "mover" | "agendar" | "marcar" | "archivar" | "responder" | null (si es saludo o no clasificable),
            "solicitud": "<detalles específicos>" | null (si no aplica) | [array de acciones para MULTIPLE] | [{{"condition": "...", "action": "..."}} para AUTOMATIZADA]
            }}

            Reglas:
            1. Si es un saludo (ej. "hola"), responde un string como "SALUDO".
            2. Para GET, agrupa verbos de lectura como "dame", "mándame", "buscar", "muéstrame", "lista", "encuentra" en "accion": "buscar".
            3. Para POST, agrupa verbos en estas categorías:
            - "enviar": "enviar", "manda", "envía", "enviale"
            - "crear": "crear", "hacer", "redactar", "redacta"
            - "eliminar": "eliminar", "borrar", "quitar"
            - "mover": "mover", "trasladar"
            - "agendar": "agendar", "programar", "agendame"
            - "marcar": "marcar", "señalar"
            - "archivar": "archivar", "guardar"
            - "responder": "responder", "contestar", "responde"
            4. Si es AUTOMATIZADA o MULTIPLE, usa arrays según el system prompt.
            5. Si no se entiende, usa "peticion": "NO_CLASIFICABLE", "accion": null, "solicitud": "Por favor, aclara qué quieres hacer".
            6. Interpreta el verbo principal y agrúpalo en la categoría correspondiente, no limites las variaciones.

            Ejemplos:
            - "Holaaaa" → SALUDO
            - "Mándame los correos de Juan" → {{"peticion": "GET", "accion": "buscar", "solicitud": "correos de Juan"}}
            - "Redacta un correo para Juan con asunto: Hola" → {{"peticion": "POST", "accion": "crear", "solicitud": "correo para Juan con asunto: Hola"}}
            - "Envía un correo a Ana" → {{"peticion": "POST", "accion": "enviar", "solicitud": "correo a Ana"}}
            - "Si recibo correo de Juan, envía mensaje" → {{"peticion": "AUTOMATIZADA", "accion": null, "solicitud": [{{"condition": "recibo correo de Juan", "action": "envía mensaje"}}]}}
            """
            response = openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": gmail_system_info},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500
            )
            ia_response = response.choices[0].message.content.strip()
            print(ia_response)
            # Parseo del JSON
            try:
            # Regex pa’ capturar JSON completo, incluso anidado
                json_pattern = r'\{(?:[^{}]|\{[^{}]*\})*\}'
                match = re.search(json_pattern, ia_response, re.DOTALL | re.MULTILINE)
                print("Match encontrado:", match)  # Debug como pediste

                if match:
                    json_str = match.group(0)  # Extrae el JSON encontrado
                    print("JSON extraído:", json_str)  # Más debug pa’ ver qué sacó
                    parsed_response = json.loads(json_str)  # Parsea el JSON
                    peticion = parsed_response.get("peticion")
                    accion = parsed_response.get("accion")
                    solicitud = parsed_response.get("solicitud")
            except json.JSONDecodeError:
                parsed_response = {"peticion": "NO_CLASIFICABLE", "accion": None, "solicitud": "¡Ups! Algo salió mal con la respuesta, ¿me lo repites?"}
                peticion = parsed_response["peticion"]
                accion = parsed_response["accion"]
                solicitud = parsed_response["solicitud"]

            # Manejo según el tipo de petición
            if "saludo" in peticion.lower():
                greeting_prompt = f"El usuario dijo '{user_query}', responde de manera cálida y amigable con emojis. Menciona que eres su asistente personalizado de Gmail."
                greeting_response = openai.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "system", "content": "Eres su asistente personal de Gmail muy amigable."}, {"role": "user", "content": greeting_prompt}],
                    max_tokens=200
                )
                result = greeting_response.choices[0].message.content.strip()
                status = 200
            elif "get" in peticion.lower():
                result, status = handle_get_request(accion, solicitud, email, user)
                print(result)
                result = generate_prompt(result)
                print(result)
            elif "POST" in peticion:
                result, status = handle_post_request(accion, solicitud, email, user)
                result = result.get("result", {}).get("message", "No se encontró mensaje")
            else:
                result = {"solicitud": "ERROR", "result": {"error": solicitud}}
                status = 400

            # Guardar en la DB
            assistant_message = {"role": "assistant", "content": json.dumps(result), "timestamp": datetime.utcnow().isoformat()}
            mongo.database.usuarios.update_one(
                {"correo": email, "chats.name": "GmailChat"},
                {"$push": {"chats.$.messages": {"$each": [user_message, assistant_message]}}}
            )

            return jsonify({"message": result}), status

        except Exception as e:
            return jsonify({"message": {"solicitud": "ERROR", "result": {"error": f"¡Ay, caray! Algo se rompió: {str(e)}"}}}), 500

    return chatGmail