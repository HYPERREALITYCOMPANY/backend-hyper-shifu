from flask import redirect, Blueprint, url_for, session, request, jsonify
import requests
from requests_oauthlib import OAuth2Session
from config import Config
from urllib.parse import urlencode
import base64 
from flask_pymongo import PyMongo, ObjectId
import os
import traceback
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

def notion_auth():
        notion_auth_url = "https://api.notion.com/v1/oauth/authorize"
        query_params = {
            'client_id': Config.NOTION_CLIENT_ID,
            'redirect_uri': "https://neuron-hyper.vercel.app/notion/callback",
            'response_type': 'code',
        }
        auth_url = f"{notion_auth_url}?{urlencode(query_params)}"

        return redirect(f"{notion_auth_url}?{urlencode(query_params)}")

def notion_callback(mongo, idUser):
    usuario = mongo.db.usuarios.find_one({"_id": ObjectId(idUser)})
    if not usuario:
         return jsonify({"error": "No se encontró el usuario en la base de datos"}), 404
    try:
        error = request.args.get('error')
        if error:
            return jsonify({"error": f"Notion devolvió un error: {error}"}), 400

        code = request.args.get('code')
        if not code:
            return jsonify({"error": "El parámetro 'code' falta en la respuesta"}), 400


        token_url = "https://api.notion.com/v1/oauth/token"
        token_data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': "https://neuron-hyper.vercel.app/notion/callback",
        }

        client_credentials = f"{Config.NOTION_CLIENT_ID}:{Config.NOTION_CLIENT_SECRET}"
        encoded_credentials = base64.b64encode(client_credentials.encode()).decode()

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {encoded_credentials}',
            "Notion-Version": "2022-06-28",
        }

        encoded_data = urlencode(token_data)

        response = requests.post(token_url, data=encoded_data, headers=headers)

        if response.status_code != 200:
            return jsonify({"error": "Error al obtener el token de Notion", "details": response.json()}), response.status_code

        access_token_data = response.json()
        access_token = access_token_data.get('access_token')
        if not access_token:
            return jsonify({"error": "No se pudo obtener el token de acceso"}), 400
        mongo.db.usuarios.update_one(
            {"_id": ObjectId(idUser)},
            {"$push": {"integrations": {"platform": "notion", "token": access_token_data}}}
        )

        return jsonify({"message": "Integración de Notion guardada exitosamente", "integration": access_token_data}), 200

    except Exception as e:
        print(f"Error: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": f"Error al procesar el token de Notion: {str(e)}"}), 500