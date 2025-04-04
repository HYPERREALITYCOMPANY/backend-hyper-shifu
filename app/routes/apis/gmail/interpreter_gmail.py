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
def gmail_chat(app, mongo, cache, refresh_functions):
    hoy = datetime.today().strftime('%Y-%m-%d')
    gmail_system_info = f"""
    Eres un intérprete de intenciones avanzado para la API de Gmail. Tu tarea es analizar la query recibida, clasificarla según el tipo de solicitud y generar una respuesta procesada ejecutando el método correspondiente. Sigue estos pasos:

    1. **Clasificación del Tipo de Solicitud**:
    - **GET**: Si la query pide información con términos como 'from:', 'proyecto', o cualquier búsqueda (ej. 'from: juan', 'proyecto Shell'), clasifica como: `"Es una solicitud GET"`.
    - **POST**: Si la query pide una acción como 'enviar correo a', 'mover a spam', 'eliminar', 'create_event' (ej. 'enviar correo a juan@gmail.com', 'mover a spam'), clasifica como: `"Es una solicitud POST"`.
    - **Automatizada**: Si la query es un dict con 'condition' y 'action' (ej. {{"condition": "recibir correo de juan@gmail.com", "action": "mover a spam"}}), clasifica como: `"Es una solicitud automatizada"`.
    - **Contexto**: Si la query menciona una respuesta anterior (ej. 'from: juan' en un contexto previo), clasifica como: `"Se refiere a la respuesta anterior"`.

    2. **Procesamiento de la Query**:
    - **GET**: 
        - Si contiene 'from:', extrae el remitente y busca correos (ej. 'from: juan' → buscar correos de juan).
        - Devuelve un JSON con los resultados: `{{"results": [{{"link": "<url>", "subject": "<asunto>"}}]}}`.
    - **POST**:
        - Si es 'enviar correo a', extrae el destinatario y envía el correo (ej. 'enviar correo a juan@gmail.com' → enviar correo).
        - Si es 'mover a spam', extrae el remitente o criterio y mueve a spam.
        - Si es 'create_event', extrae los detalles (summary, start, end, attendees) y crea el evento.
        - Devuelve un string con el resultado: `"Correo enviado a <destinatario>"`, `"Correo movido a spam"`, etc.
    - **Automatizada**:
        - Extrae la condición y la acción (ej. 'condition: recibir correo de juan@gmail.com', 'action: mover a spam').
        - Devuelve un string: `"Automatización configurada: Si <condición>, entonces <acción>"`.
    - **Contexto**:
        - Usa la query y el contexto previo para buscar más información (ej. 'from: juan' → buscar más correos de juan).
        - Devuelve un JSON similar al GET: `{{"results": [{{"link": "<url>", "subject": "<asunto>"}}]}}`.

    3. **Reglas Específicas**:
    - Si falta información clave (ej. destinatario en 'enviar correo a'), devuelve: `"Falta información clave"`.
    - Para eventos, si no se especifica la hora, asume 1 hora desde la fecha indicada (ej. 'start:2025-03-31T10:00:00' → 'end:2025-03-31T11:00:00').
    - Usa la fecha actual ({hoy}) para inferir fechas incompletas (ej. 'mañana' → '2025-04-03').

    4. **Formato de Salida**:
    - GET: `{{"results": [{{"link": "<url>", "subject": "<asunto>"}}]}}`
    - POST: String con el resultado (ej. `"Correo enviado a juan@gmail.com"`)
    - Automatizada: String (ej. `"Automatización configurada: Si recibir correo de juan@gmail.com, entonces mover a spam"`)
    - Contexto: Similar a GET: `{{"results": [{{"link": "<url>", "subject": "<asunto>"}}]}}`

    Ejemplos:
    - Query: "from: juan"
    Salida: "Es una solicitud GET" {{"results": [{{"link": "https://mail.google.com/mail/u/0/#inbox/123", "subject": "Correo de juan"}}]}}
    - Query: "enviar correo a alan.cruz@gmail.com con asunto: Extension de pago"
    Salida: "Es una solicitud POST" "Correo enviado a alan.cruz@gmail.com con asunto: Extension de pago"
    - Query: {{"condition": "recibir correo de juan@gmail.com", "action": "mover a spam"}}
    Salida: "Es una solicitud automatizada" "Automatización configurada: Si recibir correo de juan@gmail.com, entonces mover a spam"
    - Query: "from: alan.cruz@gmail.com" (con contexto)
    Salida: "Se refiere a la respuesta anterior" {{"results": [{{"link": "https://mail.google.com/mail/u/0/#inbox/456", "subject": "Más correos de alan.cruz@gmail.com"}}]}}
    """
    
    def should_refresh_tokens(self, email):
        """Determina si se deben refrescar los tokens basado en el tiempo desde el último refresco."""
        last_refresh_key = f"last_refresh_{email}"
        last_refresh = self.cache.get(last_refresh_key)
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

    def get_user_with_refreshed_tokens(self, email):
        """Obtiene el usuario y refresca tokens solo si es necesario, aprovechando la caché optimizada."""
        try:
            user = self.cache.get(email)
            if not user:
                print(f"[INFO] Usuario {email} no está en caché, consultando DB")
                user = get_user_from_db(email, self.cache, self.mongo)  # Asumiendo esta función existe
                if not user:
                    print(f"[ERROR] Usuario {email} no encontrado en DB")
                    return None
                self.cache.set(email, user, timeout=1800)

            if not self.should_refresh_tokens(email):
                print(f"[INFO] Tokens de {email} no necesitan refresco, devolviendo usuario cacheado")
                return user

            refresh_tokens_dict = self.get_refresh_tokens_from_db(email)
            if not refresh_tokens_dict or "gmail" not in refresh_tokens_dict:
                print(f"[INFO] No hay refresh tokens para Gmail de {email}, marcando tiempo y devolviendo usuario")
                self.cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
                return user

            integrations = user.get("integrations", {})
            tokens_to_refresh = {
                "gmail": refresh_tokens_dict["gmail"]
            } if "gmail" in integrations and integrations["gmail"].get("refresh_token") not in (None, "n/a") else {}

            if not tokens_to_refresh:
                print(f"[INFO] No hay tokens válidos para refrescar Gmail para {email}, marcando tiempo")
                self.cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
                return user

            print(f"[INFO] Refrescando tokens de Gmail para {email}")
            refreshed_tokens, errors = self.refresh_tokens_func(tokens_to_refresh, email)

            if refreshed_tokens:
                print(f"[INFO] Tokens de Gmail refrescados para {email}")
                user = get_user_from_db(email, self.cache, self.mongo)
                if not user:
                    print(f"[ERROR] No se pudo recargar usuario {email} tras refresco")
                    return None
                self.cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
                return user
            
            if errors:
                print(f"[WARNING] Errores al refrescar tokens de Gmail para {email}: {errors}")
                self.cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
                return user

            print(f"[INFO] No se refrescaron tokens de Gmail para {email}, marcando tiempo")
            self.cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
            return user

        except Exception as e:
            print(f"[ERROR] Error en get_user_with_refreshed_tokens para {email}: {e}")
            return None
        
    @app.route("/api/chat/gmail", methods=["POST"])
    def chatGmail(self):
        """Método para manejar chats relacionados con Gmail."""
        data = request.get_json()
        email = data.get("email")  # Obtenemos el email del JSON
        if not email:
            email = request.args.get("email")  # Fallback a query param
        user_messages = data.get("messages", [])

        if not email:
            return jsonify({"error": "Email del usuario es requerido"}), 400

        # Obtenemos el usuario con tokens refrescados
        user = self.get_user_with_refreshed_tokens(email)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404
        
        print(f"[DEBUG] Usuario cargado inicialmente: {user}")

        # Aseguramos que el usuario tenga un campo 'chats' con "GmailChat"
        if "chats" not in user or not any(chat["name"] == "GmailChat" for chat in user.get("chats", [])):
            print(f"[INFO] El usuario {email} no tiene chat 'GmailChat', inicializando")
            result = self.mongo.database.usuarios.update_one(
                {"correo": email},
                {"$set": {"chats": [{"name": "GmailChat", "messages": []}]}} if "chats" not in user else {"$push": {"chats": {"name": "GmailChat", "messages": []}}},
                upsert=True
            )
            print(f"[DEBUG] Inicialización de chats, matched: {result.matched_count}, modified: {result.modified_count}")
            user = self.mongo.database.usuarios.find_one({"correo": email})
            print(f"[DEBUG] Usuario tras inicializar GmailChat: {user}")

        # Buscamos el chat "GmailChat"
        gmail_chat = next((chat for chat in user["chats"] if chat["name"] == "GmailChat"), None)
        if not gmail_chat:
            print(f"[ERROR] No se encontró el chat 'GmailChat' después de inicializar para {email}")
            return jsonify({"error": "Error interno al inicializar el chat"}), 500
        print(f"[INFO] Mensajes previos en GmailChat: {len(gmail_chat['messages'])}")

        # Añadimos el nuevo mensaje del usuario al historial con timestamp
        if user_messages:
            last_message = user_messages[-1].get("content", "").lower()
            timestamp = datetime.utcnow().isoformat()
            user_message = {"role": "user", "content": last_message, "timestamp": timestamp}

            try:
                # Filtramos mensajes de los últimos 3 días por defecto
                three_days_ago = datetime.utcnow() - timedelta(days=3)
                filtered_messages = [
                    msg for msg in gmail_chat["messages"]
                    if datetime.fromisoformat(msg["timestamp"]) >= three_days_ago
                ]

                # Detectamos si el usuario pide un contexto mayor
                context_keywords = ["semana", "hace días", "hace una semana", "mes", "año", "hace tiempo"]
                use_full_history = any(keyword in last_message for keyword in context_keywords)

                if use_full_history:
                    print(f"[INFO] Detectado contexto mayor a 3 días en '{last_message}', usando historial completo")
                    filtered_messages = gmail_chat["messages"]

                print(f"[INFO] Mensajes enviados al contexto: {len(filtered_messages)} de {len(gmail_chat['messages'])} totales")

                # Creamos el prompt con el historial filtrado o completo, enfocado en Gmail
                prompt = f"Interpreta la query del usuario sobre Gmail: {last_message}"
                response = openai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": gmail_system_info},
                        *filtered_messages,
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=1000
                )
                ia_interpretation = response.choices[0].message.content.strip()
                print("Interpretación:", ia_interpretation)

                # Separamos el tipo de solicitud y el JSON
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

                # Añadimos los mensajes al chat "GmailChat" en la DB
                assistant_message = {
                    "role": "assistant",
                    "content": ia_interpretation,
                    "timestamp": datetime.utcnow().isoformat()
                }
                result = self.mongo.database.usuarios.update_one(
                    {"correo": email, "chats.name": "GmailChat"},
                    {"$push": {"chats.$.messages": {"$each": [user_message, assistant_message]}}}
                )
                print(f"[INFO] Mensajes añadidos al chat GmailChat para {email}, matched: {result.matched_count}, modified: {result.modified_count}")

                # Recargamos el usuario para confirmar
                user = self.mongo.database.usuarios.find_one({"correo": email})
                print(f"[DEBUG] Usuario tras actualizar mensajes: {user}")

                # Manejo según el tipo de solicitud, enfocado en Gmail
                if "saludo" in request_type.lower():
                    prompt_greeting = f"Usuario: {last_message}\nResponde de manera cálida y amigable sobre Gmail, con emojis."
                    response_greeting = openai.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "system", "content": "Eres un asistente amigable especializado en Gmail."}, {"role": "user", "content": prompt_greeting}],
                        max_tokens=150
                    )
                    ia_response = response_greeting.choices[0].message.content.strip()

                elif "GET" in request_type:
                    print("Procesando solicitud GET para Gmail")
                    if interpretation_json.get("gmail") != "N/A":
                        print("Gmail respondió:", interpretation_json["gmail"])
                        ia_response = {
                            "message": "Petición GET procesada para Gmail",
                            "apis": [{"api": "gmail", "response": f"Obteniendo datos de Gmail: {interpretation_json['gmail']}"}]
                        }
                    else:
                        ia_response = {"message": "No se especificó una consulta válida para Gmail"}

                elif "POST" in request_type:
                    print("Procesando solicitud POST para Gmail")
                    if interpretation_json.get("gmail") != "N/A":
                        print("Gmail respondió:", interpretation_json["gmail"])
                        ia_response = {
                            "message": "Petición POST procesada para Gmail",
                            "apis": [{"api": "gmail", "response": f"Ejecutando acción en Gmail: {interpretation_json['gmail']}"}]
                        }
                    else:
                        ia_response = {"message": "No se especificó una acción válida para Gmail"}

                else:
                    ia_response = {"message": f"Tipo de solicitud '{request_type}' no soportado específicamente para Gmail", "interpretation": ia_interpretation}

            except Exception as e:
                ia_response = f"Error: {str(e)}"
        else:
            ia_response = "No se proporcionó ningún mensaje."

        return jsonify(ia_response)