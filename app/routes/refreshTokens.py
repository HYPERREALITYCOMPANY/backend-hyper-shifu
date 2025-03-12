from flask import request, jsonify
import requests
import os
import datetime  # Para obtener la fecha actual
from dotenv import load_dotenv
from flask_caching import Cache
from app.utils.utils import get_user_from_db

# Cargar las variables de entorno desde el archivo .env
load_dotenv()

def setup_routes_refresh(app, mongo, cache):
    # Función para obtener las integraciones y refresh_tokens desde la base de datos
    def get_refresh_tokens_from_db(user_email):
        user_data = get_user_from_db(user_email, cache, mongo)
        if not user_data or "integrations" not in user_data:
            raise ValueError("El usuario no tiene integraciones guardadas en la base de datos.")
        
        integrations = user_data["integrations"]
        refresh_tokens = {}

        for integration_name, integration in integrations.items():
            # Solo incluir si existe el refresh_token y su valor no es "n/a"
            if "refresh_token" in integration and integration["refresh_token"] != "n/a":
                refresh_tokens[integration_name] = integration["refresh_token"]
        
        return refresh_tokens

    # Función para refrescar los tokens de las integraciones
    def refresh_tokens(integrations, user_email):
        refreshed_tokens = {}

        for integration_name, refresh_token in integrations.items():
            try:
                new_access_token = None

                if integration_name == "Gmail":
                    new_access_token = refresh_gmail_token(refresh_token)
                elif integration_name == "Dropbox":
                    new_access_token = refresh_dropbox_token(refresh_token)
                elif integration_name == "Asana":
                    new_access_token = refresh_asana_token(refresh_token)
                elif integration_name == "HubSpot":
                    new_access_token = refresh_hubspot_token(refresh_token)
                
                # Agregar más condiciones aquí para otras integraciones

                if new_access_token:
                    # Guardar el token actualizado en la base de datos (solo access_token)
                    save_access_token_to_db(user_email, integration_name, new_access_token)
                    refreshed_tokens[integration_name] = new_access_token

            except Exception as e:
                print(f"Error al refrescar el token de {integration_name}: {e}")

        return refreshed_tokens

    def save_access_token_to_db(user_email, integration_name, access_token):
        try:
            update_data = {
                f"integrations.{integration_name}.token": access_token,
                f"integrations.{integration_name}.timestamp": datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            }

            # Eliminar el caché del usuario antes de actualizar el token
            cache.delete(user_email)  # Borra el caché para que se recargue la información

            # Actualizar solo los campos token y timestamp en MongoDB
            mongo.database.usuarios.update_one(
                {"correo": user_email},
                {"$set": update_data}
            )
            
            print(f"Token de {integration_name} actualizado correctamente en la base de datos")
        except Exception as e:
            print(f"Error al actualizar el token en la base de datos: {e}")


    # Funciones para refrescar el token de cada integración
    def refresh_gmail_token(refresh_token):
        url = "https://oauth2.googleapis.com/token"
        data = {
            "client_id": os.getenv("GMAIL_CLIENT_ID"),
            "client_secret": os.getenv("GMAIL_CLIENT_SECRET"),
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }
        response = requests.post(url, data=data)
        response.raise_for_status()  # Lanza excepción si la respuesta es errónea
        return response.json()["access_token"]

    def refresh_dropbox_token(refresh_token):
        url = "https://api.dropboxapi.com/oauth2/token"
        data = {
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }
        response = requests.post(url, data=data)
        response.raise_for_status()
        return response.json()["access_token"]

    def refresh_asana_token(refresh_token):
        url = "https://app.asana.com/-/oauth_token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        }
        response = requests.post(url, data=data)
        response.raise_for_status()
        return response.json()["access_token"]

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

    # Endpoint para refrescar los tokens
    @app.route("/refresh_tokens", methods=["POST"])
    def refresh_tokens_endpoint():
        try:
            data = request.json
            user_email = data["userEmail"]
            # Obtenemos los refresh tokens de la base de datos (solo aquellos distintos de "n/a")
            integrations = get_refresh_tokens_from_db(user_email)
            # Refrescamos los tokens
            refreshed_tokens = refresh_tokens(integrations, user_email)

            return jsonify({"success": True, "refreshedTokens": refreshed_tokens}), 200
        except Exception as e:
            print(f"Error al refrescar los tokens: {e}")
            return jsonify({"success": False, "message": "Error al refrescar los tokens"}), 500


def get_user_from_db(email, cache, mongo):
    cached_user = cache.get(email)
    if cached_user:
        return cached_user  # Devuelve el usuario desde caché

    user = mongo.database.usuarios.find_one({'correo': email})
    if user:
        cache.set(email, user, timeout=1800)  # Guarda en caché por 30 minutos

    return user
