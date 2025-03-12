import os

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
def setup_routes(app, mongo, cache):
    @app.route('/')
    def home():
        return ("Este es el backend del proyecto!!")
