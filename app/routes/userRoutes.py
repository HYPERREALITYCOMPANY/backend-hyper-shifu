from flask import request, jsonify
from app.utils.utils import get_user_from_db
from flask_caching import Cache
import datetime

def setup_user_routes(app, mongo, cache):
    # No necesitas reinicializar Cache aquí, ya se pasa como argumento desde create_app
    
    @app.route('/check_integrations', methods=['GET'])
    def check_integrations():
        email = request.args.get('email')

        if not email:
            return jsonify({"error": "Correo electrónico no proporcionado"}), 400

        # Obtener el usuario desde caché o MongoDB
        usuario = get_user_from_db(email, cache, mongo)
        if not usuario:
            return jsonify({"error": "Usuario no encontrado"}), 404

        integrations = usuario.get('integrations', {})
        if not integrations:
            return jsonify({"message": "Usuario sin integraciones"}), 200

        # Lista de integraciones con tokens ilimitados
        unlimited_token_integrations = ["Notion", "Slack", "ClickUp"]

        # Procesar las integraciones para devolver info útil
        integrations_status = {}
        for api, data in integrations.items():
            token = data.get('token')
            timestamp = data.get('timestamp')  # Asumimos formato 'YYYY-MM-DD HH:MM:SS'
            status = {}

            if not token:
                status['active'] = False
                status['reason'] = "No token available"
            elif api in unlimited_token_integrations:
                status['active'] = True
                status['reason'] = "Unlimited token"
            else:
                # Verificar si el token sigue activo (menos de 1 hora)
                if not timestamp:
                    status['active'] = False
                    status['reason'] = "No timestamp available"
                else:
                    try:
                        token_time = datetime.datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                        time_diff = (datetime.datetime.utcnow() - token_time).total_seconds()
                        token_lifetime = 3600  # 1 hora en segundos
                        status['active'] = time_diff <= token_lifetime
                        status['reason'] = (
                            f"Token active (remaining: {int(token_lifetime - time_diff)}s)" 
                            if status['active'] 
                            else f"Token expired (diff: {int(time_diff)}s)"
                        )
                    except ValueError:
                        status['active'] = False
                        status['reason'] = "Invalid timestamp format"

            integrations_status[api] = status

        # Contar integraciones activas
        active_count = sum(1 for status in integrations_status.values() if status['active'])

        return jsonify({
            "message": "Usuario con integraciones",
            "integrations": integrations_status,
            "active_integrations": active_count,
            "total_integrations": len(integrations)
        }), 200

    return {'check_integrations': check_integrations}  # Devolver funciones para posibles tests