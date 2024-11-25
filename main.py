from flask import Flask
from config import Config
from app.routes import setup_routes
from pyngrok import ngrok
from flask_pymongo import PyMongo, ObjectId
from flask_cors import CORS
import os
from dotenv import load_dotenv
load_dotenv()
def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    CORS(app, resources={r"/*": {"origins": "*"}})
    app.config['MONGO_URI'] = os.getenv('MONGO_URI')
    mongo = PyMongo(app)
    try:
        # Verificamos que podemos acceder a la base de datos
        mongo.db.command('ping')  # Esto hace una consulta simple a MongoDB
        print("Conexión exitosa a MongoDB!")
    except Exception as e:
        print("Error al conectar con MongoDB:", e)
    setup_routes(app, mongo)

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
