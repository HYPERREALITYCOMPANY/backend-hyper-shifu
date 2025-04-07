from datetime import datetime
from flask import request, jsonify
from flask_pymongo import ObjectId
from functools import wraps

def setup_reward_routes(app, mongo):

    # Middleware de admin usando user_id desde el body
    def admin_required(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user_id = request.json.get("id") if request.json else None
            if not user_id:
                return jsonify({"error": "user_id requerido"}), 400

            user = mongo.database.usuarios.find_one({"_id": ObjectId(user_id)})
            print("user-found: ", user)
            if not user or user.get("rol") != "admin":
                return jsonify({"error": "Acceso denegado, no eres admin"}), 403

            request.user = user  # Guardamos user en request si es necesario luego
            return f(*args, **kwargs)
        return decorated

    # Crear recompensa (solo admin)
    @app.route('/rewards', methods=['POST'])
    @admin_required
    def create_reward():
        data = request.json
        reward = {
            "name": data.get("name"),
            "description": data.get("description"),
            "max_redemptions_per_user": data.get("max_redemptions_per_user", 1),
            "required_referrals": data.get("required_referrals", 0),
            "created_at": datetime.utcnow()
        }
        result = mongo.database.rewards.insert_one(reward)
        reward["_id"] = str(result.inserted_id)
        return jsonify(reward), 201

    # Ver todas las recompensas (todos los usuarios)
    @app.route('/rewards', methods=['GET'])
    def get_rewards():
        rewards = list(mongo.database.rewards.find())
        for r in rewards:
            r["_id"] = str(r["_id"])
        return jsonify(rewards)

    # Editar recompensa (solo admin)
    @app.route('/rewards/<reward_id>', methods=['PUT'])
    @admin_required
    def update_reward(reward_id):
        data = request.json
        update_fields = {k: v for k, v in data.items() if k in ["name", "description", "max_redemptions_per_user", "required_referrals"]}
        mongo.database.rewards.update_one({"_id": ObjectId(reward_id)}, {"$set": update_fields})
        return jsonify({"message": "Recompensa actualizada"})

    # Eliminar recompensa (solo admin)
    @app.route('/rewards/<reward_id>', methods=['DELETE'])
    @admin_required
    def delete_reward(reward_id):
        mongo.database.rewards.delete_one({"_id": ObjectId(reward_id)})
        return jsonify({"message": "Recompensa eliminada"})

    # Canjear recompensa (por user_id en el body)
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

        if user_doc.get("count_referrals", 0) < reward["required_referrals"]:
            return jsonify({"error": "No tienes suficientes referidos para esta recompensa"}), 400

        count = mongo.database.reward_redeem.count_documents({
            "user_id": ObjectId(user_id),
            "reward_id": ObjectId(reward_id)
        })

        if count >= reward["max_redemptions_per_user"]:
            return jsonify({"error": "Ya has canjeado esta recompensa el número máximo de veces"}), 400

        mongo.database.reward_redeem.insert_one({
            "user_id": ObjectId(user_id),
            "reward_id": ObjectId(reward_id),
            "redeemed_at": datetime.utcnow()
        })

        return jsonify({"message": "Recompensa canjeada correctamente"}), 200
