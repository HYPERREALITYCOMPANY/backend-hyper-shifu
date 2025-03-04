from flask import Flask
from config import Config
from app.routmain import setup_routes
from flask_pymongo import PyMongo, ObjectId
from flask_cors import CORS
import os
from dotenv import load_dotenv
from app.routes.authRoutes import setup_auth_routes

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

    setup_auth_routes(app, mongo)
    setup_routes(app, mongo)
    return app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # Render asigna un puerto en la variable PORT
    app.run(host="0.0.0.0", port=port, debug=True)
