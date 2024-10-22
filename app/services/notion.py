from flask import redirect, Blueprint, url_for, session, request, jsonify
import requests
from requests_oauthlib import OAuth2Session
from config import Config
from urllib.parse import urlencode
import base64 
import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

def notion_auth():
        notion_auth_url = "https://api.notion.com/v1/oauth/authorize"
        query_params = {
            'client_id': Config.NOTION_CLIENT_ID,
            'redirect_uri': "http://localhost:5000/notion/callback",
            'response_type': 'code',
        }
        return redirect(f"{notion_auth_url}?{urlencode(query_params)}")

def notion_callback():
        error = request.args.get('error')
        if error:
            return jsonify({"error": f"Notion devolvió un error: {error}"}), 400

        code = request.args.get('code')
        print(f"Código recibido: {code}")

        token_url = "https://api.notion.com/v1/oauth/token"

        token_data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': "http://localhost:5000/notion/callback",
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

        print(f"Status code: {response.status_code}")
        print(f"Response: {response.json()}")

        if response.status_code != 200:
            return jsonify({"error": "Error al obtener el token de Notion", "details": response.json()}), response.status_code

        access_token_data = response.json()

        session['access_token'] = access_token_data.get('access_token')
        print(f"Access token: {session['access_token']}")  

        if not session['access_token']:
            return jsonify({"error": "No se pudo obtener el token de acceso"}), 400

        return jsonify(session['access_token'])