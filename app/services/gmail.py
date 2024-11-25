from flask import redirect, Blueprint, url_for, session, request, jsonify
import requests
from requests_oauthlib import OAuth2Session
from config import Config
from urllib.parse import urlencode
import base64
from flask_pymongo import PyMongo, ObjectId
import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

def auth_gmail():
    scope = [
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/userinfo.email',
        'https://www.googleapis.com/auth/userinfo.profile'
    ]

    gmail = OAuth2Session(Config.GMAIL_CLIENT_ID, 
                          redirect_uri='https://neuron-hyper.vercel.app/auth/gmail/callback',
                          scope=scope)

    authorization_url, state = gmail.authorization_url('https://accounts.google.com/o/oauth2/auth',
                                                       access_type="online", prompt="consent")
    session['gmail_state'] = state

    return redirect(authorization_url)


def auth_gmail_callback(mongo):
    if 'user_id' not in session:
        return jsonify({"error": "Usuario no autenticado"}), 401

    user_id = session['user_id']
    code = request.args.get('code')
    if not code:
        return jsonify({"error": "El parámetro 'code' falta en la respuesta"}), 400

    try:
        token_url = 'https://oauth2.googleapis.com/token'
        payload = {
            'code': code,
            'client_id': Config.GMAIL_CLIENT_ID,
            'client_secret': Config.GMAIL_CLIENT_SECRET,
            'redirect_uri': 'https://neuron-hyper.vercel.app/auth/gmail/callback',
            'grant_type': 'authorization_code'
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        response = requests.post(token_url, data=payload, headers=headers)
        token_data = response.json()

        if response.status_code != 200:
            return jsonify({"error": "Error al obtener el token de Gmail", "details": token_data}), response.status_code

        mongo.db.usuarios.update_one(
            {"_id": ObjectId(user_id)},
            {"$push": {"integrations": {"platform": "gmail", "token": token_data}}}
        )

        return jsonify({"message": "Integración de Gmail guardada exitosamente", "integration": token_data}), 200
    except Exception as e:
        return jsonify({"error": f"Error al procesar el token de Gmail: {str(e)}"}), 500

def auth_google_drive():
    scope = [
        'https://www.googleapis.com/auth/drive.readonly',
        'https://www.googleapis.com/auth/userinfo.email',
        'https://www.googleapis.com/auth/userinfo.profile'
    ]

    google = OAuth2Session(
        Config.GOOGLE_CLIENT_ID,
        redirect_uri=Config.REDIRECT_URI,
        scope=scope
    )

    authorization_url, state = google.authorization_url(
        'https://accounts.google.com/o/oauth2/auth',
        access_type="offline",
        prompt="consent"
    )
    session['google_state'] = state
    return redirect(authorization_url)

# Ruta para el callback
def auth_google_drive_callback():
    if 'google_state' not in session:
        return jsonify({"error": "Estado de OAuth faltante en la sesión"}), 400

    google = OAuth2Session(
        Config.GOOGLE_CLIENT_ID,
        state=session['google_state'],
        redirect_uri=Config.REDIRECT_URI
    )
    try:
        token = google.fetch_token(
            'https://accounts.google.com/o/oauth2/token',
            client_secret=Config.GOOGLE_CLIENT_SECRET,
            authorization_response=request.url
        )
        session['google_token'] = token
        return jsonify(token)
    except Exception as e:
        return jsonify({"error": f"Error al obtener el token: {str(e)}"}), 500