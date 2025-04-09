import string
import random
import base64
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
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
            
            # Verificar que no exista ya en la base de datos
            existing = mongo.database.usuarios.find_one({"code_referrals_uniq": code})
            if not existing:
                return code

    @app.route('/register', methods=['POST'])
    def register_user():
        # Usar request.form para obtener los campos de texto y request.files para la imagen
        request_data = request.form.to_dict()
        print("Datos de registro recibidos:", request_data)

        if not request_data or not all(k in request_data for k in ("nombre", "apellido", "correo", "password")):
            return jsonify({"error": "Faltan campos obligatorios"}), 400

        if mongo.database.usuarios.find_one({"correo": request_data["correo"]}):
            return jsonify({"error": "El correo ya está registrado"}), 400

        hashed_password = generate_password_hash(request_data['password'])

        # Procesar imagen si se envía como archivo
        image_file = request.files.get("image")  # 'image' debe ser el nombre del campo en el formulario
        if image_file:
            image_base64 = base64.b64encode(image_file.read()).decode('utf-8')  # Convertir la imagen a base64
        else:
            image_base64 = ""  # Si no se envía imagen, dejar como vacío

        unique_referral_code = generate_unique_referral_code()

        usuario = {
            "img": image_base64,
            "nombre": request_data["nombre"],
            "apellido": request_data["apellido"],
            "correo": request_data["correo"],
            "password": hashed_password,
            "rol": "user",
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
            "nombre": request_data["nombre"],
            "apellido": request_data["apellido"],
            "code_referrals_uniq": unique_referral_code
        }), 201


    @app.route('/register-admin', methods=['POST'])
    def register_admin():
        # Usamos request.form para obtener los campos de texto y request.files para la imagen
        request_data = request.form.to_dict()
        print("Datos de registro recibidos:", request_data)

        if not request_data or not all(k in request_data for k in ("nombre", "apellido", "correo", "password")):
            return jsonify({"error": "Faltan campos obligatorios"}), 400

        if mongo.database.usuarios.find_one({"correo": request_data["correo"]}):
            return jsonify({"error": "El correo ya está registrado"}), 400

        hashed_password = generate_password_hash(request_data['password'])

        # Procesar imagen si se envía como archivo
        image_file = request.files.get("image")  # 'image' debe ser el nombre del campo en el formulario
        if image_file:
            image_base64 = base64.b64encode(image_file.read()).decode('utf-8')  # Convertir la imagen a base64
        else:
            image_base64 = ""  # Si no se envía imagen, dejar como vacío

        unique_referral_code = generate_unique_referral_code()

        usuario = {
            "img": image_base64,
            "nombre": request_data["nombre"],
            "apellido": request_data["apellido"],
            "correo": request_data["correo"],
            "password": hashed_password,
            "rol": "admin",
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
            "nombre": request_data["nombre"],
            "apellido": request_data["apellido"],
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
                
            # Convertir ObjectId a string antes de guardar en caché
            usuario_cacheable = dict(usuario)
            usuario_cacheable['_id'] = str(usuario['_id'])
            cache.set(data["correo"], usuario_cacheable, timeout=1800)
            print(f"[INFO] Usuario {data['correo']} cargado desde MongoDB y cacheado")
            usuario = usuario_cacheable

        session['user_id'] = str(usuario['_id'])
        name = usuario['nombre'] + " " + usuario['apellido']
        
        # Pasamos directamente la cadena base64 para ser usada en el frontend
        img_base64 = ""
        if usuario.get("img"):
            img_base64 = usuario["img"]  # Enviamos directamente el string base64
            
        return jsonify({
            "message": "Inicio de sesión exitoso",
            "user_id": session['user_id'],
            "user_name": name,
            "user_img": img_base64,  # Enviamos la imagen en base64
            "code_referrals_uniq": usuario.get("code_referrals_uniq", ""),
            "count_referrals": usuario.get("count_referrals", 0)
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