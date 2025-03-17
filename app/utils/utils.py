from flask_caching import Cache
import datetime

def get_user_from_db(email, cache, mongo):
    cached_user = cache.get(email)
    if cached_user:
        print("User found in cache!")
        # Verificar si algún token está vencido
        if needs_token_refresh(cached_user):
            print("Token possibly expired, refreshing...")
            updated_user = refresh_all_user_tokens(email, mongo, cache)  # Refresh ALL tokens
            if updated_user:
                return updated_user
        return cached_user  # Si no necesita refresco, devolver el usuario en caché

    print("User not found in cache, querying MongoDB...")
    user = mongo.database.usuarios.find_one({'correo': email})
    if user:
        print("User found in MongoDB, refreshing ALL tokens...")
        # Always refresh all tokens when creating a new cache entry
        user = refresh_all_user_tokens(email, mongo, cache)
        if not user:  # If refresh failed, use original user
            user = mongo.database.usuarios.find_one({'correo': email})
        
        cache.set(email, user, timeout=1800)  # Guarda en caché por 30 minutos
        print("User saved to cache with refreshed tokens!")
    return user

def needs_token_refresh(user):
    """
    Determina si algún token del usuario necesita ser refrescado.
    Por ejemplo, si el timestamp es mayor a 1 hora (3600 segundos).
    """
    integrations = user.get("integrations", {})
    for integration_name, data in integrations.items():
        timestamp_str = data.get("timestamp")
        if not timestamp_str:
            continue
        try:
            token_time = datetime.datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            time_diff = (datetime.datetime.utcnow() - token_time).total_seconds()
            if time_diff > 3600:  # 1 hora como ejemplo de expiración
                print(f"Token de {integration_name} vencido (diff: {time_diff}s)")
                return True
        except ValueError:
            print(f"Timestamp inválido para {integration_name}: {timestamp_str}")
    return False

def refresh_all_user_tokens(email, mongo, cache):
    """
    Refresca TODOS los tokens disponibles del usuario y actualiza la caché.
    """
    try:
        # Import these functions here to avoid circular imports
        from app.routes.refreshTokens import setup_routes_refresh
        
        # Get the refresh token functions
        refresh_functions = setup_routes_refresh(None, mongo, cache)
        get_refresh_tokens_from_db = refresh_functions["get_refresh_tokens_from_db"]
        refresh_tokens = refresh_functions["refresh_tokens"]
        
        # Get all available refresh tokens
        refresh_tokens_dict = get_refresh_tokens_from_db(email)
        if not refresh_tokens_dict:
            print("No refresh tokens available for this user.")
            return None

        # Refresh ALL tokens without specifying a specific integration
        print(f"Refreshing ALL tokens for user {email}")
        refreshed_tokens, errors = refresh_tokens(refresh_tokens_dict, email)
        
        if refreshed_tokens:
            print(f"Successfully refreshed tokens: {list(refreshed_tokens.keys())}")
            # Get the updated user record
            updated_user = mongo.database.usuarios.find_one({'correo': email})
            # Update the cache
            cache.set(email, updated_user, timeout=1800)
            return updated_user
        elif errors:
            print(f"Errors refreshing tokens: {errors}")
            return None
    except Exception as e:
        print(f"Error refreshing tokens for {email}: {e}")
        return None