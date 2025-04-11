import re
import requests

def handle_post_request(accion, solicitud, email, user):
    if not user:
        return {"solicitud": "POST", "result": {"error": "No te encontré en la base de datos, ¿estás seguro de que estás registrado?"}}, 404

    slack_integration = user.get('integrations', {}).get('slack', None)
    if not slack_integration or not slack_integration.get('token'):
        return {"solicitud": "POST", "result": {"error": "No tengo tu token de Slack, ¿puedes darme permisos nuevamente?"}}, 400
    slack_token = slack_integration.get('token')

    headers = {"Authorization": f"Bearer {slack_token}", "Content-Type": "application/json"}

    if not accion:
        return {"solicitud": "POST", "result": {"error": "No me indicaste qué hacer, ¿en qué puedo ayudarte?"}}, 400
    if not solicitud:
        return {"solicitud": "POST", "result": {"error": "Necesito más detalles para proceder, ¿qué te gustaría hacer?"}}, 400

    solicitud = solicitud.lower()
    try:
        # Enviar mensaje
        if accion == "enviar":
            match = re.search(r'mensaje\s*(?:al canal\s*#?(\w+))?\s*(.+)?', solicitud, re.IGNORECASE)
            if not match:
                return {"solicitud": "POST", "result": {"message": "📩 ¡Falta algo! Dime a qué canal enviar el mensaje y qué decir (ej. 'enviar mensaje al canal #general hola') 🚀"}}, 200
            channel_name = match.group(1) or None
            message_text = match.group(2) or None

            if not channel_name or not message_text:
                return {"solicitud": "POST", "result": {"error": "¡Falta algo! Necesito el canal (#nombre) y el texto del mensaje 📝"}}, 400

            channel_id = f"C{channel_name.upper()}"  # Placeholder, en producción usa conversations.list
            url = "https://slack.com/api/chat.postMessage"
            payload = {"channel": channel_id, "text": message_text}
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return {"solicitud": "POST", "result": {"message": f"💬 ¡Mensaje enviado a #{channel_name} con éxito! 🚀"}}, 200

        # Actualizar mensaje
        elif accion == "actualizar":
            match = re.search(r'mensaje\s*en\s*#?(\w+)\s*con\s*(.+)', solicitud, re.IGNORECASE)
            if not match:
                return {"solicitud": "POST", "result": {"message": "📩 ¡Falta algo! Dime qué mensaje actualizar y en qué canal (ej. 'actualizar mensaje en #general con hola') 🚀"}}, 200
            channel_name = match.group(1).strip()
            new_text = match.group(2).strip()

            channel_id = f"C{channel_name.upper()}"  # Placeholder
            url = "https://slack.com/api/chat.update"
            # Nota: En producción, necesitas el timestamp (ts) del mensaje original
            payload = {"channel": channel_id, "ts": "simulated_ts", "text": new_text}
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return {"solicitud": "POST", "result": {"message": f"✨ ¡Mensaje actualizado en #{channel_name} con '{new_text}'! 🚀"}}, 200

        # Eliminar mensaje
        elif accion == "eliminar":
            match = re.search(r'mensaje\s*en\s*#?(\w+)', solicitud, re.IGNORECASE)
            if not match:
                return {"solicitud": "POST", "result": {"message": "📩 ¡Falta algo! Dime qué mensaje eliminar y en qué canal (ej. 'eliminar mensaje en #general') 🚀"}}, 200
            channel_name = match.group(1).strip()

            channel_id = f"C{channel_name.upper()}"  # Placeholder
            url = "https://slack.com/api/chat.delete"
            # Nota: En producción, necesitas el timestamp (ts) del mensaje
            payload = {"channel": channel_id, "ts": "simulated_ts"}
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return {"solicitud": "POST", "result": {"message": f"🗑️ ¡Mensaje eliminado en #{channel_name} con éxito! 🚀"}}, 200

        else:
            return {"solicitud": "POST", "result": {"error": f"No entendí '{accion}', ¿puedes usar 'enviar', 'actualizar', 'eliminar'?"}}, 400

    except requests.RequestException as e:
        return {"solicitud": "POST", "result": {"error": f"Lo siento, hubo un problema al conectar con Slack: {str(e)}"}}, 500
    except Exception as e:
        return {"solicitud": "POST", "result": {"error": f"Ups, algo salió mal inesperadamente: {str(e)}"}}, 500