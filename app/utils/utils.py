from flask_caching import Cache

def get_user_from_db(email, cache, mongo):
    cached_user = cache.get(email)
    if cached_user:
        return cached_user  # Devuelve el usuario desde caché

    user = mongo.database.usuarios.find_one({'correo': email})
    if user:
        cache.set(email, user, timeout=1800)  # Guarda en caché por 30 minutos

    return user