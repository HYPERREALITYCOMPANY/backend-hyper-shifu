from datetime import datetime
from flask import request, jsonify
from flask_pymongo import ObjectId
from functools import wraps

def setup_reward_routes(app, mongo, cache):

    # Middleware de admin usando user_id desde el body
    def admin_required(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user_id = request.json.get("id") if request.json else None
            if not user_id:
                return jsonify({"error": "user_id requerido"}), 400

            user = mongo.database.usuarios.find_one({"_id": ObjectId(user_id)})
            if not user or user.get("rol") != "admin":
                return jsonify({"error": "Acceso denegado, no eres admin"}), 403

            request.user = user  # Guardamos user en request si es necesario luego
            return f(*args, **kwargs)
        return decorated

    # Crear recompensa (solo admin)
    @app.route('/admin/rewards', methods=['POST'])
    @admin_required
    def create_reward():
        data = request.json
        
        # Validar tipo de recompensa
        reward_type = data.get("type")
        if reward_type not in ["referral", "challenge", "streak"]:
            return jsonify({"error": "Tipo de recompensa inválido. Debe ser 'referral' o 'challenge'"}), 400
        
        # Si es tipo challenge, la fecha de fin es obligatoria
        if reward_type == "challenge" and not data.get("end_date"):
            return jsonify({"error": "Las recompensas por desafío requieren fecha de finalización"}), 400
            
        # Preparar objeto de recompensa
        reward = {
            "name": data.get("name"),
            "description": data.get("description"),
            "type": reward_type,
            "max_redemptions_per_user": data.get("max_redemptions_per_user", 1),
            "required_referrals": data.get("required_referrals", 0) if reward_type == "referral" else 0,
            "active": data.get("active", True),
            "created_at": datetime.utcnow(),
            "start_date": datetime.fromisoformat(data.get("start_date")) if data.get("start_date") else datetime.utcnow()
        }
        
        # Agregar fecha de fin si está presente
        if data.get("end_date"):
            reward["end_date"] = datetime.fromisoformat(data.get("end_date"))
        
        # Agregar detalles específicos para desafíos semanales
        if reward_type == "challenge":
            reward["challenge_description"] = data.get("challenge_description", "")
            reward["challenge_goal"] = data.get("challenge_goal", "")
            reward["challenge_points"] = data.get("challenge_points", 0)
        
        result = mongo.database.rewards.insert_one(reward)
        reward["_id"] = str(result.inserted_id)
        
        # Convertir fechas a string para respuesta JSON
        if "start_date" in reward:
            reward["start_date"] = reward["start_date"].isoformat()
        if "end_date" in reward:
            reward["end_date"] = reward["end_date"].isoformat()
        
        return jsonify(reward), 201

    # Ver todas las recompensas (para admin)
    @app.route('/admin/rewards', methods=['GET'])
    @admin_required
    def get_admin_rewards():
        rewards = list(mongo.database.rewards.find())
        for r in rewards:
            r["_id"] = str(r["_id"])
            if "start_date" in r:
                r["start_date"] = r["start_date"].isoformat()
            if "end_date" in r:
                r["end_date"] = r["end_date"].isoformat()
        return jsonify(rewards)

    # Ver recompensas activas (para usuarios)
    @app.route('/rewards', methods=['GET'])
    def get_user_rewards():
        now = datetime.utcnow()
        
        # Filtrar recompensas activas y dentro del período válido
        query = {
            "active": True,
            "start_date": {"$lte": now}
        }
        
        # Solo incluir condición de fecha de fin si existe
        rewards = list(mongo.database.rewards.find({
            **query,
            "$or": [
                {"end_date": {"$exists": False}},
                {"end_date": {"$gt": now}}
            ]
        }))
        
        for r in rewards:
            r["_id"] = str(r["_id"])
            if "start_date" in r:
                r["start_date"] = r["start_date"].isoformat()
            if "end_date" in r:
                r["end_date"] = r["end_date"].isoformat()
                
        return jsonify(rewards)

    # Editar recompensa (solo admin)
    @app.route('/admin/rewards/<reward_id>', methods=['PUT'])
    @admin_required
    def update_reward(reward_id):
        data = request.json
        
        # Validar que no se cambie el tipo
        existing_reward = mongo.database.rewards.find_one({"_id": ObjectId(reward_id)})
        if not existing_reward:
            return jsonify({"error": "Recompensa no encontrada"}), 404
            
        # Si cambia el tipo de challenge a referral y no hay required_referrals
        if data.get("type") == "referral" and existing_reward.get("type") == "challenge" and not data.get("required_referrals"):
            return jsonify({"error": "Las recompensas de tipo referido requieren required_referrals"}), 400
            
        # Si cambia de referral a challenge y no hay end_date
        if data.get("type") == "challenge" and existing_reward.get("type") == "referral" and not data.get("end_date"):
            return jsonify({"error": "Las recompensas por desafío requieren fecha de finalización"}), 400
        
        # Preparar campos a actualizar
        update_fields = {}
        for field in ["name", "description", "max_redemptions_per_user", "required_referrals", 
                     "active", "challenge_description", "challenge_goal", "challenge_points", "type"]:
            if field in data:
                update_fields[field] = data[field]
        
        # Manejar fechas
        if "start_date" in data:
            update_fields["start_date"] = datetime.fromisoformat(data["start_date"])
        if "end_date" in data:
            update_fields["end_date"] = datetime.fromisoformat(data["end_date"])
            
        mongo.database.rewards.update_one({"_id": ObjectId(reward_id)}, {"$set": update_fields})
        
        # Obtener recompensa actualizada
        updated_reward = mongo.database.rewards.find_one({"_id": ObjectId(reward_id)})
        updated_reward["_id"] = str(updated_reward["_id"])
        
        # Convertir fechas para respuesta JSON
        if "start_date" in updated_reward:
            updated_reward["start_date"] = updated_reward["start_date"].isoformat()
        if "end_date" in updated_reward:
            updated_reward["end_date"] = updated_reward["end_date"].isoformat()
            
        return jsonify(updated_reward)

    # Activar/desactivar recompensa (solo admin)
    @app.route('/admin/rewards/<reward_id>/toggle-status', methods=['PUT'])
    @admin_required
    def toggle_reward_status(reward_id):
        reward = mongo.database.rewards.find_one({"_id": ObjectId(reward_id)})
        if not reward:
            return jsonify({"error": "Recompensa no encontrada"}), 404
            
        new_status = not reward.get("active", True)
        mongo.database.rewards.update_one(
            {"_id": ObjectId(reward_id)},
            {"$set": {"active": new_status}}
        )
        
        return jsonify({
            "message": f"Recompensa {'activada' if new_status else 'desactivada'} correctamente",
            "reward_id": reward_id,
            "active": new_status
        })

    # Eliminar recompensa (solo admin)
    @app.route('/admin/rewards/<reward_id>', methods=['DELETE'])
    @admin_required
    def delete_reward(reward_id):
        result = mongo.database.rewards.delete_one({"_id": ObjectId(reward_id)})
        if result.deleted_count == 0:
            return jsonify({"error": "Recompensa no encontrada"}), 404
        return jsonify({"message": "Recompensa eliminada correctamente"})

    # Canjear recompensa de tipo referido
    @app.route('/rewards/<reward_id>/redeem', methods=['POST'])
    def redeem_reward(reward_id):
        data = request.json
        user_id = data.get("id")

        if not user_id:
            return jsonify({"error": "user_id requerido"}), 400

        user_doc = mongo.database.usuarios.find_one({"_id": ObjectId(user_id)})
        if not user_doc:
            return jsonify({"error": "Usuario no encontrado"}), 404

        reward = mongo.database.rewards.find_one({"_id": ObjectId(reward_id)})
        if not reward:
            return jsonify({"error": "Recompensa no encontrada"}), 404

        # Verificar si la recompensa está activa
        if not reward.get("active", True):
            return jsonify({"error": "Esta recompensa no está activa actualmente"}), 400

        # Verificar fechas
        now = datetime.utcnow()
        if reward.get("end_date") and reward["end_date"] < now:
            return jsonify({"error": "Esta recompensa ha expirado"}), 400
        if reward.get("start_date") and reward["start_date"] > now:
            return jsonify({"error": "Esta recompensa aún no está disponible"}), 400

        # Lógica específica por tipo de recompensa
        if reward["type"] == "referral":
            # Verificar si tiene suficientes referidos
            if user_doc.get("count_referrals", 0) < reward["required_referrals"]:
                return jsonify({
                    "error": "No tienes suficientes referidos para esta recompensa",
                    "have": user_doc.get("count_referrals", 0),
                    "you_need": reward["required_referrals"]
                }), 400

        # Verificar si ya ha canjeado el máximo permitido
        count = mongo.database.reward_redeem.count_documents({
            "user_id": ObjectId(user_id),
            "reward_id": ObjectId(reward_id)
        })

        if count >= reward["max_redemptions_per_user"]:
            return jsonify({"error": "Ya has canjeado esta recompensa el número máximo de veces"}), 400

        # Registrar canje
        redeem_record = {
            "user_id": ObjectId(user_id),
            "reward_id": ObjectId(reward_id),
            "reward_type": reward["type"],
            "reward_name": reward["name"],
            "redeemed_at": datetime.utcnow()
        }
        
        # Si es recompensa por referidos, restar count_referrals
        if reward["type"] == "referral":
            # Restar el número de referidos usados del contador del usuario
            mongo.database.usuarios.update_one(
                {"_id": ObjectId(user_id)},
                {"$inc": {"count_referrals": -reward["required_referrals"]}}
            )
            redeem_record["referrals_used"] = reward["required_referrals"]
            
            # Invalidar caché del usuario
            if "correo" in user_doc:
                cache.delete(user_doc["correo"])

        # Insertar registro del canje
        mongo.database.reward_redeem.insert_one(redeem_record)

        return jsonify({
            "message": "Recompensa canjeada correctamente",
            "reward_name": reward["name"],
            "type": reward["type"],
            "redeemed_at": datetime.utcnow().isoformat()
        }), 200

    # Obtener historial de recompensas canjeadas por un usuario
    @app.route('/rewards/history', methods=['GET'])
    def get_user_rewards_history():
        user_id = request.args.get('id')
        
        if not user_id:
            return jsonify({"error": "ID de usuario requerido"}), 400
            
        try:
            # Obtener historial de canjes del usuario
            redeems = list(mongo.database.reward_redeem.find({"user_id": ObjectId(user_id)}))
            
            history = []
            for redeem in redeems:
                history.append({
                    "reward_id": str(redeem["reward_id"]),
                    "reward_name": redeem.get("reward_name", ""),
                    "reward_type": redeem.get("reward_type", ""),
                    "redeemed_at": redeem["redeemed_at"].isoformat(),
                    "referrals_used": redeem.get("referrals_used", 0)
                })
                
            return jsonify({
                "user_id": user_id,
                "redeem_history": history
            }), 200
            
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    # API para marcar un desafío como completado por un usuario
    @app.route('/challenges/<challenge_id>/complete', methods=['POST'])
    def complete_challenge(challenge_id):
        data = request.json
        user_id = data.get("id")
        
        if not user_id:
            return jsonify({"error": "ID de usuario requerido"}), 400
            
        user = mongo.database.usuarios.find_one({"_id": ObjectId(user_id)})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404
            
        reward = mongo.database.rewards.find_one({
            "_id": ObjectId(challenge_id),
            "type": "challenge"
        })
        
        if not reward:
            return jsonify({"error": "Desafío no encontrado"}), 404
            
        # Verificar si el desafío está activo y no ha expirado
        now = datetime.utcnow()
        if not reward.get("active", True):
            return jsonify({"error": "Este desafío no está activo"}), 400
            
        if reward.get("end_date") and reward["end_date"] < now:
            return jsonify({"error": "Este desafío ha expirado"}), 400
            
        # Verificar si ya ha completado este desafío antes
        existing_completion = mongo.database.challenge_completions.find_one({
            "user_id": ObjectId(user_id),
            "challenge_id": ObjectId(challenge_id)
        })
        
        if existing_completion:
            return jsonify({"error": "Ya has completado este desafío anteriormente"}), 400
            
        # Registrar la finalización del desafío
        completion = {
            "user_id": ObjectId(user_id),
            "challenge_id": ObjectId(challenge_id),
            "challenge_name": reward["name"],
            "completed_at": now,
            "evidence": data.get("evidence", ""),  # Opcional: prueba de cumplimiento
            "approved": False  # Requiere aprobación por admin
        }
        
        result = mongo.database.challenge_completions.insert_one(completion)
        
        return jsonify({
            "message": "Desafío completado y enviado para aprobación",
            "completion_id": str(result.inserted_id)
        }), 200
        
    # API para admin: aprobar la finalización de un desafío
    @app.route('/admin/challenges/approve', methods=['POST'])
    @admin_required
    def approve_challenge():
        data = request.json
        completion_id = data.get("completion_id")
        
        if not completion_id:
            return jsonify({"error": "ID de finalización requerido"}), 400
            
        completion = mongo.database.challenge_completions.find_one({
            "_id": ObjectId(completion_id)
        })
        
        if not completion:
            return jsonify({"error": "Registro de finalización no encontrado"}), 404
            
        # Actualizar estado a aprobado
        mongo.database.challenge_completions.update_one(
            {"_id": ObjectId(completion_id)},
            {"$set": {"approved": True, "approved_at": datetime.utcnow()}}
        )
        
        # Obtener información del desafío
        challenge = mongo.database.rewards.find_one({
            "_id": completion["challenge_id"]
        })
        
        # Registrar canje automático de la recompensa por completar el desafío
        redeem_record = {
            "user_id": completion["user_id"],
            "reward_id": completion["challenge_id"],
            "reward_type": "challenge",
            "reward_name": challenge["name"],
            "redeemed_at": datetime.utcnow(),
            "challenge_completion_id": completion["_id"]
        }
        
        mongo.database.reward_redeem.insert_one(redeem_record)
        
        return jsonify({
            "message": "Desafío aprobado y recompensa otorgada",
            "user_id": str(completion["user_id"]),
            "challenge_id": str(completion["challenge_id"]),
            "challenge_name": completion["challenge_name"]
        }), 200
        
    # API para listar desafíos pendientes de aprobación (admin)
    @app.route('/admin/challenges/pending', methods=['GET'])
    @admin_required
    def list_pending_challenges():
        pending = list(mongo.database.challenge_completions.find({"approved": False}))
        
        result = []
        for p in pending:
            # Obtener información del usuario
            user = mongo.database.usuarios.find_one({"_id": p["user_id"]})
            user_info = {"nombre": "Desconocido", "apellido": "", "correo": ""}
            if user:
                user_info = {
                    "nombre": user.get("nombre", ""),
                    "apellido": user.get("apellido", ""),
                    "correo": user.get("correo", "")
                }
                
            # Obtener información del desafío
            challenge = mongo.database.rewards.find_one({"_id": p["challenge_id"]})
            challenge_info = {"name": "Desconocido", "description": ""}
            if challenge:
                challenge_info = {
                    "name": challenge.get("name", ""),
                    "description": challenge.get("description", ""),
                    "challenge_description": challenge.get("challenge_description", "")
                }
                
            result.append({
                "completion_id": str(p["_id"]),
                "user_id": str(p["user_id"]),
                "user": user_info,
                "challenge_id": str(p["challenge_id"]),
                "challenge": challenge_info,
                "completed_at": p["completed_at"].isoformat(),
                "evidence": p.get("evidence", "")
            })
            
        return jsonify(result), 200
    
    # Ruta para crear o actualizar una recompensa por racha
    @app.route('/admin/rewards-streak', methods=['POST'])
    @admin_required
    def create_update_reward():
        data = request.get_json()
        
        if not data or not all(k in data for k in ("streak_days", "reward_type", "reward_value", "description")):
            return jsonify({"error": "Faltan campos obligatorios"}), 400
        
        existing_reward = mongo.database.rewards.find_one({"streak_days": data["streak_days"]})
        
        reward_data = {
            "streak_days": data["streak_days"],
            "type": "streak",
            "reward_type": data["reward_type"],  # "discount", "feature", "points", etc.
            "reward_value": data["reward_value"],  # Valor de descuento, número de puntos, etc.
            "description": data["description"],
            "updated_at": datetime.utcnow()
        }
        
        if existing_reward:
            # Actualizar recompensa existente
            mongo.database.rewards.update_one(
                {"_id": existing_reward["_id"]},
                {"$set": reward_data}
            )
            return jsonify({"message": "Recompensa actualizada con éxito", "reward_id": str(existing_reward["_id"])}), 200
        else:
            # Crear nueva recompensa
            reward_data["created_at"] = datetime.utcnow()
            result = mongo.database.rewards.insert_one(reward_data)
            return jsonify({"message": "Recompensa creada con éxito", "reward_id": str(result.inserted_id)}), 201

    # Ruta para listar todas las recompensas
    @app.route('/rewards-streak', methods=['GET'])
    def list_rewards():
        rewards = list(mongo.database.rewards.find({ "type": "streak" }))
        
        # Convertir ObjectId a string para serialización JSON
        for reward in rewards:
            reward["_id"] = str(reward["_id"])
            
        return jsonify({"rewards": rewards}), 200

    # Ruta para obtener las recompensas de un usuario específico
    # @app.route('/user/rewards', methods=['GET'])
    # def get_user_rewards():
    #     user_id = request.headers.get('user-id')
    #     if not user_id:
    #         return jsonify({"error": "Autenticación requerida"}), 401
            
    #     try:
    #         # Obtener información del usuario
    #         usuario = mongo.database.usuarios.find_one({"_id": ObjectId(user_id)})
    #         if not usuario:
    #             return jsonify({"error": "Usuario no encontrado"}), 404
                
    #         # Obtener la racha actual del usuario
    #         current_streak = usuario.get("login_streak", 0)
            
    #         # Buscar todas las recompensas disponibles para la racha actual
    #         available_rewards = list(mongo.database.rewards.find({"streak_days": {"$lte": current_streak}}).sort("streak_days", 1))
            
    #         # Formatear las recompensas
    #         formatted_rewards = []
    #         for reward in available_rewards:
    #             formatted_rewards.append({
    #                 "id": str(reward["_id"]),
    #                 "streak_days": reward["streak_days"],
    #                 "reward_type": reward["reward_type"],
    #                 "reward_value": reward["reward_value"],
    #                 "description": reward["description"],
    #                 "is_current": reward["streak_days"] == current_streak
    #             })
                
    #         # Obtener la próxima recompensa (si existe)
    #         next_reward = mongo.database.rewards.find_one(
    #             {"streak_days": {"$gt": current_streak}},
    #             sort=[("streak_days", 1)]
    #         )
            
    #         next_reward_data = None
    #         if next_reward:
    #             next_reward_data = {
    #                 "id": str(next_reward["_id"]),
    #                 "streak_days": next_reward["streak_days"],
    #                 "reward_type": next_reward["reward_type"],
    #                 "reward_value": next_reward["reward_value"],
    #                 "description": next_reward["description"],
    #                 "days_remaining": next_reward["streak_days"] - current_streak
    #             }
                
    #         return jsonify({
    #             "user_id": user_id,
    #             "current_streak": current_streak,
    #             "available_rewards": formatted_rewards,
    #             "next_reward": next_reward_data
    #         }), 200
    #     except Exception as e:
    #         return jsonify({"error": str(e)}), 500

    # Ruta para aplicar una recompensa a un usuario
    @app.route('/redeemed-reward-streak', methods=['POST'])
    def apply_user_reward():            
        data = request.get_json()
        if not data or not "reward_id" in data:
            return jsonify({"error": "ID de recompensa no proporcionado"}), 400
        if not data or not "user_id" in data:
            return jsonify({"error": "Autenticación requerida"}), 401
            
        try:
            # Verificar que el usuario exista
            usuario = mongo.database.usuarios.find_one({"_id": ObjectId(data["user_id"])})
            if not usuario:
                return jsonify({"error": "Usuario no encontrado"}), 404
                
            # Verificar que la recompensa exista
            reward = mongo.database.rewards.find_one({"_id": ObjectId(data["reward_id"])})
            if not reward:
                return jsonify({"error": "Recompensa no encontrada"}), 404
                
            # Verificar que el usuario tenga la racha necesaria
            if usuario.get("login_streak", 0) < reward["streak_days"]:
                return jsonify({"error": "No tienes la racha suficiente para esta recompensa"}), 403
                
            # Crear registro de recompensa aplicada
            applied_reward = {
                "user_id": ObjectId(data["user_id"]),
                "reward_id": ObjectId(data["reward_id"]),
                "streak_days": reward["streak_days"],
                "reward_type": reward["reward_type"],
                "reward_value": reward["reward_value"],
                "description": reward["description"],
                "applied_at": datetime.utcnow(),
                "status": "active"  # active, used, expired
            }
            
            # Verificar si ya tiene esta recompensa activa
            existing_applied = mongo.database.reward_redeem_streak.find_one({
                "user_id": ObjectId(data["user_id"]),
                "reward_id": ObjectId(data["reward_id"]),
                "status": "active"
            })
            
            if existing_applied:
                return jsonify({"error": "Ya tienes esta recompensa activa"}), 400
                
            result = mongo.database.reward_redeem_streak.insert_one(applied_reward)
            
            # Si la recompensa es de tipo "discount", generar un código de descuento
            if reward["reward_type"] == "discount":
                import string
                import random
                discount_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                
                # Actualizar el registro con el código de descuento
                mongo.database.reward_redeem_streak.update_one(
                    {"_id": result.inserted_id},
                    {"$set": {"discount_code": discount_code}}
                )
                
                return jsonify({
                    "message": "Recompensa aplicada con éxito",
                    "reward_id": str(result.inserted_id),
                    "discount_code": discount_code
                }), 201
            
            return jsonify({
                "message": "Recompensa aplicada con éxito",
                "reward_id": str(result.inserted_id)
            }), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # Ruta para listar las recompensas aplicadas a un usuario
    @app.route('/redeemed-reward-streak', methods=['GET'])
    def list_reward_redeem_streak():
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({"error": "Autenticación requerida"}), 401
            
        try:
            # Filtrar por estado si se proporciona
            status_filter = request.args.get('status')
            query = {"user_id": ObjectId(user_id)}
            
            if status_filter:
                query["status"] = status_filter
                
            reward_redeem_streak = list(mongo.database.reward_redeem_streak.find(query).sort("applied_at", -1))
            
            # Formatear las recompensas
            formatted_rewards = []
            for reward in reward_redeem_streak:
                formatted_reward = {
                    "id": str(reward["_id"]),
                    "reward_id": str(reward["reward_id"]),
                    "streak_days": reward["streak_days"],
                    "reward_type": reward["reward_type"],
                    "reward_value": reward["reward_value"],
                    "description": reward["description"],
                    "applied_at": reward["applied_at"].strftime("%Y-%m-%d %H:%M:%S"),
                    "status": reward["status"]
                }
                
                if "discount_code" in reward:
                    formatted_reward["discount_code"] = reward["discount_code"]
                    
                if "expires_at" in reward:
                    formatted_reward["expires_at"] = reward["expires_at"].strftime("%Y-%m-%d %H:%M:%S")
                    
                formatted_rewards.append(formatted_reward)
                
            return jsonify({
                "user_id": user_id,
                "reward_redeem_streak": formatted_rewards
            }), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # Ruta para obtener estadísticas de rachas de usuarios (solo admin)
    @app.route('/admin/streak_stats', methods=['GET'])
    @admin_required
    def get_streak_stats():
        try:
            # Obtener usuarios con las rachas más largas
            top_streaks = list(mongo.database.usuarios.find(
                {},
                {"_id": 1, "nombre": 1, "apellido": 1, "login_streak": 1}
            ).sort("login_streak", -1).limit(10))
            
            # Formatear los resultados
            formatted_streaks = []
            for user in top_streaks:
                formatted_streaks.append({
                    "user_id": str(user["_id"]),
                    "name": user["nombre"] + " " + user["apellido"],
                    "streak": user.get("login_streak", 0)
                })
                
            # Estadísticas generales
            total_users = mongo.database.usuarios.count_documents({})
            users_with_streak = mongo.database.usuarios.count_documents({"login_streak": {"$gt": 0}})
            
            # Distribución de rachas
            streak_distribution = []
            ranges = [(1, 3), (4, 7), (8, 14), (15, 30), (31, float('inf'))]
            
            for start, end in ranges:
                count = mongo.database.usuarios.count_documents({
                    "login_streak": {"$gte": start, "$lte": end if end != float('inf') else 1000000}
                })
                
                streak_distribution.append({
                    "range": f"{start}-{end if end != float('inf') else '+'}",
                    "count": count,
                    "percentage": round((count / total_users) * 100, 2) if total_users > 0 else 0
                })
                
            return jsonify({
                "total_users": total_users,
                "users_with_streak": users_with_streak,
                "streak_percentage": round((users_with_streak / total_users) * 100, 2) if total_users > 0 else 0,
                "top_streaks": formatted_streaks,
                "streak_distribution": streak_distribution
            }), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500