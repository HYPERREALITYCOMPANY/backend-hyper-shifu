from flask import request, jsonify
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from config import Config
from datetime import datetime
import re
import json
import openai
from flask_caching import Cache
from app.utils.utils import get_user_from_db

openai.api_key=Config.CHAT_API_KEY

def setup_rules_routes(app, mongo, cache):
    cache = Cache(app)
    def post_auto_gmail(condition, action):
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        existing_rule = mongo.database.usuarios.find_one({
            'correo': email,
            'automatizaciones': {
                '$elemMatch': {
                    'service': "Gmail",
                    'condition': condition,
                    'action': action
                }
            }
        })
        if existing_rule:
            return jsonify({"message": "La regla ya existe."}), 200

        gmail_token = user.get('integrations', {}).get('Gmail', {}).get('token')
        if not gmail_token:
            return jsonify({"error": "Token de Gmail no disponible"}), 400

        rule = {
            "service": "Gmail",
            "condition": condition,
            "action": action,
            "active": True,
            "created_at": datetime.utcnow(),
            "last_executed": None
        }
        
        mongo.database.usuarios.update_one(
            {'correo': email},
            {"$push": {"automatizaciones": rule}}
        )

        return jsonify({"message": "Regla automatizada de Gmail guardada exitosamente", "rule": rule})

    
    def post_auto_notion(condition, action):
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        # Verificar si ya existe una regla para Notion con la misma condition y action
        existing_rule = mongo.database.usuarios.find_one({
            'correo': email,
            'automatizaciones': {
                '$elemMatch': {
                    'service': "Notion",
                    'condition': condition,
                    'action': action
                }
            }
        })
        if existing_rule:
            return jsonify({"message": "La regla ya existe."}), 200

        # Obtener el token actual desde la integración del usuario
        notion_token = user.get('integrations', {}).get('Notion', {}).get('token')
        if not notion_token:
            return jsonify({"error": "Token de Notion no disponible"}), 400

        rule = {
            "service": "Notion",
            "condition": condition,
            "action": action,
            "active": True,
            "created_at": datetime.utcnow(),
            "last_executed": None
        }

        mongo.database.usuarios.update_one(
            {'correo': email},
            {"$push": {"automatizaciones": rule}}
        )

        return jsonify({"message": "Regla automatizada de Notion guardada exitosamente", "rule": rule})
    
    def post_auto_slack(condition, action):
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        # Verificar si ya existe una regla para Slack con la misma condition y action
        existing_rule = mongo.database.usuarios.find_one({
            'correo': email,
            'automatizaciones': {
                '$elemMatch': {
                    'service': "Slack",
                    'condition': condition,
                    'action': action
                }
            }
        })
        if existing_rule:
            return jsonify({"message": "La regla ya existe."}), 200

        # Obtener el token actual desde la integración del usuario
        slack_token = user.get('integrations', {}).get('Slack', {}).get('token')
        if not slack_token:
            return jsonify({"error": "Token de Slack no disponible"}), 400

        rule = {
            "service": "Slack",
            "condition": condition,
            "action": action,
            "active": True,
            "created_at": datetime.utcnow(),
            "last_executed": None
        }

        mongo.database.usuarios.update_one(
            {'correo': email},
            {"$push": {"automatizaciones": rule}}
        )

        return jsonify({"message": "Regla automatizada de Slack guardada exitosamente", "rule": rule})
    
    def post_auto_hubspot(condition, action):
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        # Verificar si ya existe una regla para Hubspot con la misma condition y action
        existing_rule = mongo.database.usuarios.find_one({
            'correo': email,
            'automatizaciones': {
                '$elemMatch': {
                    'service': "Hubspot",
                    'condition': condition,
                    'action': action
                }
            }
        })
        if existing_rule:
            return jsonify({"message": "La regla ya existe."}), 200

        # Obtener el token actual desde la integración del usuario
        hubspot_token = user.get('integrations', {}).get('Hubspot', {}).get('token')
        if not hubspot_token:
            return jsonify({"error": "Token de Hubspot no disponible"}), 400

        rule = {
            "service": "Hubspot",
            "condition": condition,
            "action": action,
            "active": True,
            "created_at": datetime.utcnow(),
            "last_executed": None
        }

        mongo.database.usuarios.update_one(
            {'correo': email},
            {"$push": {"automatizaciones": rule}}
        )

        return jsonify({"message": "Regla automatizada de Hubspot guardada exitosamente", "rule": rule})
        
    def post_auto_outlook(condition, action):
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        # Verificar si ya existe una regla para Outlook con la misma condition y action
        existing_rule = mongo.database.usuarios.find_one({
            'correo': email,
            'automatizaciones': {
                '$elemMatch': {
                    'service': "Outlook",
                    'condition': condition,
                    'action': action
                }
            }
        })
        if existing_rule:
            return jsonify({"message": "La regla ya existe."}), 200

        # Obtener el token actual desde la integración del usuario
        outlook_token = user.get('integrations', {}).get('Outlook', {}).get('token')
        if not outlook_token:
            return jsonify({"error": "Token de Outlook no disponible"}), 400

        rule = {
            "service": "Outlook",
            "condition": condition,
            "action": action,
            "active": True,
            "created_at": datetime.utcnow(),
            "last_executed": None
        }

        mongo.database.usuarios.update_one(
            {'correo': email},
            {"$push": {"automatizaciones": rule}}
        )

        return jsonify({"message": "Regla automatizada de Outlook guardada exitosamente", "rule": rule})
    
    def post_auto_clickup(condition, action):
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        # Verificar si ya existe una regla para Clickup con la misma condition y action
        existing_rule = mongo.database.usuarios.find_one({
            'correo': email,
            'automatizaciones': {
                '$elemMatch': {
                    'service': "Clickup",
                    'condition': condition,
                    'action': action
                }
            }
        })
        if existing_rule:
            return jsonify({"message": "La regla ya existe."}), 200

        # Obtener el token actual desde la integración del usuario
        clickup_token = user.get('integrations', {}).get('Clickup', {}).get('token')
        if not clickup_token:
            return jsonify({"error": "Token de Clickup no disponible"}), 400

        rule = {
            "service": "Clickup",
            "condition": condition,
            "action": action,
            "active": True,
            "created_at": datetime.utcnow(),
            "last_executed": None
        }

        mongo.database.usuarios.update_one(
            {'correo': email},
            {"$push": {"automatizaciones": rule}}
        )

        return jsonify({"message": "Regla automatizada de Clickup guardada exitosamente", "rule": rule})

    
    def post_auto_dropbox(condition, action):
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        # Verificar si ya existe una regla para Dropbox con la misma condition y action
        existing_rule = mongo.database.usuarios.find_one({
            'correo': email,
            'automatizaciones': {
                '$elemMatch': {
                    'service': "Dropbox",
                    'condition': condition,
                    'action': action
                }
            }
        })
        if existing_rule:
            return jsonify({"message": "La regla ya existe."}), 200

        # Obtener el token actual desde la integración del usuario
        dropbox_token = user.get('integrations', {}).get('Dropbox', {}).get('token')
        if not dropbox_token:
            return jsonify({"error": "Token de Dropbox no disponible"}), 400

        rule = {
            "service": "Dropbox",
            "condition": condition,
            "action": action,
            "active": True,
            "created_at": datetime.utcnow(),
            "last_executed": None
        }

        mongo.database.usuarios.update_one(
            {'correo': email},
            {"$push": {"automatizaciones": rule}}
        )

        return jsonify({"message": "Regla automatizada de Dropbox guardada exitosamente", "rule": rule})
    
    def post_auto_asana(condition, action):
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        # Verificar si ya existe una regla para Asana con la misma condition y action
        existing_rule = mongo.database.usuarios.find_one({
            'correo': email,
            'automatizaciones': {
                '$elemMatch': {
                    'service': "Asana",
                    'condition': condition,
                    'action': action
                }
            }
        })
        if existing_rule:
            return jsonify({"message": "La regla ya existe."}), 200

        # Obtener el token actual desde la integración del usuario
        asana_token = user.get('integrations', {}).get('Asana', {}).get('token')
        if not asana_token:
            return jsonify({"error": "Token de Asana no disponible"}), 400

        rule = {
            "service": "Asana",
            "condition": condition,
            "action": action,
            "active": True,
            "created_at": datetime.utcnow(),
            "last_executed": None
        }

        mongo.database.usuarios.update_one(
            {'correo': email},
            {"$push": {"automatizaciones": rule}}
        )

        return jsonify({"message": "Regla automatizada de Asana guardada exitosamente", "rule": rule})
 
    def post_auto_googledrive(condition, action):
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        # Verificar si ya existe una regla para GoogleDrive con la misma condition y action
        existing_rule = mongo.database.usuarios.find_one({
            'correo': email,
            'automatizaciones': {
                '$elemMatch': {
                    'service': "GoogleDrive",
                    'condition': condition,
                    'action': action
                }
            }
        })
        if existing_rule:
            return jsonify({"message": "La regla ya existe."}), 200

        # Obtener el token actual desde la integración del usuario
        googledrive_token = user.get('integrations', {}).get('GoogleDrive', {}).get('token')
        if not googledrive_token:
            return jsonify({"error": "Token de Google Drive no disponible"}), 400

        rule = {
            "service": "GoogleDrive",
            "condition": condition,
            "action": action,
            "active": True,
            "created_at": datetime.utcnow(),
            "last_executed": None
        }

        mongo.database.usuarios.update_one(
            {'correo': email},
            {"$push": {"automatizaciones": rule}}
        )

        return jsonify({"message": "Regla automatizada de Google Drive guardada exitosamente", "rule": rule})

    def post_auto_onedrive(condition, action):
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        # Verificar si ya existe una regla para OneDrive con la misma condition y action
        existing_rule = mongo.database.usuarios.find_one({
            'correo': email,
            'automatizaciones': {
                '$elemMatch': {
                    'service': "OneDrive",
                    'condition': condition,
                    'action': action
                }
            }
        })
        if existing_rule:
            return jsonify({"message": "La regla ya existe."}), 200

        # Obtener el token actual desde la integración del usuario
        onedrive_token = user.get('integrations', {}).get('OneDrive', {}).get('token')
        if not onedrive_token:
            return jsonify({"error": "Token de OneDrive no disponible"}), 400

        rule = {
            "service": "OneDrive",
            "condition": condition,
            "action": action,
            "active": True,
            "created_at": datetime.utcnow(),
            "last_executed": None
        }

        mongo.database.usuarios.update_one(
            {'correo': email},
            {"$push": {"automatizaciones": rule}}
        )

        return jsonify({"message": "Regla automatizada de OneDrive guardada exitosamente", "rule": rule})

    def post_auto_teams(condition, action):
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400

        user = get_user_from_db(email, cache, mongo)
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        # Verificar si ya existe una regla para Teams con la misma condition y action
        existing_rule = mongo.database.usuarios.find_one({
            'correo': email,
            'automatizaciones': {
                '$elemMatch': {
                    'service': "Teams",
                    'condition': condition,
                    'action': action
                }
            }
        })
        if existing_rule:
            return jsonify({"message": "La regla ya existe."}), 200

        # Obtener el token actual desde la integración del usuario
        teams_token = user.get('integrations', {}).get('Teams', {}).get('token')
        if not teams_token:
            return jsonify({"error": "Token de Teams no disponible"}), 400

        rule = {
            "service": "Teams",
            "condition": condition,
            "action": action,
            "active": True,
            "created_at": datetime.utcnow(),
            "last_executed": None
        }

        mongo.database.usuarios.update_one(
            {'correo': email},
            {"$push": {"automatizaciones": rule}}
        )

        return jsonify({"message": "Regla automatizada de Teams guardada exitosamente", "rule": rule})
    
    return {
        "post_auto_gmail": post_auto_gmail,
        "post_auto_hubspot": post_auto_hubspot,
        "post_auto_outlook": post_auto_outlook,
        "post_auto_clickup": post_auto_clickup,
        "post_auto_dropbox": post_auto_dropbox,
        "post_auto_asana": post_auto_asana,
        "post_auto_googledrive": post_auto_googledrive,
        "post_auto_onedrive": post_auto_onedrive,
        "post_auto_teams": post_auto_teams,
        "post_auto_slack": post_auto_slack,
        "post_auto_notion": post_auto_notion
    }