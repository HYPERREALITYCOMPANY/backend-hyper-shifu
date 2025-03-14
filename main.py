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

    setup_routes(app, mongo, cache)
    setup_auth_routes(app, mongo, cache)
    setup_user_routes(app, mongo, cache)
    setup_integrations_routes(app, mongo, cache)
    setup_routes_secretary_posts(app, mongo, cache)
    setup_proxy_routes(app, mongo, cache)
    setup_routes_chats(app, mongo, cache)
    setup_execute_routes(app, mongo, cache)
    setup_routes_refresh(app, mongo, cache)
    
    return app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # Render asigna un puerto en la variable PORT
    app.run(host="0.0.0.0", port=port, debug=True)
