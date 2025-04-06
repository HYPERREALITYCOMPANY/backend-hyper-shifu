from flask import request, jsonify
from datetime import datetime, timedelta
from config import Config
import json
import openai
import re
from .system_prompt import system_prompt_multi
openai.api_key = Config.CHAT_API_KEY
from app.utils.utils import get_user_from_db
from flask_caching import Cache

def setup_routes_multitasks(app, mongo, cache, refresh_functions):
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

    @app.route("/api/multitask", methods=["POST"])
    def api_multitask():
        data = request.get_json()
        email = data.get("email")  # Obtenemos el email del JSON
        if not email:
            email = request.args.get("email")  # Fallback a query param
        multitask_data = data.get("multitask_data", {})

        if not email:
            return jsonify({"error": "Email del usuario es requerido"}), 400

        if not multitask_data:
            return jsonify({"error": "Datos de la solicitud múltiple son requeridos"}), 400

        # Obtenemos el usuario con tokens refrescados
        user = get_user_with_refreshed_tokens(email)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        try:
            response = openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt_multi},
                    {"role": "user", "content": json.dumps(multitask_data)}
                ],
                max_tokens=1000
            )
            ordered_operations_str = response.choices[0].message.content.strip()
            print(f"[INFO] Operaciones ordenadas: {ordered_operations_str}")

            # Parseamos el JSON de las operaciones ordenadas
            ordered_operations = json.loads(ordered_operations_str)

            # Procesamos las operaciones según las APIs involucradas
            for operation in ordered_operations:
                api = operation.get("api")
                intention = operation.get("intention")
                op_type = operation.get("type")

                if api == "gmail":
                    print(f"[GMAIL] {op_type}: {intention}")
                elif api == "outlook":
                    print(f"[OUTLOOK] {op_type}: {intention}")
                elif api == "clickup":
                    print(f"[CLICKUP] {op_type}: {intention}")
                elif api == "asana":
                    print(f"[ASANA] {op_type}: {intention}")
                elif api == "notion":
                    print(f"[NOTION] {op_type}: {intention}")
                elif api == "hubspot":
                    print(f"[HUBSPOT] {op_type}: {intention}")
                elif api == "slack":
                    print(f"[SLACK] {op_type}: {intention}")
                elif api == "teams":
                    print(f"[TEAMS] {op_type}: {intention}")
                elif api == "googledrive":
                    print(f"[GOOGLEDRIVE] {op_type}: {intention}")
                elif api == "onedrive":
                    print(f"[ONEDRIVE] {op_type}: {intention}")
                elif api == "dropbox":
                    print(f"[DROPBOX] {op_type}: {intention}")
                elif op_type == "error":
                    print(f"[ERROR] {api}: {intention} - {operation.get('message')}")

            # Respuesta temporal
            ia_response = {
                "message": "Solicitud múltiple procesada",
                "operations": ordered_operations
            }

        except Exception as e:
            print(f"[ERROR] Error al procesar solicitud múltiple: {str(e)}")
            ia_response = {"error": f"Error al procesar solicitud múltiple: {str(e)}"}

        return jsonify(ia_response)