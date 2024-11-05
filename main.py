from flask import Flask
from config import Config
from app.routes import setup_routes
from pyngrok import ngrok
import os

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    setup_routes(app)

    # if os.environ.get('FLASK_ENV') == 'development':
    #     public_url = ngrok.connect(5000)
    #     print(f"ngrok public URL: {public_url}")
    #     app.config['BASE_URL'] = public_url

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
