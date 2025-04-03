import random
import string
from datetime import datetime
from flask import request, jsonify
from flask_pymongo import ObjectId
from werkzeug.security import generate_password_hash


def setup_referrals_routes(app, mongo, cache):
    # Función para generar un código único de 6 dígitos
    def generate_unique_referral_code():
        while True:
            # Generar código alfanumérico de 6 caracteres
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            
            # Verificar que no exista ya en la base de datos
            existing = mongo.database.usuarios.find_one({"code_referrals_uniq": code})
            if not existing:
                return code

    # Ruta para registro con código de referido
    @app.route('/register_with_referral', methods=['POST'])
    def register_with_referral():
        request_data = request.get_json()
        
        if not request_data or "registerUser" not in request_data:
            return jsonify({"error": "El cuerpo de la solicitud es inválido"}), 400

        data = request_data.get('registerUser')
        if not data or not all(k in data for k in ("nombre", "apellido", "correo", "password", "referral_code")):
            return jsonify({"error": "Faltan campos obligatorios incluyendo el código de referido"}), 400

        if mongo.database.usuarios.find_one({"correo": data["correo"]}):
            return jsonify({"error": "El correo ya está registrado"}), 400
            
        # Verificar que el código de referido existe
        referrer = mongo.database.usuarios.find_one({"code_referrals_uniq": data["referral_code"]})
        if not referrer:
            return jsonify({"error": "Código de referido inválido"}), 400
            
        hashed_password = generate_password_hash(data['password'])
        
        # Generar código único de referido para el nuevo usuario
        unique_referral_code = generate_unique_referral_code()
        
        usuario = {
            "img": data.get("img", ""),  
            "nombre": data["nombre"],
            "apellido": data["apellido"],
            "correo": data["correo"],
            "password": hashed_password,
            "integrations": {},
            "code_referrals_uniq": unique_referral_code,
            "count_referrals": 0, 
            "date_registered": datetime.now()
        }

        if 'usuarios' not in mongo.database.list_collection_names():
            mongo.database.create_collection('usuarios')

        result = mongo.database.usuarios.insert_one(usuario)
        new_user_id = str(result.inserted_id)
        
        # Crear registro en la colección de referidos
        if 'referrals' not in mongo.database.list_collection_names():
            mongo.database.create_collection('referrals')
            
        referral_record = {
            "referrer_id": str(referrer["_id"]),
            "referred_id": new_user_id,
            "nombre": data["nombre"],
            "apellido": data["apellido"],
            "referral_code": data["referral_code"],
            "date_registered": datetime.now()
        }
        
        mongo.database.referrals.insert_one(referral_record)
        
        # Incrementar el contador de referidos del usuario que refirió
        mongo.database.usuarios.update_one(
            {"_id": referrer["_id"]},
            {"$inc": {"count_referrals": 1}}
        )
        
        # Invalidar caché del referente
        if "correo" in referrer:
            cache.delete(referrer["correo"])
            
        return jsonify({
            "message": "Usuario registrado exitosamente con referido", 
            "id": new_user_id,
            "code_referrals_uniq": unique_referral_code
        }), 201
    
    # Ruta para obtener información de referidos de un usuario
    @app.route('/user/referrals', methods=['GET'])
    def get_user_referrals():
        user_id = request.args.get('id')
        
        if not user_id or not ObjectId.is_valid(user_id):
            return jsonify({"error": "ID de usuario inválido"}), 400
            
        # Obtener el usuario y su información de referidos
        try:
            usuario = mongo.database.usuarios.find_one({"_id": ObjectId(user_id)})
            if not usuario:
                return jsonify({"error": "Usuario no encontrado"}), 404
                
            # Obtener lista de usuarios referidos
            referrals = list(mongo.database.referrals.find({"referrer_id": user_id}))
            
            # Obtener información básica de cada referido
            referrals_info = []
            for referral in referrals:
                referred_user = mongo.database.usuarios.find_one({"_id": ObjectId(referral["referred_id"])})
                if referred_user:
                    referrals_info.append({
                        "user_id": referral["referred_id"],
                        "nombre": referred_user["nombre"],
                        "apellido": referred_user["apellido"],
                        "correo": referred_user["correo"],
                        "img": referred_user.get("img", ""),
                        "date_registered": referral["date_registered"]
                    })
            
            return jsonify({
                "user_id": user_id,
                "code_referrals_uniq": usuario.get("code_referrals_uniq", ""),
                "count_referrals": usuario.get("count_referrals", 0),
                "referrals": referrals_info
            }), 200
            
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    # Ruta para verificar si un código de referido es válido
    @app.route('/verify_referral_code', methods=['GET'])
    def verify_referral_code():
        code = request.args.get('code')
        
        if not code:
            return jsonify({"error": "Código de referido no proporcionado"}), 400
            
        # Buscar el usuario que tiene este código
        referrer = mongo.database.usuarios.find_one({"code_referrals_uniq": code})
        
        if not referrer:
            return jsonify({"valid": False}), 200
            
        return jsonify({
            "valid": True,
            "referrer": {
                "id": str(referrer["_id"]),
                "nombre": referrer["nombre"],
                "apellido": referrer["apellido"]
            }
        }), 200