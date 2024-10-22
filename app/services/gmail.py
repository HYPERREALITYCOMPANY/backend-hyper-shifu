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
                              redirect_uri=url_for('auth_gmail_callback', _external=True),
                              scope=scope)
    
        authorization_url, state = gmail.authorization_url('https://accounts.google.com/o/oauth2/auth',
                                                           access_type="online", prompt="consent")

        session['oauth_state'] = state
    
        return redirect(authorization_url)

def auth_gmail_callback():
        gmail = OAuth2Session(Config.GMAIL_CLIENT_ID, state=session['oauth_state'], 
                              redirect_uri=url_for('auth_gmail_callback', _external=True))
        token = gmail.fetch_token('https://accounts.google.com/o/oauth2/token',
                                  client_secret=Config.GMAIL_CLIENT_SECRET,
                                  authorization_response=request.url)
        session['gmail_token'] = token
        return jsonify(token)