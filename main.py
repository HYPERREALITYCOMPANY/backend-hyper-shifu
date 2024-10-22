from flask import Flask
from config import Config
from app.routes import setup_routes

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    setup_routes(app)

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
