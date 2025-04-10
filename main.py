from flask import Flask
from config import Config
from app.routesmain import setup_routes
from flask_pymongo import PyMongo, ObjectId
from flask_cors import CORS
import os
from dotenv import load_dotenv
from app.routes.authRoutes import setup_auth_routes
from app.routes.userRoutes import setup_user_routes
from app.routes.integrationRoutes import setup_integrations_routes
from app.routes.secretaryPostRoutes import setup_routes_secretary_posts
from app.routes.secretaryGetRoutes import setup_routes_secretary_gets
from app.routes.proxyRoutes import setup_proxy_routes
from app.routes.core.principal_ia import setup_routes_chats
from app.routes.executeRoutes import setup_execute_routes
from app.routes.refreshTokens import setup_routes_refresh
from app.routes.referralsRoutes import setup_referrals_routes
from app.routes.apis.gmail.interpreter_gmail import gmail_chat
from app.routes.apis.outlook.interpreter_outlook import outlook_chat
from app.routes.apis.asana.interpreter_asana import asana_chat
from app.routes.apis.clickup.interpreter_clickup import clickup_chat
from app.routes.apis.dropbox.interpreter_dropbox import dropbox_chat

from flask_caching import Cache  # Importar Flask-Caching

load_dotenv()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Configurar Redis y caché
    app.config['CACHE_TYPE'] = 'RedisCache'
    app.config['CACHE_REDIS_URL'] = os.getenv("REDIS_URL")  # Obtén la URL de Redis desde las variables de entorno
    app.config['CACHE_DEFAULT_TIMEOUT'] = 1800  # Tiempo de expiración (30 minutos)
    
    cache = Cache(app)  # Inicializa el objeto de caché
    CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)
    
    # Configurar MongoDB
    app.config['MONGO_URI'] = os.getenv('MONGO_URI')
    mongo_client = PyMongo(app).db  # Mantiene la conexión
    mongo = mongo_client["Prueba"]  # Obtiene directamente la colección
    
    try:
        print("Conexión exitosa a MongoDB!")
    except Exception as e:
        print("Error al conectar con MongoDB:", e)
    
    setup_routes(app, mongo)
    setup_auth_routes(app, mongo, cache)
    setup_user_routes(app, mongo, cache)
    refresh_functions = setup_routes_refresh(app, mongo, cache)
    setup_integrations_routes(app, mongo, cache)
    setup_routes_secretary_posts(app, mongo, cache, refresh_functions)
    setup_proxy_routes(app, mongo, cache)
    setup_routes_chats(app, mongo, cache, refresh_functions)
    setup_execute_routes(app, mongo, cache, refresh_functions)
    setup_referrals_routes(app, mongo, cache)
    gmail_chat(app, mongo, cache, refresh_functions)
    outlook_chat(app, mongo, cache, refresh_functions)
    # notion_chat(app, mongo, cache, refresh_functions)
    clickup_chat(app, mongo, cache, refresh_functions)
    # hubspot_chat(app, mongo, cache, refresh_functions)
    asana_chat(app, mongo, cache, refresh_functions)
    # onedrive_chat(app, mongo, cache, refresh_functions)
    # drive_chat(app, mongo, cache, refresh_functions)
    # slack_chat(app, mongo, cache, refresh_functions)
    dropbox_chat(app, mongo, cache, refresh_functions)
    
    return app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)