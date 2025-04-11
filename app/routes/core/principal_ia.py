from flask import request, jsonify
from datetime import datetime, timedelta
from config import Config
import json
import openai
import re
from .system_prompt import system_prompt
openai.api_key = Config.CHAT_API_KEY
from app.utils.utils import get_user_from_db
from flask_caching import Cache
from app.routes.apis.gmail.interpreter_gmail import process_gmail_chat
from app.routes.apis.outlook.interpreter_outlook import process_outlook_chat
from app.routes.apis.asana.interpreter_asana import process_asana_chat
from app.routes.apis.clickup.interpreter_clickup import process_clickup_chat
from app.routes.apis.dropbox.interpreter_dropbox import process_dropbox_chat
from app.routes.apis.hubspot.interpreter_hubspot import process_hubspot_chat
from app.routes.apis.notion.interpreter_notion import process_notion_chat
from app.routes.apis.slack.interpreter_slack import process_slack_chat
from app.routes.apis.onedrive.interpreter_onedrive import process_onedrive_chat
from app.routes.apis.drive.interpreter_drive import process_drive_chat
from app.routes.core.context.ContextHandler import ContextHandler

def process_chat(email, user_query=None, mongo=None, cache=None, refresh_functions=None):
    """Core logic for processing general chat requests."""
    get_refresh_tokens_from_db = refresh_functions["get_refresh_tokens_from_db"]
    refresh_tokens_func = refresh_functions["refresh_tokens"]

    def should_refresh_tokens(email):
        """Determina si se deben refrescar los tokens basado en el tiempo desde el último refresco."""
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
        """Obtiene el usuario y refresca tokens solo si es necesario, aprovechando la caché optimizada."""
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

            refresh_tokens_dict = get_refresh_tokens_from_db(email)
            if not refresh_tokens_dict:
                print(f"[INFO] No hay refresh tokens para {email}, marcando tiempo y devolviendo usuario")
                cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
                return user

            integrations = user.get("integrations", {})
            tokens_to_refresh = {
                service: refresh_tokens_dict[service]
                for service in integrations
                if service in refresh_tokens_dict and integrations[service].get("refresh_token") not in (None, "n/a")
            }

            if not tokens_to_refresh:
                print(f"[INFO] No hay tokens válidos para refrescar para {email}, marcando tiempo")
                cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
                return user

            print(f"[INFO] Refrescando tokens para {email}: {list(tokens_to_refresh.keys())}")
            refreshed_tokens, errors = refresh_tokens_func(tokens_to_refresh, email)

            if refreshed_tokens:
                print(f"[INFO] Tokens refrescados para {email}: {list(refreshed_tokens.keys())}")
                user = get_user_from_db(email, cache, mongo)
                if not user:
                    print(f"[ERROR] No se pudo recargar usuario {email} tras refresco")
                    return None
                cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
                return user
            
            if errors:
                print(f"[WARNING] Errores al refrescar tokens para {email}: {errors}")
                cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
                return user

            print(f"[INFO] No se refrescaron tokens para {email}, marcando tiempo")
            cache.set(f"last_refresh_{email}", datetime.utcnow().timestamp(), timeout=1800)
            return user

        except Exception as e:
            print(f"[ERROR] Error en get_user_with_refreshed_tokens para {email}: {e}")
            return None

    def generate_prompt(apis_responses, request_type, user_query=None):
        """Genera una respuesta conversacional directa usando IA para interpretar los resultados de las APIs."""

        # Estructurar el contexto para la IA
        context = {
            "user_query": user_query if user_query else "información general",
            "request_type": request_type,
            "apis_responses": []
        }
        
        # Incluir solo la información relevante de cada respuesta de API
        for resp in apis_responses:
            if isinstance(resp.get("response", {}), dict) and "message" in resp["response"]:
                context["apis_responses"].append({
                    "api": resp.get("api", "desconocida"),
                    "message": resp["response"]["message"]
                })
        
        # Crear prompt para la IA
        system_prompt = """
        Eres un asistente amigable que interpreta resultados de múltiples APIs para generar respuestas conversacionales.
        
        INSTRUCCIONES:
        1. Analiza cada respuesta de API y determina su relevancia para la consulta del usuario.
        2. Ignora respuestas vacías, genéricas (como "N/A", "sin resultados"), o que empiecen con frases como "¡Hola!", "Lamentablemente".
        3. Extrae la información más relevante y preséntala de forma conversacional y amigable.
        4. Si no hay resultados válidos, sugiere amablemente al usuario que proporcione más detalles.
        5. Mantén un tono conversacional y amigable, pero directo y conciso.
        6. Usa máximo 1-2 emojis en toda la respuesta, no sobrecargues con emojis.
        7. Si la respuesta tiene más de 150 caracteres, resúmela e indica que hay más detalles disponibles.
        8. Personaliza tu respuesta según el tipo de consulta (correos, tareas, etc.)
        9. Termina con una pregunta apropiada según el tipo de solicitud.

        IMPORTANTE: Mantén tu respuesta concisa, natural y centrada en la información relevante.
        """
        
        user_prompt = json.dumps(context)
        
        # Realizar llamada a la API de chat
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",  # o el modelo que prefieras
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.5,  # Balancear creatividad con precisión
            max_tokens=300    # Limitar longitud de respuesta
        )
        
        # Obtener y devolver la respuesta generada
        ai_response = response.choices[0].message.content.strip()
        
        # Fallback en caso de error en la generación
        if not ai_response:
            query_part = f" sobre '{user_query}'" if user_query else ""
            ai_response = f"¡Hola! Encontré algo{query_part}. Permíteme organizarlo mejor para ti. ¿Qué te interesa saber específicamente?"
        
        return ai_response, user_prompt

    # Extract query if not provided
    if not user_query:
        try:
            data = request.get_json() or {}
            user_messages = data.get("messages", [])
            if user_messages:
                user_query = user_messages[-1].get("content", "").lower()
            if not email:
                email = data.get("email") or request.args.get("email")
        except Exception:
            return {"message": "¡Ey! No me diste un mensaje válido, ¿qué quieres que haga? 🤔"}, 400

    if not email:
        return {"message": "¡Órale! Necesito tu email pa’ trabajar, ¿me lo pasas? 😅"}, 400
    if not user_query:
        return {"message": "¡Ey! No me diste ningún mensaje, ¿qué quieres que haga? 🤷"}, 400

    user = get_user_with_refreshed_tokens(email)
    if not user:
        return {"message": "No encontré a este usuario, ¿seguro que está registrado? 😕"}, 404
    
    if "chats" not in user or not any(chat.get("name") == "Principal" for chat in user.get("chats", [])):
        print(f"[INFO] El usuario {email} no tiene chat 'Principal', inicializando")
        result = mongo.database.usuarios.update_one(
            {"correo": email},
            {"$set": {"chats": [{"name": "Principal", "messages": []}]}} if "chats" not in user else {"$push": {"chats": {"name": "Principal", "messages": []}}},
            upsert=True
        )
        print(f"[DEBUG] Inicialización de chats, matched: {result.matched_count}, modified: {result.modified_count}")

    principal_chat = next((chat for chat in user.get("chats", []) if chat.get("name") == "Principal"), None)
    if not principal_chat:
        print(f"[ERROR] No se encontró el chat 'Principal' después de inicializar para {email}")
        return {"message": "Error interno al inicializar el chat 😓"}, 500
    print(f"[INFO] Mensajes previos en Principal: {len(principal_chat['messages'])}")

    timestamp = datetime.utcnow().isoformat()
    user_message = {"role": "user", "content": user_query, "timestamp": timestamp}

    try:
        three_days_ago = datetime.utcnow() - timedelta(days=3)
        filtered_messages = [
            msg for msg in principal_chat["messages"]
            if datetime.fromisoformat(msg["timestamp"]) >= three_days_ago
        ]

        context_keywords = ["semana", "hace días", "hace una semana", "mes", "año", "hace tiempo"]
        use_full_history = any(keyword in user_query for keyword in context_keywords)

        if use_full_history:
            print(f"[INFO] Detectado contexto mayor a 3 días en '{user_query}', usando historial completo")
            filtered_messages = principal_chat["messages"]

        print(f"[INFO] Mensajes enviados al contexto: {len(filtered_messages)} de {len(principal_chat['messages'])} totales")

        prompt = f"""
        Interpreta esta query: "{user_query}"
"""
        print(prompt)
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000
        )
        ia_interpretation = response.choices[0].message.content.strip()
        print("Interpretación:", ia_interpretation)

        # Verificar si es un saludo antes de intentar parsear JSON
        if '"Es un saludo"' in ia_interpretation or 'saludo' in ia_interpretation.lower():
            print("[INFO] Detectado un saludo, generando respuesta amigable")
            prompt_greeting = f"Usuario: {user_query}\nResponde de manera cálida y amigable, con emojis."
            response_greeting = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Eres un asistente amigable."},
                    {"role": "user", "content": prompt_greeting}
                ],
                max_tokens=150
            )
            ia_response = response_greeting.choices[0].message.content.strip()

            assistant_message = {
                "role": "assistant",
                "content": ia_response,
                "timestamp": datetime.utcnow().isoformat()
            }
            result = mongo.database.usuarios.update_one(
                {"correo": email, "chats.name": "Principal"},
                {"$push": {"chats.$.messages": {"$each": [user_message, assistant_message]}}}
            )
            print(f"[INFO] Mensajes añadidos al chat Principal para {email}, matched: {result.matched_count}, modified: {result.modified_count}")
            
            return {"message": ia_response}, 200
        
        elif ia_interpretation == "Es una solicitud INFO" :
            print("[INFO] Procesando solicitud INFO directamente como texto")
            
            info_response = f"""LA QUERY DEL USUARIO ES {user_query}
            TU PUEDES HACER TODO LO QUE TE AGREGUE ABAJO, DEBES DE RESPONDERLE LA PREGUNTA QUE TE HIZO.

            📧 **Gmail y Outlook**: Puedo gestionar tus correos - buscar, enviar, eliminar, organizar y más. Con Gmail también puedo manejar tu calendario para agendar reuniones.

            📋 **ClickUp y Asana**: Te ayudo con la gestión de tareas y proyectos - buscar, crear, actualizar estados, asignar responsables y más.

            📓 **Notion**: Puedo manejar tus páginas y bases de datos - buscar, crear, actualizar contenido y organizar información.

            🤝 **HubSpot**: Gestiono contactos, negocios y tareas - buscar, crear, actualizar registros y asociar contactos a negocios.

            💬 **Slack y Teams**: Puedo buscar y enviar mensajes a canales o usuarios y reaccionar a mensajes.

            📁 **Google Drive, OneDrive y Dropbox**: Te ayudo con tus archivos - buscar, subir, eliminar, mover, crear carpetas y compartir documentos.

            RECUERDA QUE DEBES CONTESTAR LA DUDA DEL USUARIO YA QUE EL NO ESTA INFORMADO DE QUE FUNCIONALIDADES TIENES, AGREGA EMOJIS Y HAZ QUE SEA AMIGABLE
            """
            
            response_greeting = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Eres un asistente amigable."},
                    {"role": "user", "content": info_response}
                ],
                max_tokens=300
            )
            ia_response = response_greeting.choices[0].message.content.strip()
            
            assistant_message = {
                "role": "assistant",
                "content": ia_response,
                "timestamp": datetime.utcnow().isoformat()
            }
            result = mongo.database.usuarios.update_one(
                {"correo": email, "chats.name": "Principal"},
                {"$push": {"chats.$.messages": {"$each": [user_message, assistant_message]}}}
            )
            
            return {"message": ia_response}, 200
        elif "Es una solicitud GET_CONTEXT" == ia_interpretation.lower():
            print("Procesando solicitud GET_CONTEXT")
            context_handler = ContextHandler(mongo.database)
            apis_responses = []
            
            user_request = interpretation_json.get("request", user_query)
            result, status = context_handler.get_chat_context(
                email=email,
                chat_name="Principal",
                query=user_request,
                solicitud=user_request
            )

        # Procesar otras solicitudes que esperan un JSON
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
            {"correo": email, "chats.name": "Principal"},
            {"$push": {"chats.$.messages": {"$each": [user_message, assistant_message]}}}
        )
        print(f"[INFO] Mensajes añadidos al chat Principal para {email}, matched: {result.matched_count}, modified: {result.modified_count}")

        # Manejo de tipos de solicitudes
        if "Es una solicitud GET" == request_type:
            print("Procesando solicitud GET")
            apis_responses = []
            
            for api, query in interpretation_json.items():
                if query != "N/A":
                    if api == "gmail":
                        result, status = process_gmail_chat(email, query, mongo, cache, refresh_functions)
                        apis_responses.append({"api": "gmail", "response": result})
                    elif api == "outlook":
                        result, status = process_outlook_chat(email, query, mongo, cache, refresh_functions)
                        apis_responses.append({"api": "outlook", "response": result})
                    elif api == "clickup":
                        result, status = process_clickup_chat(email, query, mongo, cache, refresh_functions)
                        apis_responses.append({"api": "clickup", "response": result})
                    elif api == "asana":
                        result, status = process_asana_chat(email, query, mongo, cache, refresh_functions)
                        apis_responses.append({"api": "asana", "response": result})
                    elif api == "dropbox":
                        result, status = process_dropbox_chat(email, query, mongo, cache, refresh_functions)
                        apis_responses.append({"api": "dropbox", "response": result})
                    elif api == "hubspot":
                        result, status = process_hubspot_chat(email, query, mongo, cache, refresh_functions)
                        apis_responses.append({"api": "hubspot", "response": result})
                    elif api == "notion":
                        result, status = process_notion_chat(email, query, mongo, cache, refresh_functions)
                        apis_responses.append({"api": "notion", "response": result})
                    elif api == "slack":
                        result, status = process_slack_chat(email, query, mongo, cache, refresh_functions)
                        apis_responses.append({"api": "slack", "response": result})
                    elif api == "onedrive":
                        result, status = process_onedrive_chat(email, query, mongo, cache, refresh_functions)
                        apis_responses.append({"api": "onedrive", "response": result})
                    elif api == "googledrive":
                        result, status = process_drive_chat(email, query, mongo, cache, refresh_functions)
                        apis_responses.append({"api": "googledrive", "response": result})
            print(apis_responses)
            ia_response, prompt = generate_prompt(apis_responses, "GET")
            

        elif "POST" in request_type:
            print("Procesando solicitud POST")
            apis_responses = []
            
            for api, query in interpretation_json.items():
                if query != "N/A":
                    if api == "gmail":
                        result, status = process_gmail_chat(email, query, mongo, cache, refresh_functions)
                        apis_responses.append({"api": "gmail", "response": result})
                    elif api == "outlook":
                        result, status = process_outlook_chat(email, query, mongo, cache, refresh_functions)
                        apis_responses.append({"api": "outlook", "response": result})
                    elif api == "clickup":
                        result, status = process_clickup_chat(email, query, mongo, cache, refresh_functions)
                        apis_responses.append({"api": "clickup", "response": result})
                    elif api == "asana":
                        result, status = process_asana_chat(email, query, mongo, cache, refresh_functions)
                        apis_responses.append({"api": "asana", "response": result})
                    elif api == "dropbox":
                        result, status = process_dropbox_chat(email, query, mongo, cache, refresh_functions)
                        apis_responses.append({"api": "dropbox", "response": result})
                    elif api == "hubspot":
                        result, status = process_hubspot_chat(email, query, mongo, cache, refresh_functions)
                        apis_responses.append({"api": "hubspot", "response": result})
                    elif api == "notion":
                        result, status = process_notion_chat(email, query, mongo, cache, refresh_functions)
                        apis_responses.append({"api": "notion", "response": result})
                    elif api == "slack":
                        result, status = process_slack_chat(email, query, mongo, cache, refresh_functions)
                        apis_responses.append({"api": "slack", "response": result})
                    elif api == "onedrive":
                        result, status = process_onedrive_chat(email, query, mongo, cache, refresh_functions)
                        apis_responses.append({"api": "onedrive", "response": result})
                    elif api == "googledrive":
                        result, status = process_drive_chat(email, query, mongo, cache, refresh_functions)
                        apis_responses.append({"api": "googledrive", "response": result})
            ia_response = {"message": "Petición POST procesada", "apis": apis_responses}
            
        elif request_type == "Es una solicitud automatizada":
            ia_response = {"message": "Automatización procesada", "apis": [
                {"api": api, "response": f"Procesando {api}: Si {details['condition']}, entonces {details['action']}"}
                for api, details in interpretation_json.items() if details != "N/A"
            ]}

        elif request_type == "Es una solicitud múltiple":
            print(f"[INFO] Procesando solicitud múltiple: {interpretation_json}")
            ia_response = {"message": "Solicitud múltiple detectada", "apis": interpretation_json}

        else:
            ia_response = {"message": "Tipo de solicitud no reconocido", "interpretation": ia_interpretation}

        # Guardar mensajes en la base de datos (para no saludos ni INFO)
        if("GET" in request_type):
            assistant_message = {
            "role": "assistant",
            "content": prompt,
            "timestamp": datetime.utcnow().isoformat()
            }
            result = mongo.database.usuarios.update_one(
                {"correo": email, "chats.name": "Principal"},
                {"$push": {"chats.$.messages": {"$each": [user_message, assistant_message]}}}
            )
        else:
            assistant_message = {
                "role": "assistant",
                "content": json.dumps(ia_response) if isinstance(ia_response, dict) else ia_response,
                "timestamp": datetime.utcnow().isoformat()
            }
            result = mongo.database.usuarios.update_one(
                {"correo": email, "chats.name": "Principal"},
                {"$push": {"chats.$.messages": {"$each": [user_message, assistant_message]}}}
            )
        print(f"[INFO] Mensajes añadidos al chat Principal para {email}, matched: {result.matched_count}, modified: {result.modified_count}")

        return {"message": ia_response}, 200

    except Exception as e:
        print(f"[ERROR] Excepción en el procesamiento: {str(e)}")
        return {"message": f"¡Ay, caray! Algo se rompió: {str(e)} 😓"}, 500

def setup_chat(app, mongo, cache, refresh_functions):
    """Register general chat route."""
    cache = Cache(app)  # Ensure cache is initialized

    @app.route("/api/chatAi", methods=["POST"])
    def chatAi():
        data = request.get_json() or {}
        email = data.get("email") or request.args.get("email")
        user_query = None
        if "messages" in data and data["messages"]:
            user_query = data["messages"][-1].get("content", "").lower()
        result, status = process_chat(email, user_query, mongo, cache, refresh_functions)
        return jsonify(result), status

    return chatAi
