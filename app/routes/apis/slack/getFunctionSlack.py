import re
import requests

def handle_get_request(accion, solicitud, email, user):
    if not user:
        return {"solicitud": "GET", "result": {"error": "¡Órale! No te encontré en la base, ¿seguro que estás registrado?"}}, 404

    slack_integration = user.get('integrations', {}).get('slack', None)
    if not slack_integration or not slack_integration.get('token'):
        return {"solicitud": "GET", "result": {"error": "¡Ey! No tengo tu token de Slack, ¿me das permisos otra vez?"}}, 400
    slack_token = slack_integration.get('token')

    headers = {'Authorization': f"Bearer {slack_token}", 'Content-Type': 'application/json'}
    url = "https://slack.com/api/conversations.history"

    if not accion:
        return {"solicitud": "GET", "result": {"error": "¡Qué pasa, compa! No me dijiste qué hacer, ¿qué busco?"}}, 400
    if not solicitud:
        return {"solicitud": "GET", "result": {"error": f"¡Falta algo, papu! Necesito más detalles para buscar, ¿qué quieres ver?"}}, 400

    solicitud = solicitud.lower()

    try:
        if accion == "buscar":
            if "mensajes" in solicitud or "mensaje" in solicitud:
                channel_match = re.search(r'del canal\s*#?(\w+)', solicitud, re.IGNORECASE)
                user_match = re.search(r'de\s+(\w+)', solicitud, re.IGNORECASE)
                channel_name = channel_match.group(1) if channel_match else None
                user_name = user_match.group(1) if user_match and not channel_match else None

                if not channel_name:
                    return {"solicitud": "GET", "result": {"error": "¡Ey! ¿De qué canal quieres los mensajes? Usa #nombre 😄"}}, 400

                # Placeholder: En producción, usa conversations.list para obtener el ID del canal
                channel_id = f"C{channel_name.upper()}"
                params = {"channel": channel_id, "limit": 5}
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()

                messages = response.json().get('messages', [])
                if not messages:
                    return {"solicitud": "GET", "result": {"message": f"📭 No encontré mensajes en #{channel_name}, ¿será que está vacío?"}}, 200

                if user_name:
                    messages = [msg for msg in messages if msg.get("user", "").lower() == user_name.lower() or user_name.lower() in msg.get("text", "").lower()]
                    search_type = f"mensajes de '{user_name}' en #{channel_name}"
                else:
                    search_type = f"mensajes en #{channel_name}"

                if not messages:
                    return {"solicitud": "GET", "result": {"message": f"📭 No encontré {search_type}, ¿probamos algo más?"}}, 200

                results = [
                    {
                        "user": msg.get("user", "Unknown"),
                        "text": msg["text"][:200] + "..." if len(msg["text"]) > 200 else msg["text"],
                        "ts": msg["ts"]
                    } for msg in messages
                ]
                return {"solicitud": "GET", "result": {"message": f"¡Órale, papu! Encontré {len(results)} {search_type} 💬", "data": results}}, 200

            else:
                return {"solicitud": "GET", "result": {"error": "¡Uy! Solo puedo buscar mensajes por ahora, ¿qué tal eso? 😅"}}, 400

        else:
            return {"solicitud": "GET", "result": {"error": f"¡No entendí qué quieres con '{accion}'! Usa algo pa’ buscar, ¿va?"}}, 400

    except requests.RequestException as e:
        return {"solicitud": "GET", "result": {"error": f"¡Ay, qué mala onda! Falló la conexión con Slack: {str(e)}"}}, 500
    except Exception as e:
        return {"solicitud": "GET", "result": {"error": f"¡Uy, se puso feo! Error inesperado: {str(e)}"}}, 500