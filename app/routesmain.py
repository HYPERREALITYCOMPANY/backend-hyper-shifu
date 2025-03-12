import os

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
def setup_routes(app, mongo, cache):
    @app.route('/')
    def home():
        return ("Este es el backend del proyecto!!")
    @app.route('/test_redis', methods=['GET'])
    def test_redis():
        try:
            # Intentar obtener un valor de Redis
            value = cache.get('test_key')
            if value is None:
                cache.set('test_key', 'Redis está funcionando', timeout=60)
                return "Conexión a Redis exitosa. Test almacenado en caché.", 200
            else:
                return f"Valor en caché: {value}", 200
        except Exception as e:
            return f"Error de conexión a Redis: {str(e)}", 500
