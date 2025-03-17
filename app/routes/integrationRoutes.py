from flask import request, jsonify
from datetime import datetime

def setup_integrations_routes(app, mongo):
    @app.route('/get_integrations', methods=['GET'])
    def get_integrations():
        user_email = request.args.get("email")
        if not user_email:
            return jsonify({"error": "Falta el campo 'email'"}), 400

        # Siempre consultamos MongoDB para obtener los datos más recientes
        user = mongo.database.usuarios.find_one({"correo": user_email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        # Actualizamos la caché con los datos más recientes de MongoDB
        cache.set(user_email, user, timeout=1800)  # Guarda en caché por 30 minutos

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

        if not all([user_email, integration_name, token, refresh_token]):
            return jsonify({"error": "Faltan campos obligatorios"}), 400

        # Obtener el usuario de MongoDB
        user = mongo.database.usuarios.find_one({"correo": user_email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        # Preparar los datos de la integración
        integration_data = {
            "token": token,
            "timestamp": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            "refresh_token": refresh_token
        }

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
        updated_user = mongo.database.usuarios.find_one({"correo": user_email})
        if not updated_user:
            return jsonify({"error": "Error al obtener el usuario actualizado"}), 500

        # Actualizar la caché con el usuario actualizado
        cache.set(user_email, updated_user, timeout=1800)  # Guarda en caché por 30 minutos
        print(f"Cache updated for user {user_email} with new integration {integration_name}")

        return jsonify({"message": "Integración añadida exitosamente"}), 200