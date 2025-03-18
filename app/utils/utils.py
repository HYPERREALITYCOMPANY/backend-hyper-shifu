from flask_caching import Cache
import datetime

def get_user_from_db(email, cache, mongo, refresh_tokens=False):
    """
    Obtiene un usuario desde caché o MongoDB. Refresca tokens solo si se indica explícitamente.
    """
    cached_user = cache.get(email)
    if cached_user:
        print(f"[INFO] Usuario {email} encontrado en caché")
        if refresh_tokens and needs_token_refresh(cached_user):
            print(f"[INFO] Refrescando tokens para {email} desde caché")
            updated_user = refresh_all_user_tokens(email, mongo, cache)
            if updated_user:
                return updated_user
        return cached_user

    print(f"[INFO] Usuario {email} no está en caché, consultando MongoDB")
    user = mongo.database.usuarios.find_one({'correo': email})
    if not user:
        print(f"[ERROR] Usuario {email} no encontrado en MongoDB")
        return None

    # Solo refrescamos tokens si se pide explícitamente
    if refresh_tokens:
        print(f"[INFO] Refrescando todos los tokens para {email}")
        user = refresh_all_user_tokens(email, mongo, cache) or user
    else:
        print(f"[INFO] No se pidieron refrescos de tokens para {email}")

    cache.set(email, user, timeout=1800)  # Cacheamos por 30 min
    return user

def needs_token_refresh(user):
    """
    Determina si algún token del usuario necesita ser refrescado (1 hora de expiración).
    """
    integrations = user.get("integrations", {})
    for integration_name, data in integrations.items():
        timestamp_str = data.get("timestamp")
        if not timestamp_str:
            continue
        try:
            token_time = datetime.datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            time_diff = (datetime.datetime.utcnow() - token_time).total_seconds()
            if time_diff > 3600:  # 1 hora
                print(f"[INFO] Token de {integration_name} vencido (diff: {time_diff}s)")
                return True
        except ValueError:
            print(f"[WARNING] Timestamp inválido para {integration_name}: {timestamp_str}")
    return False

def refresh_all_user_tokens(email, mongo, cache):
    """
    Refresca TODOS los tokens disponibles del usuario y actualiza la caché.
    """
    try:
        from app.routes.refreshTokens import setup_routes_refresh
        
        # Obtenemos las funciones de refresco
        refresh_functions = setup_routes_refresh(None, mongo, cache)
        get_refresh_tokens_from_db = refresh_functions["get_refresh_tokens_from_db"]
        refresh_tokens = refresh_functions["refresh_tokens"]
        
        # Obtenemos todos los refresh tokens
        refresh_tokens_dict = get_refresh_tokens_from_db(email)
        if not refresh_tokens_dict:
            print(f"[INFO] No hay refresh tokens disponibles para {email}")
            return None

        print(f"[INFO] Refrescando todos los tokens para {email}")
        refreshed_tokens, errors = refresh_tokens(refresh_tokens_dict, email)
        
        if refreshed_tokens:
            print(f"[INFO] Tokens refrescados exitosamente: {list(refreshed_tokens.keys())}")
            updated_user = mongo.database.usuarios.find_one({'correo': email})
            cache.set(email, updated_user, timeout=1800)
            return updated_user
        elif errors:
            print(f"[WARNING] Errores al refrescar tokens: {errors}")
            return None
    except Exception as e:
        print(f"[ERROR] Error refrescando tokens para {email}: {e}")
        return None