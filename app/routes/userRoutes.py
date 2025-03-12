from flask import request, jsonify

def setup_user_routes(app, mongo, cache):
    
    @app.route('/check_integrations', methods=['GET'])
    def check_integrations():
        email = request.args.get('email')

        if not email:
            return jsonify({"error": "Correo electrónico no proporcionado"}), 400

        usuario = mongo.database.usuarios.find_one({"correo": email})
        
        if not usuario:
            return jsonify({"error": "Usuario no encontrado"}), 404

        if not usuario.get('integrations') or len(usuario['integrations']) == 0:
            return jsonify({"message": "Usuario sin integraciones"}), 200
        
        return jsonify({"message": "Usuario con integraciones", "integrations": usuario['integrations']}), 200