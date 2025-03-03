from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from database import mongo

# Crear Blueprint para autenticación
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['POST'])
def register_user():
    """Registra un nuevo usuario"""
    data = request.get_json().get('registerUser')

    if not data or not all(k in data for k in ("nombre", "apellido", "correo", "password")):
        return jsonify({"error": "Faltan campos obligatorios"}), 400

    if mongo.db.usuarios.find_one({"correo": data["correo"]}):
        return jsonify({"error": "El correo ya está registrado"}), 400

    usuario = {
        "img": data.get("img", ""),  
        "nombre": data["nombre"],
        "apellido": data["apellido"],
        "correo": data["correo"],
        "password": generate_password_hash(data['password']),
        "integrations": {}
    }
    result = mongo.db.usuarios.insert_one(usuario)
    return jsonify({"message": "Usuario registrado exitosamente", "id": str(result.inserted_id)}), 201

@auth_bp.route('/login', methods=['POST'])
def login_user():
    """Autentica a un usuario"""
    data = request.get_json()
    usuario = mongo.db.usuarios.find_one({"correo": data["correo"]})
    if not usuario or not check_password_hash(usuario["password"], data["password"]):
        return jsonify({"error": "Credenciales incorrectas"}), 401

    session['user_id'] = str(usuario['_id'])
    return jsonify({"message": "Inicio de sesión exitoso", "user_id": session['user_id']}), 200

@auth_bp.route('/logout', methods=['POST'])
def logout_user():
    """Cierra la sesión del usuario"""
    session.pop('user_id', None)
    return jsonify({"message": "Sesión cerrada exitosamente"}), 200