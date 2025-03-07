from flask import request, jsonify
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from config import Config
from datetime import datetime
import re
import json
import openai

def setup_execute_routes(app,mongo):
    @app.route('/execute/gmail', methods=['GET'])
    def execute_gmail_rules():
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400

        # Buscar el usuario en la base de datos
        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        # Obtener el token actualizado
        gmail_token = user.get('integrations', {}).get('Gmail', {}).get('token')
        if not gmail_token:
            return jsonify({"error": "Token de Gmail no disponible"}), 400

        # Obtener reglas activas para Gmail
        rules = [rule for rule in user.get('automatizaciones', []) if rule.get("service") == "Gmail" and rule.get("active")]

        executed_rules = []
        for rule in rules:
            condition = rule.get("condition", "").lower().strip()
            action = rule.get("action", "").lower().strip()

            # Extraer el remitente de la condición
            condition_match = re.search(r"de\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z0-9]{2,})", condition)
            if condition_match:
                expected_sender = condition_match.group(1).lower().strip()
                print(f"Gmail: Regla con remitente específico '{expected_sender}'")
            else:
                # Si no hay un correo, tomar el nombre después de "de"
                company_match = re.search(r"de\s+(.+)", condition)
                if company_match:
                    expected_sender = company_match.group(1).lower().strip()
                    print(f"Gmail: Buscando correos de remitentes que contengan '{expected_sender}'")
                else:
                    print(f"Gmail: No se pudo extraer un remitente válido de la condición: {condition}")
                    expected_sender = None

            if expected_sender:
                try:
                    url = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
                    headers = {"Authorization": f"Bearer {gmail_token}"}
                    params = {"q": f"from:{expected_sender}"}
                    
                    response = requests.get(url, headers=headers, params=params)
                    if response.status_code == 200:
                        messages = response.json().get('messages', [])
                        if messages:
                            for message in messages:
                                message_id = message['id']
                                if action == "borrar":
                                    delete_url = f"https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}/trash"
                                    delete_response = requests.post(delete_url, headers=headers)
                                    if delete_response.status_code == 204:
                                        print(f"Gmail: Correo eliminado con éxito.")
                                    else:
                                        print(f"Gmail: Error al eliminar el correo: {delete_response.text}")
                                elif action == "mover a spam":
                                    modify_url = f"https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}/modify"
                                    modify_payload = {"addLabelIds": ["SPAM"]}
                                    modify_response = requests.post(modify_url, headers=headers, json=modify_payload)
                                    if modify_response.status_code == 200:
                                        print(f"Gmail: Correo movido a spam.")
                                    else:
                                        print(f"Gmail: Error al mover a spam: {modify_response.text}")
                                elif action == "responder":
                                    reply_url = "https://gmail.googleapis.com/gmail/v1/messages/send"
                                    reply_body = {
                                        "raw": create_message(expected_sender, "Gracias por tu correo, responderé pronto.")
                                    }
                                    reply_response = requests.post(reply_url, headers=headers, json=reply_body)
                                    if reply_response.status_code == 200:
                                        print(f"Gmail: Correo respondido con éxito.")
                                    else:
                                        print(f"Gmail: Error al enviar respuesta: {reply_response.text}")

                            # Actualizar la última ejecución de la regla
                            mongo.database.usuarios.update_one(
                                {"_id": user["_id"], "automatizaciones.condition": condition},
                                {"$set": {"automatizaciones.$.last_executed": datetime.utcnow()}}
                            )
                            executed_rules.append(rule)
                        else:
                            print(f"Gmail: No se encontraron correos de {expected_sender}.")
                    else:
                        print(f"Gmail: Error al obtener correos: {response.text}")

                except requests.exceptions.RequestException as error:
                    return jsonify({"error": f"Error en la petición a la API de Gmail: {str(error)}"}), 500

        if executed_rules:
            return jsonify({"message": "Ejecución de reglas de Gmail completada.", "executed_rules": executed_rules})
        else:
            return jsonify({"message": "No se ejecutaron reglas de Gmail."}), 200
    
    def create_message(to, body):
        """ Crea un mensaje MIME para enviar una respuesta en Gmail (en formato base64) """
        from email.mime.text import MIMEText
        import base64

        # Crear el cuerpo del mensaje en formato MIME
        message = MIMEText(body)
        message['to'] = to
        message['subject'] = "Respuesta automática"
        
        # Codificar el mensaje en base64
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        return raw_message