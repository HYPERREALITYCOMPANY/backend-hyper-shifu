from flask import request, jsonify
from datetime import datetime

def setup_integrations_routes(app, mongo):
    @app.route('/get_integrations', methods=['GET'])
    def get_integrations():
        user_email = request.args.get("email")
        
        user = mongo.database.usuarios.find_one({"correo": user_email})
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
        refresh_token = request_data.get("refresh_token")  # Recibimos el refresh_token
        expires_in = request_data.get("expires_in")

        if not all([user_email, integration_name, token]):
            return jsonify({"error": "Faltan campos obligatorios"}), 400
        
        # Si la integración no es Notion ni ClickUp, el refresh_token es obligatorio
        if integration_name not in ["Notion", "ClickUp"] and not refresh_token:
            return jsonify({"error": "El campo 'refresh_token' es obligatorio para esta integración"}), 400

        user = mongo.database.usuarios.find_one({"correo": user_email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        # Crear el diccionario de datos de integración
        integration_data = {
            "token": token,
            "timestamp": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        }

        # Si la integración no es Notion ni ClickUp, añadimos refresh_token y expires_in
        if integration_name not in ["Notion", "ClickUp"]:
            integration_data["refresh_token"] = refresh_token  # Añadimos el refresh_token
            if expires_in is None:
                return jsonify({"error": "El campo 'expires_in' es obligatorio para esta integración"}), 400
            integration_data["expires_in"] = int(expires_in)

        # Actualizamos la base de datos con los datos de integración
        mongo.database.usuarios.update_one(
            {"correo": user_email},
            {"$set": {f"integrations.{integration_name}": integration_data}}
        )

        return jsonify({"message": "Integración añadida exitosamente"}), 200

