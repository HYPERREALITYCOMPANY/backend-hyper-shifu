from flask import redirect, Blueprint, url_for, session, request, jsonify
import requests
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dateutil.relativedelta import relativedelta
from requests_oauthlib import OAuth2Session
from config import Config
from urllib.parse import urlencode
import base64 
from bs4 import BeautifulSoup
import unicodedata
import re
import json
from werkzeug.security import generate_password_hash, check_password_hash
import os
import quopri
from flask_pymongo import PyMongo, ObjectId
import openai

# Configuración de OpenAI
openai.api_key = Config.CHAT_API_KEY

# Permitir OAuth sin HTTPS (Solo para desarrollo, NO en producción)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

def setup_routes(app, mongo):
    """
    Configura las rutas del backend
    """
    # Variables Globales
    stateSlack = ""
    idUser = ""
    queryApis = ""
    global last_searchs

    # =========================
    # Rutas de Autenticación
    # =========================
    from routes.auth_routes import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    
    # =========================
    # Rutas de Integraciones
    # =========================
    from routes.integrations_routes import integrations_bp
    app.register_blueprint(integrations_bp, url_prefix='/integrations')
    
    # =========================
    # Rutas de Búsqueda
    # =========================
    from routes.search_routes import search_bp
    app.register_blueprint(search_bp, url_prefix='/search')
    
    # =========================
    # Rutas de AI
    # =========================
    from routes.ai_routes import ai_bp
    app.register_blueprint(ai_bp, url_prefix='/ai')
    
    return app