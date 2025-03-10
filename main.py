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
from app.routes.chatRoutes import setup_routes_chats
from app.routes.executeRoutes import setup_execute_routes
from app.routes.refreshTokens import setup_routes_refresh

load_dotenv()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)
    
    app.config['MONGO_URI'] = os.getenv('MONGO_URI')
    mongo = PyMongo(app)
    mongo = mongo.db.get_collection("Prueba")

    try:
        print("Conexión exitosa a MongoDB!")
    except Exception as e:
        print("Error al conectar con MongoDB:", e)

    setup_routes(app, mongo)
    setup_auth_routes(app, mongo)
    setup_user_routes(app, mongo)
    setup_integrations_routes(app, mongo)
    setup_routes_secretary_posts(app, mongo)
    setup_proxy_routes(app, mongo)
    setup_routes_chats(app, mongo)
    setup_execute_routes(app, mongo)
    setup_routes_refresh(app, mongo)
    return app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # Render asigna un puerto en la variable PORT
    app.run(host="0.0.0.0", port=port, debug=True)
