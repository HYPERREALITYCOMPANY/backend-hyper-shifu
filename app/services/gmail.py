from flask import redirect, Blueprint, url_for, session, request, jsonify
import requests
from requests_oauthlib import OAuth2Session
from config import Config
from urllib.parse import urlencode
import base64 
import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

def auth_gmail():
    scope = [
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/userinfo.email',
        'https://www.googleapis.com/auth/userinfo.profile'
    ]

    gmail = OAuth2Session(Config.GMAIL_CLIENT_ID, 
                          redirect_uri='https://jk6rq3rx-5000.use2.devtunnels.ms/auth/gmail/callback',
                          scope=scope)

    authorization_url, state = gmail.authorization_url('https://accounts.google.com/o/oauth2/auth',
                                                       access_type="online", prompt="consent")
    session['gmail_state'] = state

    return redirect(authorization_url)


def auth_gmail_callback():
    if 'gmail_state' not in session:
        return jsonify({"error": "Estado de OAuth faltante en la sesión"}), 400

    gmail = OAuth2Session(Config.GMAIL_CLIENT_ID, state=session['gmail_state'], 
                          redirect_uri='https://jk6rq3rx-5000.use2.devtunnels.ms/auth/gmail/callback')
    try:
        token = gmail.fetch_token('https://accounts.google.com/o/oauth2/token',
                                  client_secret=Config.GMAIL_CLIENT_SECRET,
                                  authorization_response=request.url)
        session['gmail_token'] = token
        return jsonify(token)
    except Exception as e:
        return jsonify({"error": f"Error al obtener el token: {str(e)}"}), 500