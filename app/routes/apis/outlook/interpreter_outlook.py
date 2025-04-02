from datetime import datetime
from flask import request, jsonify
from datetime import datetime, timedelta
from config import Config
import json
import openai
import re
openai.api_key = Config.CHAT_API_KEY
from app.utils.utils import get_user_from_db
from flask_caching import Cache
def outlook_chat(app, mongo, cache, refresh_functions):
    hoy = datetime.today().strftime('%Y-%m-%d')
    outlook_system_info = f"""
    Eres un intérprete de intenciones avanzado para la API de Outlook. Tu tarea es analizar la query recibida, clasificarla según el tipo de solicitud y generar una respuesta procesada ejecutando el método correspondiente. Sigue estos pasos:

    1. **Clasificación del Tipo de Solicitud**:
    - **GET**: Si la query pide información con términos como 'from:', 'proyecto', o búsqueda (ej. 'from: juan', 'proyecto Shell'), clasifica como: `"Es una solicitud GET"`.
    - **POST**: Si la query pide una acción como 'enviar correo a', 'mover a spam', 'eliminar' (ej. 'enviar correo a juan@outlook.com', 'mover a spam'), clasifica como: `"Es una solicitud POST"`.
    - **Automatizada**: Si la query es un dict con 'condition' y 'action' (ej. {{"condition": "recibir correo de juan@outlook.com", "action": "mover a spam"}}), clasifica como: `"Es una solicitud automatizada"`.
    - **Contexto**: Si la query menciona una respuesta anterior (ej. 'from: juan'), clasifica como: `"Se refiere a la respuesta anterior"`.

    2. **Procesamiento de la Query**:
    - **GET**: 
        - Si contiene 'from:', extrae el remitente y busca correos.
        - Devuelve un JSON: `{{"results": [{{"webLink": "<url>", "subject": "<asunto>"}}]}}`.
    - **POST**:
        - Si es 'enviar correo a', extrae el destinatario y envía el correo.
        - Si es 'mover a spam', mueve el correo a spam.
        - Si es 'eliminar', elimina el correo.
        - Devuelve un string: `"Correo enviado a <destinatario>"`, `"Correo movido a spam"`, etc.
    - **Automatizada**:
        - Extrae la condición y la acción.
        - Devuelve un string: `"Automatización configurada: Si <condición>, entonces <acción>"`.
    - **Contexto**:
        - Usa la query y el contexto previo para buscar más información.

    3. **Reglas Específicas**:
    - Si falta información clave, devuelve: `"Falta información clave"`.
    - Usa la fecha actual ({hoy}) para inferir fechas incompletas.

    4. **Formato de Salida**:
    - GET: `{{"results": [{{"webLink": "<url>", "subject": "<asunto>"}}]}}`
    - POST: String
    - Automatizada: String
    - Contexto: Similar a GET
    """

    def should_refresh_tokens(email):
        last_refresh_key = f"last_refresh_{email}"
        last_refresh = cache.get(last_refresh_key)
        current_time = datetime.utcnow()

        if last_refresh is None:
            print(f"[INFO] No hay registro de último refresco para {email}, forzando refresco")
            return True

        last_refresh_time = datetime.fromtimestamp(last_refresh)
        refresh_interval = timedelta(minutes=30)
        time_since_last_refresh = current_time - last_refresh_time

        if time_since_last_refresh >= refresh_interval:
            print(f"[INFO] Han pasado {time_since_last_refresh} desde el último refresco para {email}, refrescando")
            return True
        
        print(f"[INFO] Tokens de {email} aún vigentes, faltan {refresh_interval - time_since_last_refresh} para refrescar")
        return False

    def get_user_with_refreshed_tokens(email):
        try:
            user = cache.get(email)
            if not user:
                print(f"[INFO] Usuario {email} no está en caché, consultando DB")
                user = get_user_from_db(email, cache, mongo)
                if not user:
                    print(f"[ERROR] Usuario {email} no encontrado en DB")
                    return None
                cache.set(email, user, timeout=1800)

            if not should_refresh_tokens(email):
                print(f"[INFO] Tokens de {email} no necesitan refresco, devolviendo usuario cacheado")
                return user

            refresh_tokens_dict = refresh_functions["get_refresh_tokens_from_db"](email)
            if not refresh_tokens_dict or "outlook" not in refresh_tokens_dict:
                print(f"[INFO] No hay refresh tokens para Outlook de {email}, marcando tiempo y devolviendo usuario")
                cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
                return user

            integrations = user.get("integrations", {})
            tokens_to_refresh = {
                "outlook": refresh_tokens_dict["outlook"]
            } if "outlook" in integrations and integrations["outlook"].get("refresh_token") not in (None, "n/a") else {}

            if not tokens_to_refresh:
                print(f"[INFO] No hay tokens válidos para refrescar Outlook para {email}, marcando tiempo")
                cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
                return user

            print(f"[INFO] Refrescando tokens de Outlook para {email}")
            refreshed_tokens, errors = refresh_functions["refresh_tokens"](tokens_to_refresh, email)

            if refreshed_tokens:
                print(f"[INFO] Tokens de Outlook refrescados para {email}")
                user = get_user_from_db(email, cache, mongo)
                if not user:
                    print(f"[ERROR] No se pudo recargar usuario {email} tras refresco")
                    return None
                cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
                return user
            
            if errors:
                print(f"[WARNING] Errores al refrescar tokens de Outlook para {email}: {errors}")
                cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
                return user

            print(f"[INFO] No se refrescaron tokens de Outlook para {email}, marcando tiempo")
            cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
            return user

        except Exception as e:
            print(f"[ERROR] Error en get_user_with_refreshed_tokens para {email}: {e}")
            return None
        
    @app.route("/api/chat/outlook", methods=["POST"])
    def chatOutlook():
        data = request.get_json()
        email = data.get("email")
        if not email:
            email = request.args.get("email")
        user_messages = data.get("messages", [])

        if not email:
            return jsonify({"error": "Email del usuario es requerido"}), 400

        user = get_user_with_refreshed_tokens(email)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404
        
        print(f"[DEBUG] Usuario cargado inicialmente: {user}")

        if "chats" not in user or not any(chat["name"] == "OutlookChat" for chat in user.get("chats", [])):
            print(f"[INFO] El usuario {email} no tiene chat 'OutlookChat', inicializando")
            result = mongo.database.usuarios.update_one(
                {"correo": email},
                {"$set": {"chats": [{"name": "OutlookChat", "messages": []}]}} if "chats" not in user else {"$push": {"chats": {"name": "OutlookChat", "messages": []}}},
                upsert=True
            )
            print(f"[DEBUG] Inicialización de chats, matched: {result.matched_count}, modified: {result.modified_count}")
            user = mongo.database.usuarios.find_one({"correo": email})
            print(f"[DEBUG] Usuario tras inicializar OutlookChat: {user}")

        outlook_chat = next((chat for chat in user["chats"] if chat["name"] == "OutlookChat"), None)
        if not outlook_chat:
            print(f"[ERROR] No se encontró el chat 'OutlookChat' después de inicializar para {email}")
            return jsonify({"error": "Error interno al inicializar el chat"}), 500
        print(f"[INFO] Mensajes previos en OutlookChat: {len(outlook_chat['messages'])}")

        if user_messages:
            last_message = user_messages[-1].get("content", "").lower()
            timestamp = datetime.utcnow().isoformat()
            user_message = {"role": "user", "content": last_message, "timestamp": timestamp}

            try:
                three_days_ago = datetime.utcnow() - timedelta(days=3)
                filtered_messages = [
                    msg for msg in outlook_chat["messages"]
                    if datetime.fromisoformat(msg["timestamp"]) >= three_days_ago
                ]

                context_keywords = ["semana", "hace días", "hace una semana", "mes", "año", "hace tiempo"]
                use_full_history = any(keyword in last_message for keyword in context_keywords)

                if use_full_history:
                    print(f"[INFO] Detectado contexto mayor a 3 días en '{last_message}', usando historial completo")
                    filtered_messages = outlook_chat["messages"]

                print(f"[INFO] Mensajes enviados al contexto: {len(filtered_messages)} de {len(outlook_chat['messages'])} totales")

                prompt = f"Interpreta la query del usuario sobre Outlook: {last_message}"
                response = openai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": outlook_system_info},
                        *filtered_messages,
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=1000
                )
                ia_interpretation = response.choices[0].message.content.strip()
                print("Interpretación:", ia_interpretation)

                request_type_match = re.match(r'^"?([^"]+)"?\s*\{', ia_interpretation, re.DOTALL)
                request_type = request_type_match.group(1).strip() if request_type_match else "Desconocido"
                json_match = re.search(r'\{[^}]*\}', ia_interpretation, re.DOTALL | re.MULTILINE)
                if json_match:
                    json_str = json_match.group(0)
                    interpretation_json = json.loads(json_str)
                else:
                    raise ValueError("No se encontró un JSON válido en la interpretación")

                print("Tipo de solicitud:", request_type)
                print("JSON extraído:", interpretation_json)

                assistant_message = {
                    "role": "assistant",
                    "content": ia_interpretation,
                    "timestamp": datetime.utcnow().isoformat()
                }
                result = mongo.database.usuarios.update_one(
                    {"correo": email, "chats.name": "OutlookChat"},
                    {"$push": {"chats.$.messages": {"$each": [user_message, assistant_message]}}}
                )
                print(f"[INFO] Mensajes añadidos al chat OutlookChat para {email}, matched: {result.matched_count}, modified: {result.modified_count}")

                user = mongo.database.usuarios.find_one({"correo": email})
                print(f"[DEBUG] Usuario tras actualizar mensajes: {user}")

                if "saludo" in request_type.lower():
                    prompt_greeting = f"Usuario: {last_message}\nResponde de manera cálida y amigable sobre Outlook, con emojis."
                    response_greeting = openai.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "system", "content": "Eres un asistente amigable especializado en Outlook."}, {"role": "user", "content": prompt_greeting}],
                        max_tokens=150
                    )
                    ia_response = response_greeting.choices[0].message.content.strip()

                elif "GET" in request_type:
                    print("Procesando solicitud GET para Outlook")
                    if interpretation_json.get("outlook") != "N/A":
                        print("Outlook respondió:", interpretation_json["outlook"])
                        ia_response = {
                            "message": "Petición GET procesada para Outlook",
                            "apis": [{"api": "outlook", "response": f"Obteniendo datos de Outlook: {interpretation_json['outlook']}"}]
                        }
                    else:
                        ia_response = {"message": "No se especificó una consulta válida para Outlook"}

                elif "POST" in request_type:
                    print("Procesando solicitud POST para Outlook")
                    if interpretation_json.get("outlook") != "N/A":
                        print("Outlook respondió:", interpretation_json["outlook"])
                        ia_response = {
                            "message": "Petición POST procesada para Outlook",
                            "apis": [{"api": "outlook", "response": f"Ejecutando acción en Outlook: {interpretation_json['outlook']}"}]
                        }
                    else:
                        ia_response = {"message": "No se especificó una acción válida para Outlook"}

                else:
                    ia_response = {"message": f"Tipo de solicitud '{request_type}' no soportado específicamente para Outlook", "interpretation": ia_interpretation}

            except Exception as e:
                ia_response = f"Error: {str(e)}"
        else:
            ia_response = "No se proporcionó ningún mensaje."

        return jsonify(ia_response)