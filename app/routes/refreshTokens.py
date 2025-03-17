from flask import request, jsonify
import requests
import os
import datetime
from dotenv import load_dotenv

load_dotenv()

def setup_routes_refresh(app, mongo, cache):
    cache2 = Cache(app)

    def get_refresh_tokens_from_db(user_email):
        user_data = mongo.database.usuarios.find_one({"correo": user_email})
        if not user_data or "integrations" not in user_data:
            raise ValueError("El usuario no tiene integraciones guardadas.")
        
        integrations = user_data["integrations"]
        refresh_tokens = {}
        for name, integration in integrations.items():
            if "refresh_token" in integration and integration["refresh_token"] != "n/a":
                refresh_tokens[name] = integration["refresh_token"]
        print(f"Refresh tokens encontrados para {user_email}: {refresh_tokens}")
        return refresh_tokens

    def save_access_token_to_db(user_email, integration_name, access_token):
        try:
            update_data = {
                f"integrations.{integration_name}.token": access_token,
                f"integrations.{integration_name}.timestamp": datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            }
            # Eliminar la caché anterior
            cache2.delete(user_email)
            # Actualizar MongoDB
            result = mongo.database.usuarios.update_one(
                {"correo": user_email},
                {"$set": update_data}
            )
            if result.matched_count == 0:
                raise ValueError("No se encontró el usuario para actualizar el token")
            
            print(f"Token de {integration_name} actualizado en DB para {user_email}")
            # Obtener el usuario actualizado de MongoDB
            updated_user = mongo.database.usuarios.find_one({"correo": user_email})
            if not updated_user:
                raise ValueError("No se pudo obtener el usuario actualizado después de la operación")

            # Actualizar la caché con el usuario actualizado
            cache2.set(user_email, updated_user, timeout=1800)  # Guarda en caché por 30 minutos
            print(f"Cache updated for user {user_email} with refreshed token for {integration_name}")
            return updated_user

        except Exception as e:
            print(f"Error al actualizar token en DB para {integration_name}: {e}")
            raise

    def refresh_gmail_token(refresh_token):
        url = "https://oauth2.googleapis.com/token"
        data = {
            "client_id": os.getenv("GMAIL_CLIENT_ID"),
            "client_secret": os.getenv("GMAIL_CLIENT_SECRET"),
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
        print(f"Gmail token refresh response: {response.status_code} {response.text}")
        return response.json()["access_token"]

    def refresh_dropbox_token(refresh_token):
        url = "https://api.dropboxapi.com/oauth2/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": os.getenv("DROPBOX_CLIENT_ID"),
            "client_secret": os.getenv("DROPBOX_CLIENT_SECRET")
        }
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
        print(f"Dropbox token refresh response: {response.status_code} {response.text}")
        return response.json()["access_token"]

    def refresh_asana_token(refresh_token):
        url = "https://app.asana.com/-/oauth_token"
        data = {
            "grant_type": "refresh_token",
            "client_id": os.getenv("ASANA_CLIENT_ID"),
            "client_secret": os.getenv("ASANA_CLIENT_SECRET"),
            "refresh_token": refresh_token
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        
        try:
            response = requests.post(url, data=data, headers=headers, timeout=10)
            print(f"Asana token refresh response: {response.status_code} {response.text}")
            response.raise_for_status()
            
            response_json = response.json()
            access_token = response_json.get("access_token")
            if not access_token:
                raise ValueError(f"No se encontró 'access_token' en la respuesta: {response_json}")
            return access_token
        except requests.exceptions.RequestException as e:
            print(f"Error en la solicitud a Asana: {e}")
            raise
        except ValueError as ve:
            print(f"Error procesando respuesta de Asana: {ve}")
            raise

    def refresh_hubspot_token(refresh_token):
        url = "https://api.hubapi.com/oauth/v1/token"
        data = {
            "grant_type": "refresh_token",
            "client_id": os.getenv("HUBSPOT_CLIENT_ID"),
            "client_secret": os.getenv("HUBSPOT_CLIENT_SECRET"),
            "refresh_token": refresh_token
        }
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
        print(f"HubSpot token refresh response: {response.status_code} {response.text}")
        return response.json()["access_token"]

    def refresh_drive_token(refresh_token):
        url = "https://oauth2.googleapis.com/token"
        data = {
            "client_id": os.getenv("DRIVE_CLIENT_ID"),
            "client_secret": os.getenv("DRIVE_CLIENT_SECRET"),
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
        print(f"Drive token refresh response: {response.status_code} {response.text}")
        return response.json()["access_token"]

    def refresh_tokens(integrations, user_email, integration_name=None):
        refreshed_tokens = {}
        errors = {}
        target_integrations = {integration_name: integrations[integration_name]} if integration_name else integrations

        supported_integrations = ["Gmail", "Dropbox", "Asana", "HubSpot", "Drive"]

        for name, refresh_token in target_integrations.items():
            if name not in supported_integrations:
                print(f"Ignorando {name}: no es una integración soportada para refresco")
                continue

            try:
                print(f"Intentando refrescar token para {name} con refresh_token: {refresh_token[:5]}...")  # Mostrar solo parte por seguridad
                new_access_token = None
                if name == "Gmail":
                    new_access_token = refresh_gmail_token(refresh_token)
                elif name == "Dropbox":
                    new_access_token = refresh_dropbox_token(refresh_token)
                elif name == "Asana":
                    new_access_token = refresh_asana_token(refresh_token)
                elif name == "HubSpot":
                    new_access_token = refresh_hubspot_token(refresh_token)
                elif name == "Drive":
                    new_access_token = refresh_drive_token(refresh_token)

                if new_access_token:
                    updated_user = save_access_token_to_db(user_email, name, new_access_token)
                    refreshed_tokens[name] = new_access_token
                else:
                    errors[name] = "No se obtuvo nuevo token"
                    print(f"No se obtuvo nuevo token para {name}")
            except Exception as e:
                errors[name] = str(e)
                print(f"Error al refrescar token de {name}: {e}")

        return refreshed_tokens, errors

    @app.route("/refresh_tokens", methods=["POST"])
    def refresh_tokens_endpoint():
        try:
            data = request.json
            user_email = data.get("userEmail")
            integration_name = data.get("integrationName")
            if not user_email:
                return jsonify({"success": False, "message": "Falta userEmail"}), 400

            integrations = get_refresh_tokens_from_db(user_email)
            if not integrations:
                return jsonify({"success": False, "message": "No se encontraron refresh tokens para este usuario"}), 404

            refreshed_tokens, errors = refresh_tokens(integrations, user_email, integration_name)

            if errors and not refreshed_tokens:
                return jsonify({"success": False, "message": "Fallaron todas las actualizaciones", "errors": errors}), 500
            elif errors:
                return jsonify({"success": True, "refreshedTokens": refreshed_tokens, "errors": errors}), 207  # Multi-Status
            return jsonify({"success": True, "refreshedTokens": refreshed_tokens}), 200
        except ValueError as ve:
            return jsonify({"success": False, "message": str(ve)}), 404
        except Exception as e:
            print(f"Error al refrescar los tokens: {e}")
            return jsonify({"success": False, "message": "Error al refrescar los tokens"}), 500
            print(f"Error en refresh_tokens_endpoint: {e}")
            return jsonify({"success": False, "message": "Error al refrescar tokens"}), 500

    return {
        "refresh_tokens": refresh_tokens,
        "save_access_token_to_db": save_access_token_to_db,
        "get_refresh_tokens_from_db": get_refresh_tokens_from_db
    }
