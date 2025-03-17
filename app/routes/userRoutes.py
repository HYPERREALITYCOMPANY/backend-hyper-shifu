from flask import request, jsonify
from app.utils.utils import get_user_from_db
from flask_caching import Cache
def setup_user_routes(app, mongo, cache):
    cache = Cache(app)
    
    @app.route('/check_integrations', methods=['GET'])
    def check_integrations():
        email = request.args.get('email')

        if not email:
            return jsonify({"error": "Correo electrónico no proporcionado"}), 400

        usuario = get_user_from_db(email, cache, mongo)
        
        if not usuario:
            return jsonify({"error": "Usuario no encontrado"}), 404

        if not usuario.get('integrations') or len(usuario['integrations']) == 0:
            return jsonify({"message": "Usuario sin integraciones"}), 200
        
        return jsonify({"message": "Usuario con integraciones", "integrations": usuario['integrations']}), 200