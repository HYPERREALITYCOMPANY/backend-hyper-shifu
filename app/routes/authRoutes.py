from datetime import datetime, timedelta
from flask import request, jsonify, session
from flask_pymongo import ObjectId
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import string
import random
import base64

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
    
    # Función para actualizar la racha de login del usuario
    def update_login_streak(user_id):
        # Obtener fecha actual en formato UTC
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday = today - timedelta(days=1)
        
        # Buscar el último registro de login del usuario
        last_login = mongo.database.login_streaks.find_one(
            {"user_id": ObjectId(user_id)},
            sort=[("login_date", -1)]
        )
        
        # Crear el registro de login para hoy
        login_record = {
            "user_id": ObjectId(user_id),
            "login_date": today,
            "created_at": datetime.utcnow()
        }
        
        # Insertar el nuevo registro de login
        mongo.database.login_streaks.insert_one(login_record)
        
        # Actualizar la racha del usuario
        if last_login:
            last_login_date = last_login["login_date"]
            
            # Si el último login fue ayer, incrementar la racha
            if last_login_date.date() == yesterday.date():
                mongo.database.usuarios.update_one(
                    {"_id": ObjectId(user_id)},
                    {"$inc": {"login_streak": 1}}
                )
            # Si el último login fue hoy, no hacer nada (ya ha iniciado sesión hoy)
            elif last_login_date.date() == today.date():
                pass
            # Si el último login fue hace más de un día, reiniciar la racha
            else:
                # Eliminar registros anteriores
                mongo.database.login_streaks.delete_many({"user_id": ObjectId(user_id)})
                # Insertar el registro de hoy nuevamente
                mongo.database.login_streaks.insert_one(login_record)
                # Reiniciar contador a 1
                mongo.database.usuarios.update_one(
                    {"_id": ObjectId(user_id)},
                    {"$set": {"login_streak": 1}}
                )
        else:
            # Es el primer login, establecer racha en 1
            mongo.database.usuarios.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": {"login_streak": 1}}
            )

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
            "login_streak": 0,  # Inicializar contador de racha
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
            "login_streak": 0,  # Inicializar contador de racha
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
            # Convertir _id a ObjectId si está como string
            user_id = usuario['_id'] if isinstance(usuario['_id'], ObjectId) else ObjectId(usuario['_id'])
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
            user_id = usuario['_id']
        
        # Actualizar la racha de login del usuario
        update_login_streak(str(user_id))
        
        # Obtener el usuario actualizado después de actualizar la racha
        usuario_actualizado = mongo.database.usuarios.find_one({"_id": user_id if isinstance(user_id, ObjectId) else ObjectId(user_id)})
        
        session['user_id'] = str(usuario_actualizado['_id'])
        name = usuario_actualizado['nombre'] + " " + usuario_actualizado['apellido']
        
        # Actualizar caché con información actualizada
        usuario_cacheable = dict(usuario_actualizado)
        usuario_cacheable['_id'] = str(usuario_actualizado['_id'])
        cache.set(data["correo"], usuario_cacheable, timeout=1800)
        
        # Pasamos directamente la cadena base64 para ser usada en el frontend
        img_base64 = ""
        if usuario_actualizado.get("img"):
            img_base64 = usuario_actualizado["img"]  # Enviamos directamente el string base64
            
        return jsonify({
            "message": "Inicio de sesión exitoso",
            "user_id": session['user_id'],
            "user_name": name,
            "user_img": img_base64,  # Enviamos la imagen en base64
            "code_referrals_uniq": usuario_actualizado.get("code_referrals_uniq", ""),
            "count_referrals": usuario_actualizado.get("count_referrals", 0),
            "login_streak": usuario_actualizado.get("login_streak", 0)  # Incluir la racha actual
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
    
    # Nueva ruta para obtener el historial de logins de un usuario
    @app.route("/login_history", methods=["GET"])
    def get_login_history():
        user_id = request.args.get('id')
        if not user_id:
            return jsonify({"error": "ID de usuario no proporcionado"}), 400
        
        try:
            # Obtener registros de login del usuario
            login_history = list(mongo.database.login_streaks.find(
                {"user_id": ObjectId(user_id)},
                sort=[("login_date", -1)]
            ))
            
            # Formatear los resultados
            formatted_history = []
            for login in login_history:
                formatted_history.append({
                    "login_date": login["login_date"].strftime("%Y-%m-%d"),
                    "login_time": login["created_at"].strftime("%H:%M:%S")
                })
            
            # Obtener la racha actual
            usuario = mongo.database.usuarios.find_one({"_id": ObjectId(user_id)})
            current_streak = usuario.get("login_streak", 0)
            
            return jsonify({
                "user_id": user_id,
                "current_streak": current_streak,
                "login_history": formatted_history
            }), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500