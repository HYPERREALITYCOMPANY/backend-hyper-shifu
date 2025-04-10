import string
import random
from datetime import datetime
from flask_pymongo import ObjectId
from flask import request, jsonify, session
from app.utils.utils import get_user_from_db
from werkzeug.security import generate_password_hash, check_password_hash


def setup_auth_routes(app, mongo, cache):
    # Función para generar un código único de 6 dígitos
    def generate_unique_referral_code():
        while True:
            # Generar código alfanumérico de 6 caracteres
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            
            # Verificar que no exista ya en la base de datos
            existing = mongo.database.usuarios.find_one({"code_referrals_uniq": code})
            if not existing:
                return code

    @app.route('/register', methods=['POST'])
    def register_user():
        request_data = request.get_json() 
        
        if not request_data or "registerUser" not in request_data:
            return jsonify({"error": "El cuerpo de la solicitud es inválido"}), 400

        data = request_data.get('registerUser')
        if not data or not all(k in data for k in ("nombre", "apellido", "correo", "password")):
            return jsonify({"error": "Faltan campos obligatorios"}), 400

        if mongo.database.usuarios.find_one({"correo": data["correo"]}):
            return jsonify({"error": "El correo ya está registrado"}), 400

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
        return jsonify({
            "message": "Usuario registrado exitosamente", 
            "id": str(result.inserted_id),
            "nombre": data["nombre"],
            "apellido": data["apellido"],
            "code_referrals_uniq": unique_referral_code,
            "date_registered": datetime.now()
        }), 201

    @app.route('/login', methods=['POST'])
    def login_user():
        data = request.get_json()
        if not data or not all(k in data for k in ("correo", "password")):
            return jsonify({"error": "Faltan campos obligatorios"}), 400
        
        # Primero revisamos el caché
        usuario = cache.get(data["correo"])
        if usuario and check_password_hash(usuario["password"], data["password"]):
            print(f"[INFO] Usuario {data['correo']} encontrado en caché, login rápido")
        else:
            # Si no está en caché, consultamos MongoDB
            usuario = mongo.database.usuarios.find_one({'correo': data["correo"]})
            if not usuario or not check_password_hash(usuario["password"], data["password"]):
                return jsonify({"error": "Credenciales incorrectas"}), 401
            cache.set(data["correo"], usuario, timeout=1800)  # Guardamos en caché por 30 min
            print(f"[INFO] Usuario {data['correo']} cargado desde MongoDB y cacheado")

        session['user_id'] = str(usuario['_id'])
        name = usuario['nombre'] + " " + usuario['apellido']
        img = usuario['img']
        
        return jsonify({
            "message": "Inicio de sesión exitoso",
            "user_id": session['user_id'],
            "user_name": name,
            "user_img": img,
            "code_referrals_uniq": usuario.get("code_referrals_uniq", ""),  # Incluimos el código de referido
            "count_referrals": usuario.get("count_referrals", 0)  # Incluimos el contador de referidos
        }), 200
    
    @app.route("/get_user", methods=["GET"])
    def get_user():
        user_id = request.args.get('id')
        if not user_id:
            return jsonify({"error": "ID de usuario no proporcionado"}), 400
        
        try:
            usuario = mongo.database.usuarios.find_one({"_id": ObjectId(user_id)})
            if not usuario:
                return jsonify({"error": "Usuario no encontrado"}), 404
            usuario["_id"] = str(usuario["_id"])
            cache.set(usuario["correo"], usuario, timeout=1800)  # Cacheamos por correo
            return jsonify({"user": usuario}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/update_user", methods=["PUT"])
    def update_user():
        user_id = request.json.get('id')
        update_data = {
            "nombre": request.json.get('nombre'),
            "correo": request.json.get('correo'),
            "img": request.json.get('img')
        }
        if not user_id or not ObjectId.is_valid(user_id):
            return jsonify({"error": "ID de usuario inválido"}), 400

        result = mongo.database.usuarios.update_one({"_id": ObjectId(user_id)}, {"$set": update_data})
        if result.matched_count == 0:
            return jsonify({"error": "Usuario no encontrado"}), 404

        # Invalidamos caché del usuario si el correo cambió
        if "correo" in update_data:
            cache.delete(update_data["correo"])
        return jsonify({"message": "Usuario actualizado con éxito"}), 200