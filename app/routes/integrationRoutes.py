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
        refresh_token = request_data.get("refresh_token")
        expires_in = request_data.get("expires_in")

        # Verificamos que se hayan enviado todos los campos obligatorios
        if not all([user_email, integration_name, token, refresh_token, expires_in]):
            return jsonify({"error": "Faltan campos obligatorios: email, integration, token, refresh_token y expires_in"}), 400

        user = mongo.database.usuarios.find_one({"correo": user_email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        # Creamos el diccionario de datos de integración con token, refresh_token, expires_in y la fecha actual
        integration_data = {
            "token": token,
            "refresh_token": refresh_token,
            "expires_in": int(expires_in),
            "timestamp": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        }

        # Actualizamos la base de datos sobrescribiendo la integración
        mongo.database.usuarios.update_one(
            {"correo": user_email},
            {"$set": {f"integrations.{integration_name}": integration_data}}
        )

        return jsonify({"message": "Integración añadida exitosamente"}), 200