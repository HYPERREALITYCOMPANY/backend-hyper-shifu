from flask import request, jsonify
import requests
import os
import datetime
from dotenv import load_dotenv
from flask_caching import Cache
from app.utils.utils import get_user_from_db

load_dotenv()

def setup_routes_refresh(app, mongo, cache):
    # Obtener refresh tokens desde la DB
    def get_refresh_tokens_from_db(user_email):
        user_data = get_user_from_db(user_email, cache, mongo)
        if not user_data or "integrations" not in user_data:
            raise ValueError("El usuario no tiene integraciones guardadas.")
        
        integrations = user_data["integrations"]
        refresh_tokens = {}
        for name, integration in integrations.items():
            if "refresh_token" in integration and integration["refresh_token"] != "n/a":
                refresh_tokens[name] = integration["refresh_token"]
        return refresh_tokens

    # Guardar token en la DB
    def save_access_token_to_db(user_email, integration_name, access_token):
        try:
            update_data = {
                f"integrations.{integration_name}.token": access_token,
                f"integrations.{integration_name}.timestamp": datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            }
            cache.delete(user_email)
            mongo.database.usuarios.update_one(
                {"correo": user_email},
                {"$set": update_data}
            )
            print(f"Token de {integration_name} actualizado en DB")
        except Exception as e:
            print(f"Error al actualizar token en DB para {integration_name}: {e}")
            raise

    # Métodos de refresco por integración
    def refresh_gmail_token(refresh_token):
        url = "https://oauth2.googleapis.com/token"
        data = {
            "client_id": os.getenv("GMAIL_CLIENT_ID"),
            "client_secret": os.getenv("GMAIL_CLIENT_SECRET"),
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }
        response = requests.post(url, data=data)
        response.raise_for_status()
        return response.json()["access_token"]

    def refresh_dropbox_token(refresh_token):
        url = "https://api.dropboxapi.com/oauth2/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": os.getenv("DROPBOX_CLIENT_ID"),
            "client_secret": os.getenv("DROPBOX_CLIENT_SECRET")
        }
        response = requests.post(url, data=data)
        response.raise_for_status()
        return response.json()["access_token"]

    def refresh_asana_token(refresh_token):
        url = "https://app.asana.com/-/oauth_token"  # URL corregida
        data = {
            "grant_type": "refresh_token",
            "client_id": os.getenv("ASANA_CLIENT_ID"),
            "client_secret": os.getenv("ASANA_CLIENT_SECRET"),
            "refresh_token": refresh_token
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        
        try:
            response = requests.post(url, data=data, headers=headers)
            print(f"Respuesta de Asana (status: {response.status_code}): {response.text}")  # Depuración
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
        response = requests.post(url, data=data)
        response.raise_for_status()
        return response.json()["access_token"]

    def refresh_drive_token(refresh_token):
        url = "https://oauth2.googleapis.com/token"
        data = {
            "client_id": os.getenv("DRIVE_CLIENT_ID"),
            "client_secret": os.getenv("DRIVE_CLIENT_SECRET"),
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }
        response = requests.post(url, data=data)
        response.raise_for_status()
        return response.json()["access_token"]

    # Lógica de refresco
    def refresh_tokens(integrations, user_email, integration_name=None):
        refreshed_tokens = {}
        errors = {}
        target_integrations = {integration_name: integrations[integration_name]} if integration_name else integrations

        for name, refresh_token in target_integrations.items():
            try:
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
                    save_access_token_to_db(user_email, name, new_access_token)
                    refreshed_tokens[name] = new_access_token
                else:
                    errors[name] = "No se obtuvo nuevo token"
                    print(f"No se obtuvo nuevo token para {name}")
            except Exception as e:
                errors[name] = str(e)
                print(f"Error al refrescar token de {name}: {e}")
        
        return refreshed_tokens, errors

    # Endpoint
    @app.route("/refresh_tokens", methods=["POST"])
    def refresh_tokens_endpoint():
        try:
            data = request.json
            user_email = data.get("userEmail")
            integration_name = data.get("integrationName")
            if not user_email:
                return jsonify({"success": False, "message": "Falta userEmail"}), 400

            integrations = get_refresh_tokens_from_db(user_email)
            refreshed_tokens, errors = refresh_tokens(integrations, user_email, integration_name)

            if errors and not refreshed_tokens:
                return jsonify({"success": False, "message": "Fallaron todas las actualizaciones", "errors": errors}), 500
            elif errors:
                return jsonify({"success": True, "refreshedTokens": refreshed_tokens, "errors": errors}), 207  # Multi-Status
            return jsonify({"success": True, "refreshedTokens": refreshed_tokens}), 200
        except ValueError as ve:
            return jsonify({"success": False, "message": str(ve)}), 404
        except Exception as e:
            print(f"Error en refresh_tokens_endpoint: {e}")
            return jsonify({"success": False, "message": "Error al refrescar tokens"}), 500