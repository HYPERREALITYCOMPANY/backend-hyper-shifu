from flask import request, jsonify
import requests
import os
import datetime
from dotenv import load_dotenv

load_dotenv()

def setup_routes_refresh(app, mongo, cache):
    # Configuración de servicios soportados con sus endpoints y credenciales
    SERVICE_CONFIG = {
        "Gmail": {
            "url": "https://oauth2.googleapis.com/token",
            "client_id": os.getenv("GMAIL_CLIENT_ID"),
            "client_secret": os.getenv("GMAIL_CLIENT_SECRET"),
        },
        "Dropbox": {
            "url": "https://api.dropboxapi.com/oauth2/token",
            "client_id": os.getenv("DROPBOX_CLIENT_ID"),
            "client_secret": os.getenv("DROPBOX_CLIENT_SECRET"),
        },
        "Asana": {
            "url": "https://app.asana.com/-/oauth_token",
            "client_id": os.getenv("ASANA_CLIENT_ID"),
            "client_secret": os.getenv("ASANA_CLIENT_SECRET"),
            "headers": {"Content-Type": "application/x-www-form-urlencoded"},
        },
        "HubSpot": {
            "url": "https://api.hubapi.com/oauth/v1/token",
            "client_id": os.getenv("HUBSPOT_CLIENT_ID"),
            "client_secret": os.getenv("HUBSPOT_CLIENT_SECRET"),
        },
        "Drive": {
            "url": "https://oauth2.googleapis.com/token",
            "client_id": os.getenv("DRIVE_CLIENT_ID"),
            "client_secret": os.getenv("DRIVE_CLIENT_SECRET"),
        },
    }

    def get_refresh_tokens_from_db(user_email):
        """Obtiene los refresh tokens desde la caché o MongoDB."""
        cache_key = f"refresh_tokens_{user_email}"
        cached_tokens = cache.get(cache_key)
        if cached_tokens is not None:
            print(f"[INFO] Tokens obtenidos de caché para {user_email}")
            return cached_tokens

        user_data = mongo.database.usuarios.find_one({"correo": user_email}, {"integrations": 1})
        if not user_data or "integrations" not in user_data:
            raise ValueError("El usuario no tiene integraciones guardadas.")

        integrations = user_data["integrations"]
        refresh_tokens = {
            name: integration["refresh_token"]
            for name, integration in integrations.items()
            if "refresh_token" in integration and integration["refresh_token"] != "n/a"
        }
        cache.set(cache_key, refresh_tokens, timeout=1800)  # Cache por 30 min
        print(f"[INFO] Tokens obtenidos de MongoDB y cacheados para {user_email}: {refresh_tokens.keys()}")
        return refresh_tokens

    def save_access_token_to_db(user_email, integration_name, access_token):
        """Actualiza el token en MongoDB y la caché en una sola operación."""
        try:
            update_data = {
                f"integrations.{integration_name}.token": access_token,
                f"integrations.{integration_name}.timestamp": datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            }
            result = mongo.database.usuarios.update_one(
                {"correo": user_email},
                {"$set": update_data},
                upsert=False
            )
            if result.matched_count == 0:
                raise ValueError("No se encontró el usuario para actualizar el token")

            # Invalidar la caché del usuario para que se recargue con los nuevos datos
            cache.delete(user_email)
            print(f"[INFO] Token de {integration_name} actualizado para {user_email}. Modificados: {result.modified_count}")
            return True
        except Exception as e:
            print(f"[ERROR] Error al actualizar token en DB para {integration_name}: {e}")
            raise

    def refresh_token(service, refresh_token):
        """Función genérica para refrescar tokens de cualquier servicio."""
        config = SERVICE_CONFIG.get(service)
        if not config:
            raise ValueError(f"Servicio {service} no soportado para refresco")

        cache_key = f"access_token_{service}_{refresh_token[:10]}"  # Usamos parte del refresh token como clave
        cached_access_token = cache.get(cache_key)
        if cached_access_token:
            print(f"[INFO] Usando token de acceso cacheado para {service}")
            return cached_access_token

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": config["client_id"],
            "client_secret": config["client_secret"]
        }
        headers = config.get("headers", {})
        try:
            response = requests.post(config["url"], data=data, headers=headers, timeout=10)
            response.raise_for_status()
            response_json = response.json()
            access_token = response_json.get("access_token")
            if not access_token:
                raise ValueError(f"No se encontró 'access_token' en la respuesta: {response_json}")
            cache.set(cache_key, access_token, timeout=3600)  # Cache por 1 hora
            print(f"[INFO] Token refrescado para {service}: {response.status_code}")
            return access_token
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Error en solicitud para {service}: {e}")
            raise
        except ValueError as ve:
            print(f"[ERROR] Error procesando respuesta de {service}: {ve}")
            raise

    def refresh_tokens(integrations, user_email, integration_name=None):
        """Refresca tokens para las integraciones especificadas."""
        refreshed_tokens = {}
        errors = {}
        target_integrations = {integration_name: integrations[integration_name]} if integration_name else integrations

        for name, refresh_token in target_integrations.items():
            if name not in SERVICE_CONFIG:
                print(f"[INFO] Ignorando {name}: no soportado para refresco")
                continue
            try:
                print(f"[INFO] Refrescando token para {name}")
                new_access_token = refresh_token(name, refresh_token)
                save_access_token_to_db(user_email, name, new_access_token)
                refreshed_tokens[name] = new_access_token
            except Exception as e:
                errors[name] = str(e)
                print(f"[ERROR] Fallo al refrescar token de {name}: {e}")

        return refreshed_tokens, errors

    @app.route("/refresh_tokens", methods=["POST"])
    def refresh_tokens_endpoint():
        """Endpoint para refrescar tokens manualmente."""
        try:
            data = request.json
            user_email = data.get("userEmail")
            integration_name = data.get("integrationName")
            if not user_email:
                return jsonify({"success": False, "message": "Falta userEmail"}), 400

            integrations = get_refresh_tokens_from_db(user_email)
            if not integrations:
                return jsonify({"success": False, "message": "No se encontraron refresh tokens"}), 404

            refreshed_tokens, errors = refresh_tokens(integrations, user_email, integration_name)

            if errors and not refreshed_tokens:
                return jsonify({"success": False, "message": "Fallaron todas las actualizaciones", "errors": errors}), 500
            elif errors:
                return jsonify({"success": True, "refreshedTokens": refreshed_tokens, "errors": errors}), 207
            return jsonify({"success": True, "refreshedTokens": refreshed_tokens}), 200
        except ValueError as ve:
            return jsonify({"success": False, "message": str(ve)}), 404
        except Exception as e:
            print(f"[ERROR] Error en endpoint /refresh_tokens: {e}")
            return jsonify({"success": False, "message": "Error al refrescar los tokens"}), 500

    return {
        "refresh_tokens": refresh_tokens,
        "save_access_token_to_db": save_access_token_to_db,
        "get_refresh_tokens_from_db": get_refresh_tokens_from_db
    }