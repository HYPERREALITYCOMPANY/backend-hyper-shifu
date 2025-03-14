from flask import request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_pymongo import ObjectId
from utils.utils import get_user_from_db
def setup_auth_routes(app, mongo):

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
        usuario = {
            "img": data.get("img", ""),  
            "nombre": data["nombre"],
            "apellido": data["apellido"],
            "correo": data["correo"],
            "password": hashed_password,
            "integrations": {}
        }

        if 'usuarios' not in mongo.database.list_collection_names():
            mongo.database.create_collection('usuarios')

        result = mongo.database.usuarios.insert_one(usuario)
        return jsonify({"message": "Usuario registrado exitosamente", "id": str(result.inserted_id)}), 201

    @app.route('/login', methods=['POST'])
    def login_user():
        data = request.get_json()
        if not data or not all(k in data for k in ("correo", "password")):
            return jsonify({"error": "Faltan campos obligatorios"}), 400
        
        # Usa Redis para obtener el usuario
        usuario = get_user_from_db(data["correo"], cache, mongo)

        if not usuario or not check_password_hash(usuario["password"], data["password"]):
            return jsonify({"error": "Credenciales incorrectas"}), 401

        session['user_id'] = str(usuario['_id'])
        name = usuario['nombre'] + " " + usuario['apellido']
        img = usuario['img']
        
        return jsonify({
            "message": "Inicio de sesión exitoso",
            "user_id": session['user_id'],
            "user_name": name,
            "user_img": img 
        }), 200
    
    @app.route("/get_user", methods=["GET"])
    def get_user():
        user_id = request.args.get('id')
        if not user_id:
            return jsonify({"error": "ID de usuario no proporcionado"}), 400
        
        try:
            usuario = mongo.database.usuarios.find_one({"_id": ObjectId(user_id)})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        
        if not usuario:
            return jsonify({"error": "Usuario no encontrado"}), 404
        
        usuario["_id"] = str(usuario["_id"])
        return jsonify({"user": usuario}), 200

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

        return jsonify({"message": "Usuario actualizado con éxito"}), 200
