from flask import request, jsonify
from datetime import datetime
from app.utils.utils import get_user_from_db
from flask_caching import Cache

def setup_integrations_routes(app, mongo, cache):
    cache = Cache(app)

    @app.route('/get_integrations', methods=['GET'])
    def get_integrations():
        user_email = request.args.get("email")
        
        user = get_user_from_db(user_email, cache, mongo)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        # Devolvemos las integraciones que tiene el usuario
        return jsonify({"integrations": user.get("integrations", {})}), 200

    @app.route('/add_integration', methods=['POST'])
    def add_integration():
        request_data = request.get_json()
        user_email = request_data.get("email")
        integration_name = request_data.get("integration")
        token = request_data.get("token")
        refresh_token = request_data.get("refresh_token")
        expires_in = request_data.get("expires_in")

        # Validar campos obligatorios
        if not all([user_email, integration_name, token, refresh_token]):
            return jsonify({"error": "Faltan campos obligatorios"}), 400

        # Obtener el usuario
        user = get_user_from_db(user_email, cache, mongo)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        # Preparar los datos de la integración
        integration_data = {
            "token": token,
            "timestamp": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            "refresh_token": refresh_token
        }

        # Validar expires_in para integraciones que lo requieren
        if integration_name not in ["Notion", "Slack", "ClickUp"]:
            if expires_in is None:
                return jsonify({"error": "El campo 'expires_in' es obligatorio para esta integración"}), 400
            integration_data["expires_in"] = int(expires_in)

        # Actualizar el usuario en MongoDB
        mongo.database.usuarios.update_one(
            {"correo": user_email},
            {"$set": {f"integrations.{integration_name}": integration_data}}
        )

        # Obtener el usuario actualizado de MongoDB
        updated_user = mongo.database.usuarios.find_one({'correo': user_email})
        if not updated_user:
            return jsonify({"error": "Error al obtener el usuario actualizado"}), 500

        # Actualizar la caché con el usuario actualizado
        cache.set(user_email, updated_user, timeout=1800)  # Guarda en caché por 30 minutos
        print(f"Cache updated for user {user_email} with new integration {integration_name}")

        return jsonify({"message": "Integración añadida exitosamente"}), 200

def get_user_from_db(email, cache, mongo):
    cached_user = cache.get(email)
    if cached_user:
        print("User found in cache!")
        return cached_user  # Devuelve el usuario desde caché

    print("User not found in cache, querying MongoDB...")
    user = mongo.database.usuarios.find_one({'correo': email})
    if user:
        print("User found in MongoDB, saving to cache...")
        cache.set(email, user, timeout=1800)  # Guarda en caché por 30 minutos

    return user