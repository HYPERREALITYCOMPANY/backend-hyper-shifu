from flask_caching import Cache
import datetime

def get_user_from_db(email, cache, mongo):
    """
    Obtiene un usuario desde caché o MongoDB sin refrescar tokens.
    """
    cached_user = cache.get(email)
    if cached_user:
        print(f"[INFO] Usuario {email} encontrado en caché")
        return cached_user

    print(f"[INFO] Usuario {email} no está en caché, consultando MongoDB")
    user = mongo.database.usuarios.find_one({'correo': email})
    if not user:
        print(f"[ERROR] Usuario {email} no encontrado en MongoDB")
        return None

    cache.set(email, user, timeout=1800)  # Cacheamos por 30 min
    print(f"[INFO] Usuario {email} cargado desde MongoDB y cacheado")
    return user