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
from app.routes.core.principal_ia import setup_chat
from app.routes.executeRoutes import setup_execute_routes
from app.routes.refreshTokens import setup_routes_refresh
from app.routes.referralsRoutes import setup_referrals_routes
from app.routes.apis.gmail.interpreter_gmail import setup_gmail_chat  # Import the setup function
from app.routes.apis.outlook.interpreter_outlook import setup_outlook_chat  # Assuming similar refactoring
from app.routes.apis.asana.interpreter_asana import setup_asana_chat
from app.routes.apis.clickup.interpreter_clickup import setup_clickup_chat
from app.routes.apis.dropbox.interpreter_dropbox import setup_dropbox_chat
from app.routes.apis.drive.interpreter_drive import setup_drive_chat
from app.routes.apis.hubspot.interpreter_hubspot import setup_hubspot_chat
from app.routes.apis.notion.interpreter_notion import setup_notion_chat
from app.routes.apis.onedrive.interpreter_onedrive import setup_onedrive_chat
from app.routes.apis.slack.interpreter_slack import setup_slack_chat
from app.routes.core.multitask.interpreter_multitask import setup_multitask_chat

from flask_caching import Cache

load_dotenv()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Configurar Redis y caché
    app.config['CACHE_TYPE'] = 'RedisCache'
    app.config['CACHE_REDIS_URL'] = os.getenv("REDIS_URL")
    app.config['CACHE_DEFAULT_TIMEOUT'] = 1800
    
    cache = Cache(app)
    CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)
    
    # Configurar MongoDB
    app.config['MONGO_URI'] = os.getenv('MONGO_URI')
    mongo_client = PyMongo(app).db
    mongo = mongo_client["Prueba"]
    
    try:
        print("Conexión exitosa a MongoDB!")
    except Exception as e:
        print("Error al conectar con MongoDB:", e)
    
    # Register routes
    setup_routes(app, mongo)
    setup_auth_routes(app, mongo, cache)
    setup_user_routes(app, mongo, cache)
    refresh_functions = setup_routes_refresh(app, mongo, cache)
    setup_integrations_routes(app, mongo, cache)
    setup_routes_secretary_posts(app, mongo, cache, refresh_functions)
    setup_proxy_routes(app, mongo, cache)
    setup_chat(app, mongo, cache, refresh_functions)
    setup_multitask_chat(app, mongo, cache, refresh_functions)
    setup_execute_routes(app, mongo, cache, refresh_functions)
    setup_referrals_routes(app, mongo, cache)
    
    # Register API-specific chat routes
    setup_gmail_chat(app, mongo, cache, refresh_functions)
    setup_outlook_chat(app, mongo, cache, refresh_functions)
    setup_notion_chat(app, mongo, cache, refresh_functions)
    setup_clickup_chat(app, mongo, cache, refresh_functions)
    setup_hubspot_chat(app, mongo, cache, refresh_functions)
    setup_asana_chat(app, mongo, cache, refresh_functions)
    setup_onedrive_chat(app, mongo, cache, refresh_functions)
    setup_drive_chat(app, mongo, cache, refresh_functions)
    setup_slack_chat(app, mongo, cache, refresh_functions)
    setup_dropbox_chat(app, mongo, cache, refresh_functions)
    
    return app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)