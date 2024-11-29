from flask import redirect, Blueprint, url_for, session, request, jsonify
import requests
from requests_oauthlib import OAuth2Session
from config import Config
from urllib.parse import urlencode
import base64 
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import unicodedata
from requests.models import Response
import re
import json
from werkzeug.security import generate_password_hash, check_password_hash
import os
import quopri
from flask_pymongo import PyMongo, ObjectId
import openai
from app.services.gmail import auth_gmail as service_auth_gmail
from app.services.gmail import auth_gmail_callback as service_auth_callback
from app.services.notion import notion_auth as service_auth_notion
from app.services.notion import notion_callback as service_auth_notion_callback

openai.api_key=Config.CHAT_API_KEY

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
def setup_routes(app, mongo):
    stateSlack = ""
    idUser = ""
    notion_bp = Blueprint('notion', __name__)
    @app.route('/')
    def home():
        return ("Este es el backend del proyecto!!")

    @app.route('/register', methods=['POST'])
    def register_user():
        request_data = request.get_json() 
        if not request_data or "body" not in request_data:
            return jsonify({"error": "El cuerpo de la solicitud es inválido"}), 400
        try:
            data = json.loads(request_data["body"])
        except json.JSONDecodeError:
            return jsonify({"error": "El cuerpo JSON es inválido"}), 400

        if not data or not all(k in data for k in ("nombre", "apellido", "correo", "password")):
            return jsonify({"error": "Faltan campos obligatorios"}), 400

        # Verificar si el correo ya existe en la base de datos
        if mongo.db.usuarios.find_one({"correo": data["correo"]}):
            return jsonify({"error": "El correo ya está registrado"}), 400

        # Si el correo no existe, proceder con el registro
        hashed_password = generate_password_hash(data['password'])
        usuario = {
            "img": data.get("img", ""),  # Opcional
            "nombre": data["nombre"],
            "apellido": data["apellido"],
            "correo": data["correo"],
            "password": hashed_password,
            "integrations": {} # Inicialmente vacío
        }

        if 'usuarios' not in mongo.db.list_collection_names():
            mongo.db.create_collection('usuarios')

        if 'usuarios' in mongo.db.list_collection_names():
            result = mongo.db.usuarios.insert_one(usuario)
        
        return jsonify({"message": "Usuario registrado exitosamente", "id": str(result.inserted_id)}), 201

    @app.route('/login', methods=['POST'])
    def login_user():
        data = request.get_json()
        if not data or not all(k in data for k in ("correo", "password")):
            return jsonify({"error": "Faltan campos obligatorios"}), 400
        
        usuario = mongo.db.usuarios.find_one({"correo": data["correo"]})
        if not usuario or not check_password_hash(usuario["password"], data["password"]):
            return jsonify({"error": "Credenciales incorrectas"}), 401

        session['user_id'] = str(usuario['_id'])
        idUser = str(usuario['_id'])
        return jsonify({"message": "Inicio de sesión exitoso", "user_id": session['user_id']}), 200
        
    @app.route('/check_integrations', methods=['GET'])
    def check_integrations():
        email = request.args.get('email')

        if not email:
            return jsonify({"error": "Correo electrónico no proporcionado"}), 400

        usuario = mongo.db.usuarios.find_one({"correo": email})
        
        if not usuario:
            return jsonify({"error": "Usuario no encontrado"}), 404

        if not usuario.get('integrations') or len(usuario['integrations']) == 0:
            return jsonify({"message": "Usuario sin integraciones"}), 200
        
        return jsonify({"message": "Usuario con integraciones", "integrations": usuario['integrations']}), 200

    @app.route('/get_integrations', methods=['GET'])
    def get_integrations():
        user_email = request.args.get("email")
        
        user = mongo.db.usuarios.find_one({"correo": user_email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        # Devolvemos las integraciones que tiene el usuario
        return jsonify({"integrations": user.get("integrations", {})}), 200


    @app.route('/add_integration', methods=['POST'])
    def add_integration():
        request_data = request.get_json()
        user_email = request_data.get("email")
        print(user_email)
        integration_name = request_data.get("integration")
        print(integration_name)
        token = request_data.get("token")
        print(token)

        if not all([user_email, integration_name, token]):
            return jsonify({"error": "Faltan campos obligatorios"}), 400

        user = mongo.db.usuarios.find_one({"correo": user_email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        # Actualizar el campo de integraciones
        # Verifica si la integración ya existe, de lo contrario, la agrega
        mongo.db.usuarios.update_one(
            {"correo": user_email},
            {"$set": {f"integrations.{integration_name}": token}}
        )

        return jsonify({"message": "Integración añadida exitosamente"}), 200


    @app.route('/assign_user_id', methods=['POST'])
    def assign_user_id():
        id_user = request.args.get('idUser')  # Obtenemos el parámetro de consulta
        
        if not id_user:
            return jsonify({"error": "ID de usuario no proporcionado"}), 400
        
        # Aquí podrías realizar validaciones o asignar este ID a una sesión, si fuera necesario
        idUser = id_user  # Ejemplo: almacenar el ID en la sesión

        return jsonify({"message": "ID de usuario asignado correctamente", "user_id": id_user}), 200


    @app.route('/auth/gmail')
    def auth_gmail():
        return service_auth_gmail()

    @app.route('/auth/gmail/callback')
    def auth_gmail_callback():
       return service_auth_callback(mongo)
    
    @app.route('/auth/hubspot')
    def auth_hubspot():
        scope = [
            "crm.objects.appointments.read",
            "crm.objects.appointments.write",
            "crm.objects.carts.read",
            "crm.objects.carts.write",
            "crm.objects.companies.read",
            "crm.objects.companies.write",
            "crm.objects.contacts.read",
            "crm.objects.contacts.write",
            "crm.objects.courses.read",
            "crm.objects.courses.write",
            "crm.objects.custom.read",
            "crm.objects.custom.write",
            "crm.objects.deals.read",
            "crm.objects.deals.write",
            "crm.objects.feedback_submissions.read",
            "crm.objects.goals.read",
            "crm.objects.invoices.read",
            "crm.objects.leads.read",
            "crm.objects.leads.write",
            "crm.objects.line_items.read",
            "crm.objects.line_items.write",
            "crm.objects.listings.read",
            "crm.objects.listings.write",
            "crm.objects.marketing_events.read",
            "crm.objects.marketing_events.write",
            "crm.objects.orders.read",
            "crm.objects.orders.write",
            "crm.objects.owners.read",
            "crm.objects.partner-clients.read",
            "crm.objects.partner-clients.write",
            "crm.objects.quotes.read",
            "crm.objects.quotes.write",
            "crm.objects.services.read",
            "crm.objects.services.write",
            "crm.objects.subscriptions.read",
            "crm.objects.users.read",
            "crm.objects.users.write",
            "crm.schemas.deals.read",
            "crm.schemas.deals.write",
            "crm.schemas.invoices.read",
            "oauth",
            "tickets"
        ]
        hubspot = OAuth2Session(Config.HUBSPOT_CLIENT_ID, 
                                redirect_uri='https://neuron-hyper.vercel.app/auth/hubspot/callback', 
                                scope=scope)
        authorization_url, state = hubspot.authorization_url('https://app.hubspot.com/oauth/authorize')
        session['hubspot_state'] = state
        return redirect(authorization_url)

    @app.route('/auth/hubspot/callback')
    def auth_hubspot_callback():
        if 'user_id' not in session:
            return jsonify({"error": "Usuario no autenticado"}), 401

        user_id = session['user_id']
        code = request.args.get('code')
        if not code:
            return jsonify({"error": "El parámetro 'code' falta en la respuesta"}), 400

        try:
            token_url = 'https://api.hubapi.com/oauth/v1/token'
            payload = {
                'grant_type': 'authorization_code',
                'client_id': Config.HUBSPOT_CLIENT_ID,
                'client_secret': Config.HUBSPOT_CLIENT_SECRET,
                'redirect_uri': 'https://neuron-hyper.vercel.app/auth/hubspot/callback',
                'code': code
            }
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            response = requests.post(token_url, data=payload, headers=headers)
            token_data = response.json()

            if response.status_code != 200:
                return jsonify({"error": "Error al obtener el token de HubSpot", "details": token_data}), response.status_code

            mongo.db.usuarios.update_one(
                {"_id": ObjectId(user_id)},
                {"$push": {"integrations": {"platform": "hubspot", "token": token_data}}}
            )

            return jsonify({"message": "Integración de HubSpot guardada exitosamente", "integration": token_data}), 200
        except Exception as e:
            return jsonify({"error": f"Error al procesar el token de HubSpot: {str(e)}"}), 500

    @app.route('/auth/outlook')
    def auth_outlook():
        MICROSOFT_OUTLOOK_SCOPE = [
            "https://graph.microsoft.com/Mail.Read",
            "https://graph.microsoft.com/Mail.Send",
            "https://graph.microsoft.com/User.Read",
            "https://graph.microsoft.com/Files.ReadWrite"
        ]
        
        outlook = OAuth2Session(Config.OUTLOOK_CLIENT_ID, 
                                redirect_uri="https://neuron-hyper.vercel.app/auth/outlook/callback", 
                                scope=MICROSOFT_OUTLOOK_SCOPE)
        
        authorization_url, state = outlook.authorization_url("https://login.microsoftonline.com/common/oauth2/v2.0/authorize", access_type="online", prompt="consent")
        session['outlook_state'] = state
        return redirect(authorization_url)


    @app.route('/auth/outlook/callback')
    def auth_outlook_callback():
        if 'user_id' not in session:
            return jsonify({"error": "Usuario no autenticado"}), 401

        user_id = session['user_id']
        code = request.args.get('code')
        if not code:
            return jsonify({"error": "El parámetro 'code' falta en la respuesta"}), 400

        try:
            token_url = 'https://login.microsoftonline.com/common/oauth2/v2.0/token'
            payload = {
                'client_id': Config.OUTLOOK_CLIENT_ID,
                'scope': 'https://graph.microsoft.com/.default',
                'redirect_uri': 'https://neuron-hyper.vercel.app/auth/outlook/callback',
                'client_secret': Config.OUTLOOK_CLIENT_SECRET,
                'grant_type': 'authorization_code',
                'code': code
            }
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            response = requests.post(token_url, data=payload, headers=headers)
            token_data = response.json()

            if response.status_code != 200:
                return jsonify({"error": "Error al obtener el token de Outlook", "details": token_data}), response.status_code

            mongo.db.usuarios.update_one(
                {"_id": ObjectId(user_id)},
                {"$push": {"integrations": {"platform": "outlook", "token": token_data}}}
            )

            return jsonify({"message": "Integración de Outlook guardada exitosamente", "integration": token_data}), 200
        except Exception as e:
            return jsonify({"error": f"Error al procesar el token de Outlook: {str(e)}"}), 500

        
    @app.route('/auth/notion')
    def auth_notion():
        return service_auth_notion()

    @app.route('/notion/callback')
    def auth_notion_callback():
        return service_auth_notion_callback(mongo, idUser)
    
    @app.route('/auth/slack')
    def auth_slack():
        scopes = ["channels:read", "chat:write", "users:read"]
        slack = OAuth2Session(Config.SLACK_CLIENT_ID, redirect_uri='https://neuron-hyper.vercel.app/auth/slack/callback', scope=scopes)
        authorization_url, state = slack.authorization_url('https://slack.com/oauth/v2/authorize')
        session['oauth_state'] = stateSlack
        print(f"Estado almacenado en la sesión: {state}")
        return redirect(authorization_url)

    @app.route('/auth/slack/callback')
    def auth_slack_callback():
        if 'user_id' not in session:
            return jsonify({"error": "Usuario no autenticado"}), 401

        user_id = session['user_id']
        slack = OAuth2Session(Config.SLACK_CLIENT_ID, redirect_uri='https://neuron-hyper.vercel.app/auth/slack/callback')
        try:
            token = slack.fetch_token(
                'https://slack.com/api/oauth.v2.access',
                client_secret=Config.SLACK_CLIENT_SECRET,
                authorization_response=request.url
            )

            mongo.db.usuarios.update_one(
                {"_id": ObjectId(user_id)},
                {"$push": {"integrations": {"platform": "slack", "token": token}}}
            )

            return jsonify({"message": "Integración de Slack guardada exitosamente", "integration": token}), 200
        except Exception as e:
            return jsonify({"error": f"Error al procesar el token de Slack: {str(e)}"}), 500


    def to_ascii(text):
        normalized_text = unicodedata.normalize('NFD', text)
        ascii_text = ''.join(
            c for c in normalized_text if unicodedata.category(c) != 'Mn' and ord(c) < 128
        )
        
        cleaned_text = re.sub(r'(\r\n|\r|\n){2,}', '\n', ascii_text)
        cleaned_text = re.sub(r'\s{2,}', ' ', cleaned_text) 
        cleaned_text = re.sub(r'(\S)\n(\S)', r'\1 \2', cleaned_text)
        
        return cleaned_text
    
    def decode_message_body(body):
        decoded_body = ""
        try:
            body = base64.urlsafe_b64decode(body)
            decoded_body = body.decode('utf-8', 'ignore')
        except Exception as e:
            print(f"Error decodificando Base64: {e}")
            try:
                decoded_body = quopri.decodestring(body).decode('utf-8', 'ignore')
            except Exception as e2:
                print(f"Error decodificando Quoted-printable: {e2}")
                decoded_body = "Error al decodificar el cuerpo del mensaje."
        
        return decoded_body

    @app.route('/search/gmail')
    def search_gmail():
        token = session.get('gmail_token')
        if not token:
            return jsonify({"error": "Usuario no autenticado en Gmail"}), 401
        
        query = request.args.get('query')
        if query and not query.startswith("from:"):
            query = f"{query}"
        
        headers = {'Authorization': f'Bearer {token["access_token"]}'}
        params = {'q': query}
        
        response = requests.get('https://www.googleapis.com/gmail/v1/users/me/messages', headers=headers, params=params)
        if response.status_code != 200:
            return jsonify({"error": "Error al obtener mensajes"}), response.status_code
        
        messages = response.json().get('messages', [])
        if not messages:
            return jsonify({"error": "No se encontraron mensajes"}), 404
        
        email_details = []
        for message in messages:
            message_id = message['id']
            message_response = requests.get(f'https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}', headers=headers)
            if message_response.status_code != 200:
                return jsonify({"error": "Error al obtener el mensaje"}), message_response.status_code

            message_data = message_response.json()
            message_headers = message_data.get('payload', {}).get('headers', [])

            sender = next((header['value'] for header in message_headers if header['name'] == 'From'), "Sin remitente")
            date = next((header['value'] for header in message_headers if header['name'] == 'Date'), "Sin fecha")
            subject = next((header['value'] for header in message_headers if header['name'] == 'Subject'), "Sin asunto")
            body = ""
            if 'parts' in message_data['payload']:
                for part in message_data['payload']['parts']:
                    if part['mimeType'] == 'text/plain':
                        body = part['body']['data']
                        decoded_body = decode_message_body(body)
                        decoded_body = to_ascii(decoded_body)
                        break
            else:
                body = message_data['payload']['body']['data'] if 'body' in message_data['payload'] else ""
                body = decode_message_body(body)

            if body:
                try:
                    body = base64.urlsafe_b64decode(body).decode('utf-8')
                    body = body.encode().decode('unicode_escape')
                    body = to_ascii(decoded_body)
                except Exception as e:
                    body = quopri.decodestring(body).decode('utf-8')

            email_details.append({
                'from': sender,
                'date': date,
                'subject': subject,
                'body': body
            })

        return jsonify(email_details)

    @app.route('/search/notion', methods=['GET'])
    def search_notion():
        simplified_results = []
        access_token = session.get('access_token')
        if not access_token:
            return jsonify({"error": "Usuario no autenticado en Notion"}), 401

        query = request.args.get('query')
        if not query:
            return jsonify({"error": "No se proporcionó un término de búsqueda"}), 400

        url = 'https://api.notion.com/v1/search'
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Notion-Version': '2022-06-28',
            'Content-Type': 'application/json'
        }
        data = {
            "query": query
        }

        response = requests.post(url, headers=headers, json=data)

        if response.status_code != 200:
            return jsonify({"error": "Error al buscar en Notion", "details": response.json()}), response.status_code

        for result in response.json().get("results", []):
            page_info = {
                "id": result["id"],
                "created_time": result.get("created_time"),
                "last_edited_time": result.get("last_edited_time"),
                "url": result.get("url"),
                "properties": {}
            }

            properties = result.get("properties", {})

            for property_name, property_value in properties.items():
                if property_name == "Nombre de tarea" and property_value.get("title"):
                    page_info["properties"]["Nombre de tarea"] = property_value["title"][0]["plain_text"]
                elif property_name == "Estado" and property_value.get("status"):
                    page_info["properties"]["Estado"] = property_value["status"].get("name", None)
                elif property_name == "Etiquetas" and property_value.get("multi_select"):
                    page_info["properties"]["Etiquetas"] = [tag["name"] for tag in property_value.get("multi_select", [])]
                elif property_name == "Fecha límite" and property_value.get("date"):
                    page_info["properties"]["Fecha límite"] = property_value.get("date")
                elif property_name == "Prioridad" and property_value.get("select"):
                    page_info["properties"]["Prioridad"] = property_value["select"].get("name")
                elif property_name == "Proyecto" and property_value.get("relation"):
                    page_info["properties"]["Proyecto"] = [relation["id"] for relation in property_value.get("relation", [])]
                elif property_name == "Responsable" and property_value.get("people"):
                    page_info["properties"]["Responsable"] = [person["id"] for person in property_value.get("people", [])]
                elif property_name == "Resumen" and property_value.get("rich_text"):
                    page_info["properties"]["Resumen"] = [text["text"]["content"] for text in property_value.get("rich_text", [])]
                elif property_name == "Subtareas" and property_value.get("relation"):
                    page_info["properties"]["Subtareas"] = [subtask["id"] for subtask in property_value.get("relation", [])]
                elif property_name == "Tarea principal" and property_value.get("relation"):
                    page_info["properties"]["Tarea principal"] = [parent_task["id"] for parent_task in property_value.get("relation", [])]

            children = result.get("children", [])
            for block in children:
                if block.get("type") == "gallery":
                    gallery_items = block.get("gallery", {}).get("items", [])
                    page_info["properties"]["Galería"] = [item.get("title", "Sin título") for item in gallery_items]

            simplified_results.append(page_info)

        return jsonify(simplified_results)

    @app.route('/search/slack', methods=['GET'])
    def search_slack():
        access_token = session.get('slack_token')
        
        if not access_token:
            return jsonify({"error": "Usuario no autenticado en Slack"}), 401

        query = request.args.get('query')
        if not query:
            return jsonify({"error": "No se proporcionó un término de búsqueda"}), 400

        url = 'https://slack.com/api/search.messages'
        headers = {
            'Authorization': f'Bearer {Config.SLACK_USER_TOKEN}',
            'Content-Type': 'application/json'
        }
        params = {
            'query': query
        }

        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        print(data)

        if response.status_code != 200 or not data.get('ok'):
            return jsonify({"error": "Error al buscar en Slack", "details": data}), response.status_code
        messages = data.get("messages", {}).get("matches", [])
        if not messages:
            return jsonify({"error": "No se encontraron mensajes en Slack"}), 404
        slack_results = []
        for message in messages:
            slack_results.append({
                "channel": message.get("channel", {}).get("name"),
                "user": message.get("username"),
                "text": message.get("text"),
                "ts": message.get("ts")
            })

        return jsonify(slack_results)
    
    @app.route('/search/outlook', methods=['GET'])
    def search_outlook():
        access_token = session.get('outlook_token')
        
        if not access_token:
            return jsonify({"error": "Usuario no autenticado en Outlook"}), 401

        expires_at = session.get('expires_at')
        if expires_at and datetime.now().timestamp() > expires_at:
            return jsonify({"error": "El token de acceso ha expirado, por favor vuelve a iniciar sesión."}), 401

        query = request.args.get('query')
        if not query:
            return jsonify({"error": "No se proporcionó un término de búsqueda"}), 400

        url = 'https://graph.microsoft.com/v1.0/me/messages'
        headers = {
            'Authorization': f"Bearer {access_token['access_token']}",
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.get(url, headers=headers, params={'$search': query})
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            return jsonify({"error": "Error al buscar en Outlook", "details": str(e)}), 500

        results = response.json().get('value', [])
        search_results = []

        for result in results:
            body = to_ascii(result.get("bodyPreview"))
            result_info = {
                "subject": result.get("subject"),
                "receivedDateTime": result.get("receivedDateTime"),
                "sender": result.get("sender", {}).get("emailAddress", {}).get("address"),
                "bodyPreview": body
            }
            search_results.append(result_info)

        return jsonify(search_results)


    def get_owner_name(owner_id, token, field):
        """Obtiene el nombre del propietario a partir de su ID."""
        if not owner_id:
            return "N/A"
        url = f"https://api.hubapi.com/crm/v3/owners/{owner_id}"
        headers = {'Authorization': f"Bearer {token}"}
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                owner_data = response.json()
                if field == "name":
                    return f"{owner_data.get('firstName', 'N/A')} {owner_data.get('lastName', 'N/A')}"
                elif field == "email":
                    return owner_data.get('email', 'N/A')
        except requests.RequestException:
            pass
        return "N/A"

    def get_associations(object_type, object_id, associated_type, token):
        """Obtiene asociaciones de un objeto."""
        url = f"https://api.hubapi.com/crm/v3/objects/{object_type}/{object_id}/associations/{associated_type}"
        headers = {'Authorization': f"Bearer {token}"}
        try:
            response = requests.get(url, headers=headers)
            print(response.json())
            if response.status_code == 200:
                return [assoc.get("id") for assoc in response.json().get("results", [])]
        except requests.RequestException:
            pass
        return []
    
    def fetch_associated_details(associated_ids, object_type, token):
        """Obtiene los detalles de las asociaciones por ID."""
        print(associated_ids)
        results = []
        for assoc_id in associated_ids:
            url = f"https://api.hubapi.com/crm/v3/objects/{object_type}/{assoc_id}"
            headers = {'Authorization': f"Bearer {token}"}
            try:
                response = requests.get(url, headers=headers)
                print(response)
                if response.status_code == 200:
                    properties = response.json().get("properties", {})
                    print(properties)
                    if object_type == "contacts":
                        # Para los contactos, se concatena 'firstname' y 'lastname'
                        name = f"{properties.get('firstname', 'N/A')} {properties.get('lastname', 'N/A')}"
                        results.append({
                            "id": assoc_id,
                            "name": name,
                            "email": properties.get("email", "N/A") 
                        })
                    elif object_type == "companies":
                        # Para las compañías, solo se usa 'name'
                        results.append({
                            "id": assoc_id,
                            "domain": properties.get("domain", "N/A")
                        })
            except requests.RequestException:
                continue
        return results


    @app.route('/search/hubspot', methods=['GET'])
    def search_hubspot(access_token):
        query = request.args.get('query')
        stopwords = ["mandame", "del", "que", "link", "pasame", "enviame", "brindame", "dame", "me", "paso", "envio", "dijo", "dame", "toda", "la", "información", "del", "en", "que", "esta", "empresa"]
        keywords = ' '.join([word for word in query.split() if word.lower() not in stopwords])
        if not query:
            return jsonify({"error": "No se proporcionó un término de búsqueda"}), 400

        # Endpoints de búsqueda en HubSpot
        endpoints = {
            "contacts": {
                "url": "https://api.hubapi.com/crm/v3/objects/contacts/search",
                "propertyName": "firstname"
            },
            "companies": {
                "url": "https://api.hubapi.com/crm/v3/objects/companies/search",
                "propertyName": "name"
            },
            "deals": {
                "url": "https://api.hubapi.com/crm/v3/objects/deals/search",
                "propertyName": "dealname"
            }
        }

        headers = {
            'Authorization': f"Bearer {access_token}",
            'Content-Type': 'application/json'
        }

        search_results = {}
        for object_type, config in endpoints.items():
            url = config["url"]
            property_name = config["propertyName"]

            data = {
                "filters": [
                    {
                        "propertyName": property_name,
                        "operator": "CONTAINS_TOKEN",
                        "value": keywords
                    }
                ],
                "properties": ["firstname", "lastname", "name", "dealname", "cost", "email", "phone", "company", "createdate", "hubspot_owner_id", "dealstage", "price"]
            }

            try:
                response = requests.post(url, headers=headers, json=data)
                if response.status_code == 200:
                    results = response.json().get("results", [])

                    if not results:
                        search_results[object_type] = {"message": f"No se encontraron {object_type} con '{query}'"}
                    else:
                        formatted_results = []

                        for result in results:
                            properties = result.get("properties", {})
                            created_date = properties.get("createdate", "")
                            try:
                                formatted_date = datetime.strptime(
                                    created_date, "%Y-%m-%dT%H:%M:%S.%fZ"
                                ).strftime("%Y-%m-%d")
                            except ValueError:
                                formatted_date = created_date

                            result_info = {
                                "id": result.get("id"),
                                "email": properties.get("email", "N/A"),
                                "phone": properties.get("phone", "N/A"),
                                "createdate": formatted_date
                            }

                            if object_type == "deals":
                                result_info["owner"] = get_owner_name(properties.get("hubspot_owner_id"), access_token['access_token'], "name")
                                result_info["stage"] = properties.get("dealstage", "N/A")
                                result_info["name"] = properties.get("dealname", "N/A")
                                price = properties.get("price", "N/A")
                                result_info["price"] = price
                                contacts_assoc = get_associations("deals", result_info["id"], "contacts", access_token['access_token'])
                                companies_assoc = get_associations("deals", result_info["id"], "companies", access_token['access_token'])
                                result_info["associations"] = {
                                    "contacts": fetch_associated_details(contacts_assoc, "contacts", access_token['access_token']),
                                    "companies": fetch_associated_details(companies_assoc, "companies", access_token['access_token'])
                                }

                            elif object_type == "contacts":
                                if properties.get("firstname"):
                                    result_info["name"] = f"{properties['firstname']} {properties['lastname']}"
                                else:
                                    result_info["name"] = "N/A"

                                company_assoc = get_associations("contacts", result_info["id"], "companies", access_token['access_token'])
                                company_info = fetch_associated_details(company_assoc, "companies", access_token['access_token'])

                                if company_info:
                                    result_info["company"] = company_info[0].get("name", "N/A")
                                else:
                                    result_info["company"] = "N/A"

                            elif object_type == "companies":
                                result_info["company"] = properties.get("name", "N/A")
                                result_info["price"] = properties.get("price", "N/A")

                            formatted_results.append(result_info)

                        search_results[object_type] = formatted_results
                else:
                    search_results[object_type] = {
                        "error": f"Error al buscar en {object_type}",
                        "details": response.json()
                    }

            except requests.RequestException as e:
                search_results[object_type] = {
                    "error": f"Error al procesar la solicitud en {object_type}",
                    "details": str(e)
                }

        return jsonify(search_results)

    @app.route('/askIa', methods=['POST'])
    def ask():
        # Obtener los parámetros 'email' y 'query' de la solicitud
        email = request.args.get('email')
        query = request.args.get('query')
        print(email)
        print(query)

        # Validar si se proporcionaron ambos parámetros
        if not email or not query:
            return jsonify({"error": "Se deben proporcionar tanto el email como la consulta de búsqueda"}), 400

        # Llamar a la función de búsqueda usando el email proporcionado
        try:
            search_results = search_all(email)
            search_results_data = search_results.get_json()
            print("search_results obtenidos:", search_results_data)  # Verificar si los resultados son correctos

            user = mongo.db.usuarios.find_one({'correo': email})
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404
            # Verificar y buscar datos en HubSpot si existe un token
            # Verificar si existe un token de HubSpot
            hubspot_token = user.get('integrations', {}).get('HubSpot', None)
            if hubspot_token:
                hubspot_data = search_hubspot(hubspot_token)
                print(f"Tipo de search_results: {type(search_results)}")
                print(f"Tipo de hubspot_data: {type(hubspot_data)}")
                # Extraemos el contenido de ambas respuestas como JSON
                search_results_data = search_results.get_json()  # Extraemos los datos de search_results
                hubspot_data_extracted = hubspot_data.get_json()  # Extraemos los datos de hubspot_data

                print("search_results_data:", search_results_data)
                print("hubspot_data_extracted:", hubspot_data_extracted)

                # Actualizamos search_results_data con los datos de HubSpot
                search_results_data.update(hubspot_data_extracted)
                
                print("Resultados combinados:", search_results_data)
            else:
                print("No se encontró token de HubSpot")

        except Exception as e:
            # Si ocurre un error al buscar los resultados
            return jsonify({"error": f"Error al obtener resultados de búsqueda: {str(e)}"}), 500

        # Generar el prompt para la IA usando la query y los resultados de búsqueda
        prompt = generate_prompt(query, search_results_data)
        print(prompt)

        # Realizar la solicitud a OpenAI para obtener la respuesta de la IA
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Eres un asistente útil el cual está conectado con diversas aplicaciones y automatizarás el proceso de buscar información en base a la query que se te envie"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4096
            )
            print("RESPONSE IA CONNECTED", response)
        except Exception as e:
            # Manejo de error si ocurre un problema con OpenAI
            return jsonify({"error": f"Error al contactar con OpenAI: {str(e)}"}), 500

        # Obtener la respuesta de la IA
        ia_response = response.choices[0].message['content'].strip()
        print("RESPONSE IA", ia_response)

        # Validar que la respuesta de la IA no esté vacía
        if not ia_response:
            return jsonify({"error": "La respuesta de la IA está vacía"}), 500

        # Retornar la respuesta de la IA en formato JSON
        return jsonify({
            "response": to_ascii(ia_response)
        })

    def generate_prompt(query, search_results):
        # Gmail Results
        gmail_results = "\n".join([ 
            f"De: {email['from']}\nFecha: {email['date']}\nAsunto: {email['subject']}\nCuerpo: {email['body']}\n"
            for email in search_results.get('gmail', []) if isinstance(email, dict)
        ]) or "No se encontraron correos relacionados en Gmail."

        # Slack Results
        slack_results = "\n".join([ 
            f"En el canal '{msg['channel']}', el usuario '{msg['user']}' dijo:\n'{msg['text']}'\nFecha: {msg['ts']}\n"
            for msg in search_results.get('slack', []) if isinstance(msg, dict)
        ]) or "No se encontraron mensajes relacionados en Slack."

        # Notion Results
        notion_results = "\n".join([ 
            f"Página ID: {page['id']}\nCreada el: {page['created_time']}\nÚltima editada: {page['last_edited_time']}\n"
            f"URL: {page['url']}\nPropiedades: {json.dumps(page['properties'], ensure_ascii=False)}\n"
            for page in search_results.get('notion', []) if isinstance(page, dict)
        ]) or "No se encontraron notas o registros relacionados en Notion."

        # Outlook Results
        outlook_results = "\n".join([ 
            f"De: {email['sender']}\nFecha: {email['receivedDateTime']}\nAsunto: {email['subject']}\nCuerpo: {email['bodyPreview']}\n"
            for email in search_results.get('outlook', []) if isinstance(email, dict)
        ]) or "No se encontraron correos relacionados en Outlook."

        # HubSpot Results
        hubspot_results = ""
        hubspot_data = search_results.get("hubspot", {})

        if "contacts" in hubspot_data:
            contacts = hubspot_data["contacts"]
            if isinstance(contacts, list) and contacts:
                hubspot_results += "\n### Contacts:\n"
                for contact in contacts:
                    name = contact.get('name', 'N/A')
                    email = contact.get('email', 'N/A')
                    phone = contact.get('phone', 'N/A')
                    company = contact.get('company', 'N/A')
                    createdate = contact.get('createdate', 'N/A')
                    hubspot_results += f"Nombre: {name}\nCorreo: {email}\nTeléfono: {phone}\nCompañía: {company}\nFecha de creación: {createdate}\n\n"
            else: 
                hubspot_results += "No se encontraron contactos relacionados en HubSpot.\n"

        if "companies" in hubspot_data:
            companies = hubspot_data["companies"]
            if isinstance(companies, list) and companies:
                hubspot_results += "\n### Companies:\n"
                for company in companies:
                    name = company.get('company', 'N/A')
                    price = company.get('price', 'N/A')
                    phone = company.get('phone', 'N/A')
                    email = company.get('email', 'N/A')
                    createdate = company.get('createdate', 'N/A')
                    hubspot_results += f"Compañía: {name}\nPrecio: {price}\nTeléfono: {phone}\nCorreo: {email}\nFecha de creación: {createdate}\n\n"
            else:
                hubspot_results += "No se encontraron compañías relacionadas en HubSpot.\n"

        if "deals" in hubspot_data:
            deals = hubspot_data["deals"]
            if isinstance(deals, list) and deals:
                hubspot_results += "\n### Deals:\n"
                for deal in deals:
                    name = deal.get('name', 'N/A')
                    price = deal.get('price', 'N/A')
                    stage = deal.get('stage', 'N/A')
                    owner = deal.get('owner', 'N/A')
                    createdate = deal.get('createdate', 'N/A')
                    hubspot_results += f"Negocio: {name}\nMonto: {price}\nEstado: {stage}\nPropietario: {owner}\nFecha de cierre: {createdate}\n"
            else:
                hubspot_results += "No se encontraron negocios relacionados en HubSpot.\n"

        # Si no hay resultados de HubSpot, mostrar mensaje
        hubspot_results = hubspot_results.strip() or "No se encontraron resultados relacionados en HubSpot."

        # Construcción del prompt
        prompt = f"""Resultados de búsqueda para la consulta: "{query}"

        ### Gmail:
        {gmail_results}

        ### Notion:
        {notion_results}

        ### Slack:
        {slack_results}

        ### Outlook:
        {outlook_results}

        ### HubSpot:
        {hubspot_results}

        Con base en esta información, genera una respuesta detallada que incluya únicamente resultados específicos para la consulta.
        - Para **Gmail**, proporciona el asunto, cuerpo y enlaces relevantes, el nombre del remitente y palabras clave detectadas. Asegúrate de verificar coincidencias exactas con '{query}'.
        - En **Slack**, resume el contenido y tono del mensaje, el canal o grupo, y la fecha de envío.
        - En **Notion**, enfócate en los contenidos de las propiedades clave y su relación con '{query}'.
        - En **Outlook**, proporciona los detalles del asunto, cuerpo y remitente de los correos relevantes, verificando coincidencias con '{query}'.
        - En **HubSpot**, resalta los contactos, compañías y negocios que coincidan con la búsqueda, incluyendo nombres, correos, información de la compañía, monto de negocio, fecha de cierre y cualquier otra información relevante.

        Quiero que no respondas como lista por cada uno si no que solo menciones En gmail se encontro esto, En Notion se encontro esto, y asi con cada una. Si en dado caso hay error en busqueda pon que busque con terminos semejantes
        """

        return prompt



    def clean_body(body):
        normalized_text = unicodedata.normalize('NFD', body)
        ascii_text = ''.join(
            c for c in normalized_text if unicodedata.category(c) != 'Mn' and ord(c) < 128
        )
        cleaned_text = re.sub(r'(\r\n|\r|\n){2,}', '\n', ascii_text)
        cleaned_text = re.sub(r'\s{2,}', ' ', cleaned_text) 
        cleaned_text = re.sub(r'(\S)\n(\S)', r'\1 \2', cleaned_text)
        
        return cleaned_text
    
    def decode_message_body(data):
        """Decodifica el cuerpo del mensaje en base64."""
        return base64.urlsafe_b64decode(data).decode('utf-8')

    def extract_text_from_html(html_content):
        """Extrae texto del contenido HTML."""
        soup = BeautifulSoup(html_content, 'html.parser')
        return soup.get_text()
    
    @app.route('/notion-proxy', methods=['POST'])
    def notion_proxy():
        try:
            # Datos enviados desde el frontend
            data = request.json

            # Credenciales de cliente codificadas en Base64
            client_id = data.get('client_id')
            client_secret = data.get('client_secret')
            client_credentials = f"{client_id}:{client_secret}"
            encoded_credentials = base64.b64encode(client_credentials.encode()).decode()

            # Configuración de los encabezados
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {encoded_credentials}",
                "Notion-Version": "2022-06-28",
            }

            # Datos de la solicitud enviados al endpoint de Notion
            token_data = {
                "grant_type": "authorization_code",
                "code": data.get("code"),
                "redirect_uri": data.get("redirect_uri"),
            }

            # Realiza la solicitud POST a la API de Notion
            response = requests.post("https://api.notion.com/v1/oauth/token", data=token_data, headers=headers)

            # Devuelve la respuesta de Notion al cliente
            return jsonify(response.json()), response.status_code

        except Exception as e:
            # Manejo de errores
            return jsonify({"error": str(e)}), 500
        
    @app.route('/hubspot-proxy', methods=['POST'])
    def hubspot_proxy():
        try:
            # Datos enviados desde el frontend
            data = request.json
            
            # Parámetros de autenticación
            token_url = 'https://api.hubapi.com/oauth/v1/token'
            payload = {
                'grant_type': 'authorization_code',
                'client_id': data.get('client_id'),  # Client ID de HubSpot
                'client_secret': data.get('client_secret'),  # Client Secret de HubSpot
                'redirect_uri': data.get('redirect_uri'),  # URI de redirección
                'code': data.get('code')  # El código de autorización obtenido
            }

            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
            }

            # Realiza la solicitud POST a la API de HubSpot
            response = requests.post(token_url, data=urlencode(payload), headers=headers)

            if response.status_code == 200:
                token_data = response.json()
                return jsonify(token_data), 200  # Devuelve el token de HubSpot al frontend
            else:
                return jsonify({'error': 'HubSpot API error', 'details': response.json()}), response.status_code

        except Exception as e:
            # Manejo de errores
            return jsonify({"error": str(e)}), 500

    @app.route('/search/all', methods=['GET'])
    def search_all(email):
        query = request.args.get('query')
        if not query:
            return jsonify({"error": "No se proporcionó una consulta de búsqueda"}), 400
        
        two_weeks_ago = datetime.now() - timedelta(weeks=2)
        two_weeks_ago_str = two_weeks_ago.strftime('%Y/%m/%d')
        results = {
            "gmail": [],
            "slack": [],
            "notion": [],
            "outlook": []
        }

        user = mongo.db.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404
        # Búsqueda en Gmail
        gmail_token = user.get('integrations', {}).get('Gmail', None)
        if gmail_token:
            headers = {'Authorization': f'Bearer {gmail_token}'}

            stopwords = ["mandame", "del", "que", "link", "pasame", "enviame", "brindame", "dame", "me", "paso", "envio", "dijo","dame","toda","la","información", "del"]
            keywords = ' '.join([word for word in query.split() if word.lower() not in stopwords])
            params = {'q': f"{keywords} after:{two_weeks_ago_str}"}
            gmail_response = requests.get('https://www.googleapis.com/gmail/v1/users/me/messages', headers=headers, params=params)

            if gmail_response.status_code == 200:
                messages = gmail_response.json().get('messages', [])
                for message in messages:
                    message_id = message['id']
                    message_response = requests.get(f'https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}', headers=headers)

                    if message_response.status_code == 200:
                        message_data = message_response.json()
                        message_headers = message_data.get('payload', {}).get('headers', [])
                        sender = next((header['value'] for header in message_headers if header['name'] == 'From'), "Sin remitente")
                        date = next((header['value'] for header in message_headers if header['name'] == 'Date'), "Sin fecha")
                        subject = next((header['value'] for header in message_headers if header['name'] == 'Subject'), "Sin asunto")

                        body = ""
                        if 'parts' in message_data['payload']:
                            for part in message_data['payload']['parts']:
                                if part['mimeType'] == 'text/html':
                                    html_body = decode_message_body(part['body']['data'])
                                    decoded_body = decode_message_body(body)
                                    decoded_body = to_ascii(decoded_body)
                                    body = extract_text_from_html(html_body)
                                    body = clean_body(body)
                                    break
                        else:
                            if message_data['payload'].get('body', {}).get('data'):
                                html_body = decode_message_body(message_data['payload']['body']['data'])
                                body = clean_body(body)
                                body = extract_text_from_html(html_body)

                        results['gmail'].append({
                            'from': sender,
                            'date': date,
                            'subject': subject,
                            'body': body if body else "Cuerpo vacío"
                        })
            else:
                results['gmail'] = {"error": "Error al buscar en Gmail", "details": gmail_response.json()}
        else:
            results['gmail'] = {"error": "Sesión no ingresada en Gmail"}

        # Búsqueda en Slack
        slack_token = user.get('integrations', {}).get('Slack', None)
        if slack_token:
            url = 'https://slack.com/api/search.messages'
            headers = {
                'Authorization': f'Bearer {Config.SLACK_USER_TOKEN}',
                'Content-Type': 'application/json'
            }
            params = {'query': query}
            response = requests.get(url, headers=headers, params=params)
            data = response.json()

            if response.status_code != 200 or not data.get('ok'):
                return jsonify({"error": "Error al buscar en Slack", "details": data}), response.status_code
            messages = data.get("messages", {}).get("matches", [])
            for message in messages:
                results['slack'].append({
                    "channel": message.get("channel", {}).get("name"),
                    "user": message.get("username"),
                    "text": message.get("text"),
                    "ts": message.get("ts")
                })

        # Búsqueda en Notion
        notion_token = user.get('integrations', {}).get('Notion', None)
        if notion_token:
            headers = {
                'Authorization': f'Bearer {notion_token}',
                'Notion-Version': '2022-06-28',
                'Content-Type': 'application/json'
            }
            data = {"query": query}
            notion_response = requests.post('https://api.notion.com/v1/search', headers=headers, json=data)

            if notion_response.status_code == 200:
                for result in notion_response.json().get("results", []):
                    page_info = {
                        "id": result["id"],
                        "created_time": result.get("created_time"),
                        "last_edited_time": result.get("last_edited_time"),
                        "url": result.get("url"),
                        "properties": {}
                    }
                    properties = result.get("properties", {})
                    for property_name, property_value in properties.items():
                        if isinstance(property_value, dict):
                            if property_value.get("type") == "title" and property_value.get("title"):
                                page_info["properties"][property_name] = property_value["title"][0]["plain_text"]
                            elif property_value.get("type") == "status" and property_value.get("status"):
                                page_info["properties"][property_name] = property_value["status"].get("name")
                            elif property_value.get("type") == "multi_select":
                                page_info["properties"][property_name] = [tag["name"] for tag in property_value.get("multi_select", [])]
                            elif property_value.get("type") == "date" and property_value.get("date"):
                                page_info["properties"][property_name] = property_value["date"].get("start")
                            elif property_value.get("type") == "select" and property_value.get("select"):
                                page_info["properties"][property_name] = property_value["select"].get("name")
                            elif property_value.get("type") == "relation":
                                if isinstance(property_value.get("relation"), list):
                                    page_info["properties"][property_name] = [relation["id"] for relation in property_value.get("relation", [])]
                                else:
                                    page_info["properties"][property_name] = [] 
                            elif property_value.get("type") == "people":
                                page_info["properties"][property_name] = [{"id": person["id"], "name": person["name"]} for person in property_value.get("people", [])]
                            elif property_value.get("type") == "rich_text":
                                page_info["properties"][property_name] = "".join([text["text"]["content"] for text in property_value.get("rich_text", [])])
                        else:
                            page_info["properties"][property_name] = str(property_value)  
                    results['notion'].append(page_info)
            else:
                results['notion'] = {"error": "Error al buscar en Notion", "details": notion_response.json()}
        else:
            results['notion'] = {"error": "Sesión no ingresada en Notion"}

        # Búsqueda en Outlook
        outlook_token = user.get('integrations', {}).get('Outlook', None)
        if outlook_token:
            expires_at = session.get('expires_at')
            if expires_at and datetime.now().timestamp() > expires_at:
                return jsonify({"error": "El token de acceso ha expirado, por favor vuelve a iniciar sesión."}), 401

            query = request.args.get('query')
            if not query:
                return jsonify({"error": "No se proporcionó un término de búsqueda"}), 400

            url = 'https://graph.microsoft.com/v1.0/me/messages'
            headers = {
                'Authorization': f"Bearer {outlook_token}",
                'Content-Type': 'application/json'
            }
            
            try:
                response = requests.get(url, headers=headers, params={'$search': query})
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                return jsonify({"error": "Error al buscar en Outlook", "details": str(e)}), 500

            results_outlook = response.json().get('value', [])
            search_results_outlook = []
            for result in results_outlook:
                body = to_ascii(result.get("bodyPreview"))
                result_info = {
                    "subject": result.get("subject"),
                    "receivedDateTime": result.get("receivedDateTime"),
                    "sender": result.get("sender", {}).get("emailAddress", {}).get("address"),
                    "bodyPreview": body
                }

                search_results_outlook.append(result_info)
            results['outlook'] = search_results_outlook
        else:
            results['outlook'] = {"error": "Sesión no ingresada en Outlook"}

        return jsonify(results)