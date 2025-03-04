from flask import Blueprint, request, jsonify
from flask_pymongo import ObjectId
from datetime import datetime

user_bp = Blueprint("user", __name__)

def setup_user_routes(app, mongo):
    
    @user_bp.route('/check_integrations', methods=['GET'])
    def check_integrations():
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Correo electrónico no proporcionado"}), 400

        usuario = mongo.db.usuarios.find_one({"correo": email})
        if not usuario:
            return jsonify({"error": "Usuario no encontrado"}), 404

        return jsonify({
            "message": "Integraciones encontradas" if usuario.get('integrations') else "Sin integraciones",
            "integrations": usuario.get('integrations', {})
        }), 200

    @user_bp.route('/add_integration', methods=['POST'])
    def add_integration():
        request_data = request.get_json()
        user_email = request_data.get("email")
        integration_name = request_data.get("integration")
        token = request_data.get("token")
        expires_in = request_data.get("expires_in")

        if not all([user_email, integration_name, token]):
            return jsonify({"error": "Faltan datos"}), 400

        user = mongo.db.usuarios.find_one({"correo": user_email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        integration_data = {
            "token": token,
            "timestamp": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        }

        if integration_name not in ["Notion", "Slack", "ClickUp"] and expires_in is None:
            return jsonify({"error": "Se requiere 'expires_in' para esta integración"}), 400

        if expires_in:
            integration_data["expires_in"] = int(expires_in)

        mongo.db.usuarios.update_one(
            {"correo": user_email},
            {"$set": {f"integrations.{integration_name}": integration_data}}
        )

        return jsonify({"message": "Integración añadida"}), 200

    app.register_blueprint(user_bp)