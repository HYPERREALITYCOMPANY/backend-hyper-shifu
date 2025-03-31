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

def setup_routes_chats(app, mongo, cache, refresh_functions):
    cache = Cache(app)
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

    @app.route("/api/chatAi", methods=["POST"])
    def apiChat():
        data = request.get_json()
        email = data.get("email")  # Obtenemos el email del JSON
        if not email:
            email = request.args.get("email")  # Fallback a query param
        user_messages = data.get("messages", [])

        if not email:
            return jsonify({"error": "Email del usuario es requerido"}), 400

        # Obtenemos el usuario con tokens refrescados
        user = get_user_with_refreshed_tokens(email)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404
        
        print(f"[DEBUG] Usuario cargado inicialmente: {user}")

        # Aseguramos que el usuario tenga un campo 'chats' con "Principal"
        if "chats" not in user or not any(chat["name"] == "Principal" for chat in user.get("chats", [])):
            print(f"[INFO] El usuario {email} no tiene chat 'Principal', inicializando")
            result = mongo.database.usuarios.update_one(
                {"correo": email},
                {"$set": {"chats": [{"name": "Principal", "messages": []}]}} if "chats" not in user else {"$push": {"chats": {"name": "Principal", "messages": []}}},
                upsert=True
            )
            print(f"[DEBUG] Inicialización de chats, matched: {result.matched_count}, modified: {result.modified_count}")
            # Recargamos el usuario desde la DB
            user = mongo.database.usuarios.find_one({"correo": email})
            print(f"[DEBUG] Usuario tras inicializar Principal: {user}")

        # Buscamos el chat "Principal" (ahora debería existir)
        principal_chat = next((chat for chat in user["chats"] if chat["name"] == "Principal"), None)
        if not principal_chat:
            print(f"[ERROR] No se encontró el chat 'Principal' después de inicializar para {email}")
            return jsonify({"error": "Error interno al inicializar el chat"}), 500
        print(f"[INFO] Mensajes previos en Principal: {len(principal_chat['messages'])}")

        # Añadimos el nuevo mensaje del usuario al historial con timestamp
        if user_messages:
            last_message = user_messages[-1].get("content", "").lower()
            timestamp = datetime.utcnow().isoformat()
            user_message = {"role": "user", "content": last_message, "timestamp": timestamp}

            try:
                # Filtramos mensajes de los últimos 3 días por defecto
                three_days_ago = datetime.utcnow() - timedelta(days=3)
                filtered_messages = [
                    msg for msg in principal_chat["messages"]
                    if datetime.fromisoformat(msg["timestamp"]) >= three_days_ago
                ]

                # Detectamos si el usuario pide un contexto mayor
                context_keywords = ["semana", "hace días", "hace una semana", "mes", "año", "hace tiempo"]
                use_full_history = any(keyword in last_message for keyword in context_keywords)

                if use_full_history:
                    print(f"[INFO] Detectado contexto mayor a 3 días en '{last_message}', usando historial completo")
                    filtered_messages = principal_chat["messages"]

                print(f"[INFO] Mensajes enviados al contexto: {len(filtered_messages)} de {len(principal_chat['messages'])} totales")

                # Creamos el prompt con el historial filtrado o completo
                prompt = f"Interpreta la query del usuario: {last_message}"
                response = openai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
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

                # Añadimos los mensajes al chat "Principal" en la DB
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

                # Recargamos el usuario para confirmar
                user = mongo.database.usuarios.find_one({"correo": email})
                print(f"[DEBUG] Usuario tras actualizar mensajes: {user}")

                # Manejo según el tipo de solicitud
                if "saludo" in request_type.lower():
                    prompt_greeting = f"Usuario: {last_message}\nResponde de manera cálida y amigable, con emojis."
                    response_greeting = openai.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "system", "content": "Eres un asistente amigable."}, {"role": "user", "content": prompt_greeting}],
                        max_tokens=150
                    )
                    ia_response = response_greeting.choices[0].message.content.strip()

                elif "GET" in request_type:
                    print("Procesando solicitud GET")
                    if interpretation_json.get("gmail") != "N/A":
                        print("Gmail respondió:", interpretation_json["gmail"])
                    if interpretation_json.get("outlook") != "N/A":
                        print("Outlook respondió:", interpretation_json["outlook"])
                    if interpretation_json.get("clickup") != "N/A":
                        print("ClickUp respondió:", interpretation_json["clickup"])
                    if interpretation_json.get("asana") != "N/A":
                        print("Asana respondió:", interpretation_json["asana"])
                    if interpretation_json.get("notion") != "N/A":
                        print("Notion respondió:", interpretation_json["notion"])
                    if interpretation_json.get("hubspot") != "N/A":
                        print("HubSpot respondió:", interpretation_json["hubspot"])
                    if interpretation_json.get("slack") != "N/A":
                        print("Slack respondió:", interpretation_json["slack"])
                    if interpretation_json.get("teams") != "N/A":
                        print("Teams respondió:", interpretation_json["teams"])
                    if interpretation_json.get("googledrive") != "N/A":
                        print("Google Drive respondió:", interpretation_json["googledrive"])
                    if interpretation_json.get("onedrive") != "N/A":
                        print("OneDrive respondió:", interpretation_json["onedrive"])
                    if interpretation_json.get("dropbox") != "N/A":
                        print("Dropbox respondió:", interpretation_json["dropbox"])
                    if interpretation_json.get("googlecalendar") != "N/A":
                        print("Google Calendar respondió:", interpretation_json["googlecalendar"])
                    ia_response = {"message": "Petición GET procesada", "apis": [
                        {"api": api, "response": f"Obteniendo datos de {api}: {query}"}
                        for api, query in interpretation_json.items() if query != "N/A"
                    ]}

                elif "POST" in request_type:
                    print("Procesando solicitud POST")
                    if interpretation_json.get("gmail") != "N/A":
                        print("Gmail respondió:", interpretation_json["gmail"])
                    if interpretation_json.get("outlook") != "N/A":
                        print("Outlook respondió:", interpretation_json["outlook"])
                    if interpretation_json.get("clickup") != "N/A":
                        print("ClickUp respondió:", interpretation_json["clickup"])
                    if interpretation_json.get("asana") != "N/A":
                        print("Asana respondió:", interpretation_json["asana"])
                    if interpretation_json.get("notion") != "N/A":
                        print("Notion respondió:", interpretation_json["notion"])
                    if interpretation_json.get("hubspot") != "N/A":
                        print("HubSpot respondió:", interpretation_json["hubspot"])
                    if interpretation_json.get("slack") != "N/A":
                        print("Slack respondió:", interpretation_json["slack"])
                    if interpretation_json.get("teams") != "N/A":
                        print("Teams respondió:", interpretation_json["teams"])
                    if interpretation_json.get("googledrive") != "N/A":
                        print("Google Drive respondió:", interpretation_json["googledrive"])
                    if interpretation_json.get("onedrive") != "N/A":
                        print("OneDrive respondió:", interpretation_json["onedrive"])
                    if interpretation_json.get("dropbox") != "N/A":
                        print("Dropbox respondió:", interpretation_json["dropbox"])
                    if interpretation_json.get("googlecalendar") != "N/A":
                        print("Google Calendar respondió:", interpretation_json["googlecalendar"])
                    ia_response = {"message": "Petición POST procesada", "apis": [
                        {"api": api, "response": f"Ejecutando acción en {api}: {query}"}
                        for api, query in interpretation_json.items() if query != "N/A"
                    ]}

                elif request_type == "Es una solicitud INFO":
                    ia_response = {"message": "Información de capacidades", "capabilities": interpretation_json["capabilities"]}

                elif request_type == "Es una solicitud automatizada":
                    ia_response = {"message": "Automatización procesada", "apis": [
                        {"api": api, "response": f"Procesando {api}: Si {details['condition']}, entonces {details['action']}"}
                        for api, details in interpretation_json.items()
                    ]}

                elif request_type == "Se refiere a la respuesta anterior":
                    api_responses = [
                        {"api": api, "response": f"Procesando con contexto en {api}: {query} (basado en la respuesta anterior)"}
                        for api, query in interpretation_json.items() if query != "N/A"
                    ]
                    ia_response = {"message": "Petición con contexto procesada", "apis": api_responses} if api_responses else "No hay suficiente contexto de la respuesta anterior para procesar esta petición."

            except Exception as e:
                ia_response = f"Error: {str(e)}"
        else:
            ia_response = "No se proporcionó ningún mensaje."

        return jsonify(ia_response)

    def extract_links_from_datas(datas):
        """Extrae los enlaces y los nombres (asunto/página/mensaje/nombre de archivo) de cada API según la estructura de datos recibida."""
        results = {
            'gmail': [], 'slack': [], 'notion': [], 'outlook': [], 'clickup': [], 'hubspot': [],
            'dropbox': [], 'asana': [], 'onedrive': [], 'teams': [], 'googledrive': []
        }

        if isinstance(datas.get('gmail'), list):
            results['gmail'] = [
                {'link': item['link'], 'subject': item.get('subject', 'No subject')} 
                for item in datas['gmail'] if 'link' in item
            ]
        
        if isinstance(datas.get('slack'), list):
            results['slack'] = [
                {'link': item['link'], 'message': item.get('message', 'No message')} 
                for item in datas['slack'] if 'link' in item
            ]
        
        if isinstance(datas.get('notion'), list):
            results['notion'] = [
                {'url': item['url'], 'page_name': item.get('properties', {}).get('Nombre', 'Sin Nombre')} 
                for item in datas['notion'] if 'url' in item
            ]
        
        if isinstance(datas.get('outlook'), list):
            results['outlook'] = [
                {'webLink': item['webLink'], 'subject': item.get('subject', 'No subject')} 
                for item in datas['outlook'] if 'webLink' in item
            ]
        
        if isinstance(datas.get("clickup"), list):
            results['clickup'] = [
                {'url': item['url'], 'task_name': item.get('task_name', 'Sin Nombre')} 
                for item in datas["clickup"] if 'url' in item
            ]
        
        if isinstance(datas.get("dropbox"), list):
            results['dropbox'] = [
                {'url': item['download_link'], 'name': item.get('name', 'Sin Nombre')} 
                for item in datas["dropbox"] if 'download_link' in item
            ]
        
        if isinstance(datas.get("onedrive"), list):
            results['onedrive'] = [
                {'url': item['url'], 'name': item.get('name', 'Sin Nombre')} 
                for item in datas["onedrive"] if 'url' in item
            ]
        
        if isinstance(datas.get("asana"), list):
            results['asana'] = [
                {'url': item['url'], 'task_name': item.get('name', 'Sin Nombre')} 
                for item in datas["asana"] if 'url' in item
            ]
        
        if isinstance(datas.get("googledrive"), list):
            results['googledrive'] = [
                {'url': item['url'], 'name': item.get('name', 'Sin Nombre')} 
                for item in datas["googledrive"] if 'url' in item
            ]
        
        return results