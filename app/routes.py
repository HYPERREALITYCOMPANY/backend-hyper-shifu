from flask import redirect, Blueprint, url_for, session, request, jsonify
import requests
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from dateutil.relativedelta import relativedelta
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
openai.api_key=Config.CHAT_API_KEY

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
def setup_routes(app, mongo):
    stateSlack = ""
    idUser = ""
    notion_bp = Blueprint('notion', __name__)
    queryApis = ""
    global last_searchs

    @app.route('/')
    def home():
        return ("Este es el backend del proyecto!!")

    @app.route('/register', methods=['POST'])
    def register_user():
        request_data = request.get_json() 
        
        # Aquí obtienes el dato correctamente
        data = request_data.get('registerUser')
        
        if not request_data or "registerUser" not in request_data:
            return jsonify({"error": "El cuerpo de la solicitud es inválido"}), 400

        if not data or not all(k in data for k in ("nombre", "apellido", "correo", "password")):
            return jsonify({"error": "Faltan campos obligatorios"}), 400

        # Verificar si el correo ya existe en la base de datos
        if mongo.database.usuarios.find_one({"correo": data["correo"]}):
            return jsonify({"error": "El correo ya está registrado"}), 400

        # Si el correo no existe, proceder con el registro
        hashed_password = generate_password_hash(data['password'])
        usuario = {
            "img": data.get("img", ""),  # Opcional
            "nombre": data["nombre"],
            "apellido": data["apellido"],
            "correo": data["correo"],
            "password": hashed_password,
            "integrations": {}  # Inicialmente vacío
        }

        if 'usuarios' not in mongo.database.list_collection_names():
            mongo.database.create_collection('usuarios')

        if 'usuarios' in mongo.database.list_collection_names():
            result = mongo.database.usuarios.insert_one(usuario)
        
        return jsonify({"message": "Usuario registrado exitosamente", "id": str(result.inserted_id)}), 201

    @app.route('/login', methods=['POST'])
    def login_user():
        data = request.get_json()
        if not data or not all(k in data for k in ("correo", "password")):
            return jsonify({"error": "Faltan campos obligatorios"}), 400
        
        usuario = mongo.database.usuarios.find_one({"correo": data["correo"]})
        if not usuario or not check_password_hash(usuario["password"], data["password"]):
            return jsonify({"error": "Credenciales incorrectas"}), 401

        session['user_id'] = str(usuario['_id'])
        name = usuario['nombre'] +" "+ usuario['apellido']
        img = usuario['img']
        idUser = str(usuario['_id'])
        return jsonify({"message": "Inicio de sesión exitoso", "user_id": session['user_id'], "user_name": name, "user_img": img }), 200
        
    @app.route("/get_user", methods=["GET"])
    def get_user():
        user_id = request.args.get('id')
        if not user_id:
            return jsonify({"error": "ID de usuario no proporcionado"}), 400
        
        try:
            usuario = mongo.database.usuarios.find_one({"_id": ObjectId(user_id)})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        
        if not usuario:
            return jsonify({"error": "Usuario no encontrado"}), 404
        
        usuario["_id"] = str(usuario["_id"])  # Convertir ObjectId a string para serialización
        return jsonify({"user": usuario}), 200

    @app.route("/update_user", methods=["PUT"])
    def update_user():
        user_id = request.json.get('id')
        update_data = {
            "nombre": request.json.get('nombre'),
            "correo": request.json.get('correo'),
            "img": request.json.get('img')
        }

        if not user_id or not ObjectId.is_valid(user_id):
            return jsonify({"error": "ID de usuario inválido"}), 400

        result = mongo.database.usuarios.update_one({"_id": ObjectId(user_id)}, {"$set": update_data})

        if result.matched_count == 0:
            return jsonify({"error": "Usuario no encontrado"}), 404

        return jsonify({"message": "Usuario actualizado con éxito"}), 200

    @app.route('/check_integrations', methods=['GET'])
    def check_integrations():
        email = request.args.get('email')

        if not email:
            return jsonify({"error": "Correo electrónico no proporcionado"}), 400

        usuario = mongo.database.usuarios.find_one({"correo": email})
        
        if not usuario:
            return jsonify({"error": "Usuario no encontrado"}), 404

        if not usuario.get('integrations') or len(usuario['integrations']) == 0:
            return jsonify({"message": "Usuario sin integraciones"}), 200
        
        return jsonify({"message": "Usuario con integraciones", "integrations": usuario['integrations']}), 200

    @app.route('/get_integrations', methods=['GET'])
    def get_integrations():
        user_email = request.args.get("email")
        
        user = mongo.database.usuarios.find_one({"correo": user_email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        # Devolvemos las integraciones que tiene el usuario
        return jsonify({"integrations": user.get("integrations", {})}), 200

    @app.route('/add_integration', methods=['POST'])
    def add_integration():
        request_data = request.get_json()
        user_email = request_data.get("email")
        integration_name = request_data.get("integration")
        token = request_data.get("token")
        expires_in = request_data.get("expires_in")

        if not all([user_email, integration_name, token]):
            return jsonify({"error": "Faltan campos obligatorios"}), 400

        # Verificar que el usuario exista
        user = mongo.database.usuarios.find_one({"correo": user_email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        # Crear el objeto para la integración
        integration_data = {
            "token": token,
            "timestamp": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')  # Guardar la fecha y hora en UTC
        }

        # Si no es Notion ni Slack, agregar el campo expires_in
        if integration_name not in ["Notion", "Slack", "ClickUp"]:
            if expires_in is None:
                return jsonify({"error": "El campo 'expires_in' es obligatorio para esta integración"}), 400
            integration_data["expires_in"] = int(expires_in)

        # Actualizar el campo de integraciones
        # Verifica si la integración ya existe, de lo contrario, la agrega
        mongo.database.usuarios.update_one(
            {"correo": user_email},
            {"$set": {f"integrations.{integration_name}": integration_data}}
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

    @app.route('/search/gmail', methods=["GET"])
    def search_gmail(query):
        email = request.args.get('email')
        try:
            user = mongo.database.usuarios.find_one({'correo': email})
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            gmail_integration = user.get('integrations', {}).get('Gmail', None)
            if gmail_integration:
                gmail_token = gmail_integration.get('token', None)
                gmail_expires_in = gmail_integration.get('expires_in', None)
            else:
                gmail_token = None
                gmail_expires_in = None
            
            if not gmail_token:
                return jsonify({"error": "Token de Gmail no disponible"}), 400

            if not query:
                return jsonify({"error": "No se proporcionó un término de búsqueda"}), 400
            
            # Si la query está vacía después de filtrar, devolvemos un error
            if not query:
                return jsonify({"error": "No se proporcionó un término de búsqueda válido"}), 400

            if any(palabra in query for palabra in ["ultimo", "último"]):    
                if any(palabra in query for palabra in ["mi", "mí", "mis"]):
                    query = "is:inbox"
                    params = {"q": query, "maxResults": 1 }
                    response = requests.get(url, headers=headers, params=params)
                    response.raise_for_status()
                    messages = response.json().get('messages', [])
                    if not messages:
                        return jsonify({"message": "No se encontraron resultados en Gmail"}), 200

                    keywords = query.split()
                    search_results = []
                    for message in messages:
                        message_id = message['id']
                        message_response = requests.get(
                            f'https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}', headers=headers
                        )

                        if message_response.status_code == 200:
                            message_data = message_response.json()
                            message_headers = message_data.get('payload', {}).get('headers', [])
                            sender = next((header['value'] for header in message_headers if header['name'] == 'From'), "Sin remitente")
                            date = next((header['value'] for header in message_headers if header['name'] == 'Date'), "Sin fecha")
                            subject = next((header['value'] for header in message_headers if header['name'] == 'Subject'), "Sin asunto")

                            body = ""
                            # Decodificar el cuerpo del mensaje
                            if 'parts' in message_data['payload']:
                                for part in message_data['payload']['parts']:
                                    if part['mimeType'] == 'text/html':
                                        html_body = decode_message_body(part['body']['data'])
                                        body = extract_text_from_html(html_body)
                                        break
                            else:
                                if message_data['payload'].get('body', {}).get('data'):
                                    html_body = decode_message_body(message_data['payload']['body']['data'])
                                    body = extract_text_from_html(html_body)

                            # Crear la URL del correo
                            mail_url = f"https://mail.google.com/mail/u/0/#inbox/{message_id}"

                            # Añadir a los resultados (removí filtros problemáticos)
                            search_results.append({
                                'from': sender,
                                'date': date,
                                'subject': subject,
                                'body': body,
                                'link': mail_url
                            })
            else:
                url = "https://www.googleapis.com/gmail/v1/users/me/messages"
                headers = {
                    'Authorization': f"Bearer {gmail_token}"
                }
                params = {"q": query, "maxResults": 5 }
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()

                messages = response.json().get('messages', [])
                if not messages:
                    return jsonify({"message": "No se encontraron resultados en Gmail"}), 200

                keywords = query.split()
                search_results = []
                for message in messages:
                    message_id = message['id']
                    message_response = requests.get(
                        f'https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}', headers=headers
                    )

                    if message_response.status_code == 200:
                        message_data = message_response.json()
                        message_headers = message_data.get('payload', {}).get('headers', [])
                        sender = next((header['value'] for header in message_headers if header['name'] == 'From'), "Sin remitente")
                        date = next((header['value'] for header in message_headers if header['name'] == 'Date'), "Sin fecha")
                        subject = next((header['value'] for header in message_headers if header['name'] == 'Subject'), "Sin asunto")

                        body = ""
                        # Decodificar el cuerpo del mensaje
                        if 'parts' in message_data['payload']:
                            for part in message_data['payload']['parts']:
                                if part['mimeType'] == 'text/html':
                                    html_body = decode_message_body(part['body']['data'])
                                    body = extract_text_from_html(html_body)
                                    break
                        else:
                            if message_data['payload'].get('body', {}).get('data'):
                                html_body = decode_message_body(message_data['payload']['body']['data'])
                                body = extract_text_from_html(html_body)

                        # Crear la URL del correo
                        mail_url = f"https://mail.google.com/mail/u/0/#inbox/{message_id}"

                        # Añadir a los resultados (removí filtros problemáticos)
                        search_results.append({
                            'from': sender,
                            'date': date,
                            'subject': subject,
                            'body': body,
                            'link': mail_url
                        })

            if not search_results:
                return jsonify({"message": "No se encontraron resultados que coincidan con la solicitud"}), 200
            return jsonify(search_results)

        except requests.RequestException as e:
            return jsonify({"error": "Error al realizar la solicitud a Gmail", "details": str(e)}), 500
        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500

    @app.route('/search/notion', methods=['GET'])
    def search_notion(query):
        email = request.args.get('email')
        simplified_results = []
        try:
            # Verificar usuario en la base de datos
            user = mongo.database.usuarios.find_one({'correo': email})
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            # Verificar token de Notion
            notion_integration = user.get('integrations', {}).get('Notion', None)
            notion_token = notion_integration.get('token') if notion_integration else None
            if not notion_token:
                return jsonify({"error": "Token de Notion no disponible"}), 400

            # Limpiar el query
            if "proyecto" in query:
                query = query.split("proyecto", 1)[1].strip() 
            if "compañia" in query:
                query = query.split("compañia", 1)[1].strip()
            if "empresa" in query:
                query = query.split("empresa", 1)[1].strip()

            # Verificar término de búsqueda
            if not query:
                return jsonify({"error": "No se proporcionó un término de búsqueda"}), 400

            # Configuración de solicitud a Notion
            url = 'https://api.notion.com/v1/search'
            headers = {
                'Authorization': f'Bearer {notion_token}',
                'Notion-Version': '2022-06-28',
                'Content-Type': 'application/json'
            }
            data = {"query": query}
            
            # Realizar solicitud a Notion
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            notion_response = response.json()

            # Procesar resultados
            results = notion_response.get("results", [])
            if not results:
                return jsonify({"error": "No se encontraron resultados en Notion"}), 404

            for result in results:
                page_info = {
                    "id": result["id"],
                    "url": result.get("url"),
                    "properties": {}
                }

                properties = result.get("properties", {})
                for property_name, property_value in properties.items():
                    # Procesar propiedades relevantes
                    if property_value.get("type") == "status":
                        page_info["properties"][property_name] = property_value["status"].get("name", None)
                    elif property_name == "Nombre" and property_value.get("title"):
                        page_info["properties"][property_name] = property_value["title"][0]["plain_text"]

                # Filtrar resultados relevantes
                if (
                    'Nombre' in page_info["properties"]
                    and query.lower() in page_info["properties"]["Nombre"].lower()
                ):
                    simplified_results.append(page_info)

            # Verificar si hay resultados simplificados
            if not simplified_results:
                return jsonify({"error": "No se encontraron resultados relevantes en Notion"}), 404

            return jsonify(simplified_results)

        except requests.RequestException as e:
            return jsonify({"error": "Error al realizar la solicitud a Notion", "details": str(e)}), 500
        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500

    @app.route('/search/slack', methods=['GET'])
    def search_slack(query):
        email = request.args.get('email')
        try:
            # Verificar existencia de usuario
            user = mongo.database.usuarios.find_one({'correo': email})
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            # Verificar integración con Slack
            slack_integration = user.get('integrations', {}).get('Slack', None)
            if slack_integration:
                slack_token = slack_integration.get('token', None)
            else:
                slack_token = None

            if not slack_token:
                return jsonify({"error": "No se encuentra integración con Slack"}), 404

            # Verificar término de búsqueda
            if not query:
                return jsonify({"error": "No se proporcionó un término de búsqueda"}), 400

            # Preparar solicitud a la API de Slack
            url = 'https://slack.com/api/search.messages'
            headers = {
                'Authorization': f'Bearer {slack_token}',
                'Content-Type': 'application/json'
            }
            params = {'query': query}

            # Realizar la solicitud
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()  # Levantar excepción en caso de error HTTP

            data = response.json()

            # Validar respuesta de Slack
            if not data.get('ok'):
                return jsonify({"error": "Error al buscar en Slack", "details": data.get('error', 'Desconocido')}), response.status_code

            # Asegurarse de que los mensajes existen y son válidos
            messages = data.get("messages", {}).get("matches", [])
            if not messages:
                return jsonify({"message": "No se encontraron resultados en Slack"}), 200

            # Procesar los resultados
            slack_results = [
                {
                    "channel": message.get("channel", {}).get("name", "Sin canal"),
                    "user": message.get("username", "Desconocido"),
                    "text": message.get("text", "Sin texto"),
                    "ts": message.get("ts", "Sin timestamp"),
                    "link": f"https://slack.com/archives/{message.get('channel')}/p{message.get('ts').replace('.', '')}"
                }
                for message in messages
            ]

            return jsonify(slack_results)

        except requests.exceptions.RequestException as e:
            return jsonify({"error": "Error al conectarse a Slack", "details": str(e)}), 500
        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500

    def parse_fecha_relativa(fecha_str):
        """
        Parsea una fecha relativa como '1 mes', '2 días', etc., y devuelve un objeto datetime.
        """
        # Definir las unidades que se pueden usar
        unidades = {
            "día": "days",
            "mes": "months",
            "año": "years",
            "hora": "hours",
            "minuto": "minutes",
            "segundo": "seconds"
        }

        # Expresión regular para buscar el número y la unidad
        pattern = r'(\d+)\s*(día|mes|año|hora|minuto|segundo)s?'
        match = re.match(pattern, fecha_str)

        if match:
            cantidad = int(match.group(1))
            unidad = match.group(2)
            
            # Convertir a la unidad apropiada de relativedelta
            kwargs = {unidades[unidad]: cantidad}
            
            # Restar el tiempo a la fecha actual
            return datetime.now() - relativedelta(**kwargs)
    
        raise ValueError("Formato de fecha relativa no válido.")

    @app.route('/search/outlook', methods=['GET'])
    def search_outlook(query):
        email = request.args.get('email')
        try:
            user = mongo.database.usuarios.find_one({'correo': email})
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            outlook_integration = user.get('integrations', {}).get('Outlook', None)
            if outlook_integration:
                outlook_token = outlook_integration.get('token', None)
                outlook_expires_in = outlook_integration.get('expires_in', None)
            else:
                outlook_token = None
                outlook_expires_in = None

            if not outlook_token:
                return jsonify({"error": "Token de Outlook no disponible"}), 400

            if not query:
                return jsonify({"error": "No se proporcionó un término de búsqueda"}), 400

            # Utilizar comillas para buscar la frase exacta
            search_query = f'"{query}"'

            url = 'https://graph.microsoft.com/v1.0/me/messages'
            headers = {
                'Authorization': f"Bearer {outlook_token}",
                'Content-Type': 'application/json'
            }

            params = {
                '$search': search_query, '$top':10
            }

            response = requests.get(url, headers=headers, params=params)
            keywords = query.lower().split()
            # Verificar si la respuesta tiene un código de error
            if response.status_code != 200:
                print("Error en la respuesta de Outlook:", response.status_code, response.text)
                return jsonify({"error": "Error en la respuesta de Outlook", "details": response.text}), 500

            results = response.json().get('value', [])
            if not results:
                return jsonify({"message": "No se encontraron resultados en Outlook"}), 200

            search_results = []
            for result in results:
                body = to_ascii(result.get("bodyPreview", ""))
                if any(keyword in result.get("subject").lower() for keyword in keywords):
                    result_info = {
                        "subject": result.get("subject"),
                        "receivedDateTime": result.get("receivedDateTime"),
                        "sender": result.get("sender", {}).get("emailAddress", {}).get("address"),
                        "bodyPreview": body,
                        "webLink": result.get("webLink")
                    }
                    search_results.append(result_info)

            return jsonify(search_results)

        except requests.RequestException as e:
            return jsonify({"error": "Error al realizar la solicitud a Outlook", "details": str(e)}), 500
        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500

    def get_hubspot_headers(token):
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    @app.route('/search/hubspot', methods=['GET'])
    def search_hubspot(query):
        if not query:
            return jsonify({"error": "No se proporcionó un término de búsqueda"}), 400

        # Buscar usuario en la base de datos
        email = request.args.get("email")
        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        # Obtener el token de HubSpot
        hubspot_integration = user.get('integrations', {}).get('HubSpot', None)
        if not hubspot_integration:
            return jsonify({"error": "Integración con HubSpot no configurada"}), 400

        hubspot_token = hubspot_integration.get('token', None)
        if not hubspot_token:
            return jsonify({"error": "Token de HubSpot no disponible"}), 400

        headers = get_hubspot_headers(hubspot_token)
        search_results = {}

        if "n/a" in query:
            return jsonify({"message": "No hay resultados en HubSpot"}), 200

        # Buscar todos los contactos
        if query.lower() == "todos mis contactos":
            search_data = {
                "filters": [],
                "properties": ["firstname", "lastname", "email", "hubspot_owner_id", "company"]
            }
            response = requests.post(
                "https://api.hubapi.com/crm/v3/objects/contacts/search",
                headers=headers,
                json=search_data
            )
            if response.status_code == 200:
                contacts = response.json().get("results", [])
                search_results["contacts"] = [
                    {
                        "firstname": contact["properties"].get("firstname", "N/A"),
                        "lastname": contact["properties"].get("lastname", "N/A"),
                        "email": contact["properties"].get("email", "N/A"),
                        "owner": contact["properties"].get("hubspot_owner_id", "N/A"),
                        "company": contact["properties"].get("company", "N/A")
                    }
                    for contact in contacts
                ]
                if not search_results["contacts"]:
                    search_results["contacts"] = {"message": "No se encontraron contactos."}
            else:
                return jsonify({"error": f"Error al buscar en HubSpot: {response.status_code} {response.text}"}), response.status_code

        # Búsqueda de contactos, negocios y empresas
        elif "contacto" in query.lower() or "contactos" in query.lower():
            search_data = {
                "filters": [],
                "properties": ["firstname", "lastname", "email", "phone", "company", "hubspot_owner_id"]
            }
            response = requests.post(
                "https://api.hubapi.com/crm/v3/objects/contacts/search",
                headers=headers,
                json=search_data
            )
            if response.status_code == 200:
                contacts = response.json().get("results", [])
                search_results["contacts"] = [
                    {
                        "firstname": contact["properties"].get("firstname", "N/A"),
                        "lastname": contact["properties"].get("lastname", "N/A"),
                        "email": contact["properties"].get("email", "N/A"),
                        "company": contact["properties"].get("company", "N/A"),
                        "owner": contact["properties"].get("hubspot_owner_id", "N/A"),
                        "phone": contact["properties"].get("phone", "N/A")
                    }
                    for contact in contacts
                ]
                if not search_results["contacts"]:
                    search_results["contacts"] = {"message": f"No se encontraron contactos{(' para ' + query.split('compañia', 1)[1].strip()) if query.split('compañia', 1)[1].strip() else ''}."}
            else:
                return jsonify({"error": f"Error al buscar en HubSpot: {response.status_code} {response.text}"}), response.status_code

        elif "negocio" in query.lower() or "negocios" in query.lower():
            search_data = {
                "filters": [],
                "properties": ["dealname", "amount", "dealstage", "hubspot_owner_id", "company"]
            }
            response = requests.post(
                "https://api.hubapi.com/crm/v3/objects/deals/search",
                headers=headers,
                json=search_data
            )
            stage_mapping = {
                "qualifiedtobuy": "Calificado para comprar",
                "appointmentscheduled": "Cita programada",
                "noactivity": "Sin actividad",
                "presentationscheduled": "Presentación programada",
                "quoteaccepted": "Propuesta aceptada",
                "contractsent": "Contrato enviado",
                "closedwon": "Cierre ganado",
                "closedlost": "Cierre perdido"
            }
            if response.status_code == 200:
                deals = response.json().get("results", [])
                search_results["deals"] = [{
                    "dealname": deal["properties"].get("dealname", "N/A"),
                    "amount": deal["properties"].get("amount", "N/A"),
                    "dealstage": stage_mapping.get(deal["properties"].get("dealstage", "N/A"), "N/A"),
                    "owner": deal["properties"].get("hubspot_owner_id", "N/A"),
                    "company": deal["properties"].get("company", "N/A")
                }
                for deal in deals
                ]
            else:
                return jsonify({"error": f"Error al buscar en HubSpot: {response.status_code} {response.text}"}), response.status_code

        # Búsqueda de empresas
        elif "empresa" in query.lower() or "compañia" in query.lower():
            search_data = {
                "filters": [],
                "properties": ["name", "industry", "size", "hubspot_owner_id"]
            }
            response = requests.post(
                "https://api.hubapi.com/crm/v3/objects/companies/search",
                headers=headers,
                json=search_data
            )
            if response.status_code == 200:
                companies = response.json().get("results", [])
                search_results["companies"] = [
                    {
                        "name": company["properties"].get("name", "N/A"),
                        "industry": company["properties"].get("industry", "N/A"),
                        "size": company["properties"].get("size", "N/A"),
                        "owner": company["properties"].get("hubspot_owner_id", "N/A")
                    }
                    for company in companies
                ]
                if not search_results["companies"]:
                    search_results["companies"] = {"message": "No se encontraron empresas."}
            else:
                return jsonify({"error": f"Error al buscar en HubSpot: {response.status_code} {response.text}"}), response.status_code

        else:
            return jsonify({"error": "Tipo de solicitud no soportado"}), 400

        return jsonify(search_results)


    def extract_links(results, key):
        if isinstance(results, list):
            return [item.get(key) for item in results if key in item]
        return []

    
    def generate_prompt(query, search_results):
        # Extraer solo la información relevante de cada fuente
        results = {}
        # Gmail Results (extraer información relevante)
        gmail_results = "\n".join([ 
            f"De: {email.get('from', 'Desconocido')} | Asunto: {email.get('subject', 'Sin asunto')} | Fecha: {email.get('date', 'Sin fecha')} | Body: {email.get('body', 'Sin cuerpo')}" 
            for email in search_results.get('gmail', []) if isinstance(email, dict)
        ]) or "No se encontraron correos relacionados en Gmail."

        # Slack Results (extraer información relevante)
        slack_results = "\n".join([
            f"Canal: {msg.get('channel', 'Desconocido')} | Usuario: {msg.get('user', 'Desconocido')} | Mensaje: {msg.get('text', 'Sin mensaje')} | Fecha: {msg.get('ts', 'Sin fecha')}"
            for msg in search_results.get('slack', []) if isinstance(msg, dict)
        ]) or "No se encontraron mensajes relacionados en Slack."

        # Notion Results (extraer información relevante)
        notion_results = "\n".join([ 
            f"Página ID: {page.get('id', 'Sin ID')} | "
            f"Nombre: {page.get('properties', {}).get('Nombre', 'Sin Nombre')} | "
            f"Estado: {page.get('properties', {}).get('Estado', 'Sin Estado')} | "
            f"URL: {page.get('url', 'Sin URL')} | "
            f"Última edición: {page.get('last_edited_time', 'Sin edición')}"
            for page in search_results.get('notion', []) if isinstance(page, dict)
        ]) or "No se encontraron notas relacionadas en Notion."

        # Outlook Results (extraer información relevante)
        outlook_results = "\n".join([
            f"De: {email.get('sender', 'Desconocido')} | Asunto: {email.get('subject', 'Sin asunto')} | Fecha: {email.get('receivedDateTime', 'Sin fecha')}"
            for email in search_results.get('outlook', []) if isinstance(email, dict)
        ]) or "No se encontraron correos relacionados en Outlook."

        # HubSpot Results (extraer información relevante)
        hubspot_results = []
        hubspot_data = search_results.get("hubspot", {})

        try:
            if "contacts" in hubspot_data:
                contacts = hubspot_data["contacts"]
                if isinstance(contacts, list) and contacts:
                    hubspot_results.append("Contactos:\n" + "\n".join([ 
                        f"Nombre: {contact.get('firstname', 'N/A')} {contact.get('lastname', 'N/A')} | Correo: {contact.get('email', 'N/A')} | Teléfono: {contact.get('phone', 'N/A')} | Compañía: {contact.get('company', 'N/A')}"
                        for contact in contacts
                    ]))

            if "companies" in hubspot_data:
                companies = hubspot_data["companies"]
                if isinstance(companies, list) and companies:
                    hubspot_results.append("Compañías:\n" + "\n".join([ 
                        f"Nombre: {company.get('name', 'N/A')} | Industria: {company.get('industry', 'N/A')} | Tamaño: {company.get('size', 'N/A')}"
                        for company in companies
                    ]))

            if "deals" in hubspot_data:
                deals = hubspot_data["deals"]
                if isinstance(deals, list) and deals:
                    hubspot_results.append("Negocios:\n" + "\n".join([ 
                        f"Nombre: {deal.get('dealname', 'N/A')} | Estado: {deal.get('dealstage', 'N/A')} | Monto: {deal.get('amount', 'N/A')}"
                        for deal in deals
                    ]))

        except Exception as e:
            hubspot_results.append(f"Error procesando datos de HubSpot: {str(e)}")

        hubspot_results = "\n".join(hubspot_results) or "No se encontraron resultados relacionados en HubSpot."

        # Nuevas APIs: ClickUp, Dropbox, Asana, OneDrive, Teams

        clickup_results = "\n".join([
            f"Tarea: {task.get('task_name', 'Sin nombre')} | "
            f"Estado: {task.get('status', 'Sin estado')} | "
            f"Prioridad: {task.get('priority', 'Sin prioridad')} | "
            f"Asignado a: {', '.join(task.get('assignees', ['Sin asignar']))} | "
            f"Fecha de vencimiento: {task.get('due_date') if task.get('due_date') else 'Sin fecha'} | "
            f"Lista: {task.get('list', 'Sin lista')} | "
            f"URL: {task.get('url', 'Sin URL')}"
            for task in search_results.get('clickup', []) if isinstance(task, dict)
        ]) or "No se encontraron tareas relacionadas en ClickUp."

        # Dropbox Results
        dropbox_results = "\n".join([
            f"Archivo: {file.get('name', 'Sin nombre')} | Tamaño: {file.get('size', 'Desconocido')} | Fecha de modificación: {file.get('modified', 'Sin fecha')}"
            for file in search_results.get('dropbox', []) if isinstance(file, dict)
        ]) or "No se encontraron archivos relacionados en Dropbox."

        # Asana Results
        asana_results = "\n".join([
            f"Tarea: {task.get('task_name', 'Sin nombre')} | "
            f"Estado: {task.get('status', 'Sin estado')} | "
            f"Fecha de vencimiento: {task.get('due_date', 'Sin fecha')} | "
            f"Asignado a: {task.get('assignee', 'Sin asignar')} | "
            f"Proyectos: {task.get('projects', 'Sin proyectos asignados')} | "
            f"URL: {task.get('url', 'Sin URL')}"
            for task in search_results.get('asana', []) if isinstance(task, dict)
        ]) or "No se encontraron tareas relacionadas en Asana."

        # OneDrive Results
        onedrive_results = "\n".join([
            f"Archivo: {file.get('name', 'Sin nombre')} | Tamaño: {file.get('size', 'Desconocido')} | Fecha de modificación: {file.get('modified', 'Sin fecha')}"
            for file in search_results.get('onedrive', []) if isinstance(file, dict)
        ]) or "No se encontraron archivos relacionados en OneDrive."

        # Teams Results
        teams_results = "\n".join([
            f"Canal: {msg.get('channel', 'Desconocido')} | Usuario: {msg.get('user', 'Desconocido')} | Mensaje: {msg.get('text', 'Sin mensaje')} | Fecha: {msg.get('ts', 'Sin fecha')}"
            for msg in search_results.get('teams', []) if isinstance(msg, dict)
        ]) or "No se encontraron mensajes relacionados en Teams."

        google_drive_results = "\n".join([
            f"Archivo: {file.get('title', 'Sin nombre')} | Tipo: {file.get('type', 'Desconocido')} | Enlace: {file.get('url', 'Sin enlace')}"
            for file in search_results.get('googledrive', []) if isinstance(file, dict)
        ]) or "No se encontraron archivos relacionados en Google Drive."
        
        # Crear el prompt final
        prompt = f"""Respuesta concisa a la consulta: "{query}"

        Resultados de la búsqueda:

        Gmail:
        {gmail_results}

        Notion:
        {notion_results}

        Slack:
        {slack_results}

        Outlook:
        {outlook_results}

        HubSpot:
        {hubspot_results}

        ClickUp:
        {clickup_results}

        Dropbox:
        {dropbox_results}

        Google Drive:
        {google_drive_results}

        Asana:
        {asana_results}

        OneDrive:
        {onedrive_results}

        Teams:
        {teams_results}

        Responde de forma humana, concisa y en parrafo:
        Quiero que respondas a la query que mando el usuario en base a la informacion que se te agrego por cada api, solo puedes y debes usar esa información para contestar
        - En dado caso que no exista información en ninguna api, contesta de manera amable que si puede mejorar su prompt o lo que desea encontrar
        - En dado caso exista la información en una api y en unas no, solo contesta con la que si existe la información.
        - En el caso de HubSpot, cuando se soliciten contactos de una compañía y el campo 'compañía' esté vacío, valida que el nombre de la empresa pueda obtenerse del dominio del correo electrónico (es decir, todo lo que sigue después del '@'). Si el dominio es, por ejemplo, 'empresa.com', entonces considera que la empresa es 'empresa'. Asegúrate de no responder con registros irrelevantes y solo muestre los resultados de contactos relacionados con el dominio del correo o con el nombre de la compañía.
        Necesito que tu respuesta sea concisa a la query enviada por el usuario (toma el formato de "Suggested Answers" de Guru para guiarte) incluye emojis de ser posible para hacer mas amigable la interacción con el usuario.
        No respondas 'Respuesta:' si no que responde de manera natural como si fuese una conversación, tampoco agregues enlaces.
        Analiza antes de responder ya que algunas apis te devuelven información general, si tu piensas que no se responde de manera amena la pregunta contesta de manera amable si puede mejorar su prompt o que desea encontrar
        Información relevante a tomar en cuenta bodys de correos, fechas y Remitente (De:)
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
    
    def extract_links_from_datas(datas):
        """Extrae los enlaces y los nombres (asunto/página/mensaje) de cada API según la estructura de datos recibida."""
        results = {
            'gmail': [],
            'slack': [],
            'notion': [],
            'outlook': [],
            'clickup': [],
            'hubspot': [],
            'dropbox': [],
            'asana': [],
            'onedrive': [],
            'teams': []  # Añadimos Teams al diccionario de resultados
        }

        # Extraer links y asunto de Gmail (vienen en una lista de diccionarios)
        if isinstance(datas.get('gmail'), list):  # Comprobamos si es una lista
            results['gmail'] = [
                {'link': item['link'], 'subject': item.get('subject', 'No subject')} 
                for item in datas['gmail'] if 'link' in item
            ]

        # Extraer links y mensaje de Slack (viene en una lista dentro de una tupla)
        if isinstance(datas.get('slack'), list):  # Cambié para verificar si es una lista
            results['slack'] = [
                {'link': item['link'], 'message': item.get('message', 'No message')}
                for item in datas['slack'] if 'link' in item
            ]

        # Extraer links y nombre de página de Notion (viene en una lista)
        if isinstance(datas.get('notion'), list):  # Verificamos que sea lista
            results['notion'] = [
                {'url': item['url'], 'page_name': item.get('properties', {}).get('Nombre', 'Sin Nombre')}
                for item in datas['notion'] if 'url' in item
            ]

        # Extraer links y asunto de Outlook (viene en una lista dentro de una tupla)
        if isinstance(datas.get('outlook'), list):  # Cambié para verificar si es lista
            results['outlook'] = [
                {'webLink': item['webLink'], 'subject': item.get('subject', 'No subject')}
                for item in datas['outlook'] if 'webLink' in item
            ]

        if isinstance(datas.get("clickup"), list):
            results['clickup'] = [
                {'url': item['url'], 'task_name': item.get('task_name', 'Sin Nombre')}
                for item in datas.get("clickup") if 'url' in item
            ]

        return results
                
    @app.route("/api/chatAi", methods=["POST"])
    def apiChat():
        data = request.get_json()
        user_messages = data.get("messages", [])
        last_ai_response = ""
        hoy = datetime.today().strftime('%Y-%m-%d')
        system_message = """
        Eres Shiffu, un asistente virtual amigable y útil en su versión alfa. 
        Ayudas a los usuarios respondiendo preguntas de manera clara y humana. 
        Si el usuario saluda, responde de forma cálida y amigable como si estuvieras manteniendo una conversación fluida.
        Si el usuario cuenta algo sobre cómo se siente o alguna situación especial, responde de manera comprensiva.
        En general, responde con naturalidad y empatía a las interacciones.
        Tambien eres un analizador de prompts para distintas apis (Gmail, Hubspot, Outlook, Slack, Notion, etc)
        """

        ia_response = "Lo siento, no entendí tu mensaje. ¿Puedes reformularlo?"

        if user_messages:
            
            try:
                last_message = user_messages[-1].get("content", "").lower()
                prompt = (
                    f"Interpreta el siguiente mensaje del usuario: '{last_message}'. "
                    f"TEN EN CUENTA QUE LA FECHA DE HOY ES {hoy}\n"
                    f"1. LO MÁS IMPORTANTE: Identifica si es un saludo, una solicitud GET o POST, o si se refiere a la respuesta anterior enviada por la IA.\n"
                    f"   - Si es un saludo, responde con 'Es un saludo'.\n"
                    f"   - Si es una solicitud GET, responde con 'Es una solicitud GET'.\n"
                    f"   - Si es una solicitud POST, responde con 'Es una solicitud POST'.\n"
                    f"   - Si es una solicitud que menciona algo sobre una conversación o respuesta anterior (ejemplo: 'de lo que hablamos antes', 'en la conversación anterior', 'acerca del mensaje previo', 'respuesta anterior', 'de que trataba', etc), responde con 'Se refiere a la respuesta anterior'.\n"
                    f"En caso de ser una solicitud GET o POST, desglosa las partes relevantes para cada API (Gmail, Notion, Slack, HubSpot, Outlook, ClickUp, Dropbox, Asana, Google Drive, OneDrive, Teams).\n"
                    f"Asegúrate de lo siguiente:\n"
                    f"ESPECIFICAMENTE SI Y SOLO SI LA SOLICITUD ES TIPO GET"
                    f"- No coloques fechas en ninguna query, ni after ni before'.\n"
                    f"- Si se menciona un nombre propio (detectado si hay una combinación de nombre y apellido), responde 'from: <nombre completo>'.\n"
                    f"- Si se menciona un correo electrónico, responde 'from: <correo mencionado>'. Usa una expresión regular para verificar esto.\n"
                    f"- Usa la misma query de Gmail también para Outlook.\n"
                    f"- Usa la misma query de Notion en Asana y Clickup"
                    f"- En HubSpot, identifica qué tipo de objeto busca el usuario (por ejemplo: contacto, compañía, negocio, empresa, tarea, etc.) y ajusta la query de forma precisa. "
                    f"El valor debe seguir esta estructura: \"<tipo de objeto> <query>\", como por ejemplo \"contacto osuna\" o \"compañía osuna\".\n\n"
                    f"Para Slack, adapta la query de Gmail.\n\n"
                    f"En ClickUp, si el usuario menciona tareas o proyectos (también toma en cuenta siempre la query de Notion), ajusta la consulta a su nombre o identificador específico.\n"
                    f"""
                        Genera una consulta para Dropbox, OneDrive y Google Drive basada en el mensaje del usuario.
                            
                            - Si menciona un archivo: "archivo:<nombre>"
                            - Si menciona una carpeta: "carpeta:<nombre>"
                            - Si menciona un archivo dentro de una carpeta: "archivo:<nombre> en carpeta:<ubicación>"
                            - Si no se puede interpretar una búsqueda para Dropbox, devuelve "N/A"
                    \n"""
                    f"En Asana, si menciona un proyecto o tarea, ajusta la consulta a ese nombre específico.\n"
                    f"En Google Drive, si menciona un archivo, carpeta o documento, ajusta la consulta a su nombre o ubicación.\n"
                    f"En Teams, ajusta la consulta según lo que menciona el usuario:\n"
                    f"- Si menciona un canal (ejemplo: 'en el canal de proyectos', 'en #soporte'): usa \"channel:<nombre del canal>\".\n"
                    f"- Si el usuario menciona que está 'hablando con', 'conversando con', 'chateando con' o términos similares seguidos de un nombre propio o usuario como: 'pvasquez-2018044', usa: \"conversation with:<nombre> <palabras clave>\", asegurándote de incluir cualquier referencia a temas mencionados.\n"
                    f"- Si menciona un tema específico sin un contacto, pero da detalles del contenido, usa \"message:<palabras clave>\".\n"
                    f"- Si el usuario usa términos como 'mensaje sobre', 'hablamos de', 'tema de conversación', extrae las palabras clave y úsalas en \"message:<palabras clave>\".\n"
                    f"- Si no se puede interpretar una búsqueda específica para Teams, devuelve \"N/A\".\n"
                    f"- SI EL USUARIO MENCIONA EXPLICITAMENTE 'TEAMS' O 'MICROSOFT TEAMS' HAZ LA QUERY\n"
                     f"- SI EL USUARIO MENCIONA EXPLICITAMENTE 'TEAMS' O 'MICROSOFT TEAMS' HAZ LA QUERY"
                    f"Estructura del JSON:\n"
                    f"{{\n"
                    f"    \"gmail\": \"<query para Gmail> Se conciso y evita palabras de solicitud y solo pon la query y evita los is:unread\",\n"
                    f"    \"notion\": \"<query para Notion o 'N/A' si no aplica, siempre existira mediante se mencionen status de proyectos o tareas. O se mencionen compañias, empresas o proyectos en la query>\",\n"
                    f"    \"slack\": \"<query para Slack o 'N/A' si no aplica, usa la de Gmail pero más redireccionada a como un mensaje, si es una solicitud, hazla más informal y directa>\",\n"
                    f"    \"hubspot\": \"Si el usuario menciona 'contactos de <empresa o nombre>', responde 'contacto <empresa o nombre>'. Si menciona 'empresas de <sector>', responde 'empresa <sector>'. Si menciona 'negocio >nombre>' o 'negocio de <empresa>', responde 'negocio <sector o empresa>'. Si menciona 'compañías de <sector>', responde 'compañía <sector>'. Si el usuario menciona un contacto específico con un nombre propio y pide información (como número, correo, etc.), responde 'contacto <nombre> (<campo solicitado>)'.\",\n"
                    f"    \"outlook\": \"<query para Outlook, misma que Gmail>\",\n"
                    f"    \"clickup\": \"<query para ClickUp, o 'N/A' si no aplica. Siempre existira si y solo si se mencionan status de proyectos, tareas, compañías, empresas, proyectos específicos o fechas en la query. Además, se realizará la búsqueda en tareas, calendarios, diagramas de Gantt y tablas relacionadas con el equipo y las tareas asociadas, dependiendo de los elementos presentes en la consulta.>"
                    f"    \"dropbox\": \"<query para Dropbox o 'N/A' si no aplica>\",\n"
                    f"    \"asana\": \"<query para Asana o 'N/A' si no aplica>\",\n"
                    f"    \"googledrive\": \"<query para Google Drive o 'N/A' si no aplica>\",\n"
                    f"    \"onedrive\": \"<query para OneDrive o 'N/A' si no aplica>\",\n"
                    f"    \"teams\": \"<query para Teams o 'N/A' si no aplica>\"\n"
                    f"}}\n\n"
                    f"El JSON debe incluir solo información relevante extraída del mensaje del usuario y ser fácilmente interpretable por sistemas automatizados."
                    f"Si el mensaje del usuario no puede ser interpretado para una de las aplicaciones, responde 'N/A' o 'No se puede interpretar'." 
                    f""
                    f"ESPECIFICAMENTE SI Y SOLO SI LA SOLICITUD ES TIPO POST:\n"
                    f"OBLIGATORIO: Responde con 'es una solicitud post' seguido del JSON de abajo\n"
                    f"Detecta las acciones solicitadas por el usuario y genera la consulta para la API correspondiente:\n"
                    f"1. **Crear o Agregar elementos** (acciones como 'crear', 'agregar', 'añadir', 'subir', 'agendar'):\n"
                    f"   - Ejemplo: Crear un contacto, tarea, archivo. (Esto se envía a Notion, Asana, ClickUp)\n"
                    f"2. **Modificar o Editar elementos** (acciones como 'editar', 'modificar', 'actualizar', 'mover'):\n"
                    f"   - Ejemplo: Editar una tarea, archivo. (Esto se envía a Notion, Asana, ClickUp)\n"
                    f"3. **Eliminar elementos** (acciones como 'eliminar', 'borrar', 'suprimir'):\n"
                    f"   - Ejemplo: Eliminar un contacto, tarea, archivo. (Esto se envía a Notion, Asana, ClickUp)\n"
                    f"   - Si se menciona **'eliminar correos'**, debe enviarse a **Gmail** y **Outlook**\n"
                    f"   - Si se menciona **'elimina la cita'** o 'elimina la reunion' debe enviarse a **Gmail**\n"
                    f"4. **Mover elementos** (acciones como 'mover', 'trasladar', 'archivar', 'poner en spam'):\n"
                    f"   - Ejemplo: Mover un archivo o correo a una carpeta, o poner correos en spam. (Esto se envía a **Gmail** y **Outlook**)\n"
                    f"5. **Enviar o compartir** (acciones como 'enviar', 'compartir', 'enviar por correo'):\n"
                    f"   - Ejemplo: Enviar un correo (Esto se envía a Gmail, Outlook, Teams, Slack)\n"
                    f"6. **Agendar o Programar** (acciones como 'agendar', 'programar'):\n"
                    f"   - Ejemplo: Agendar cita en Gmail \n"
                    f"Cuando detectes una solicitud de POST, identifica a qué servicios corresponde basándote en las acciones. Usa 'N/A' para las APIs que no apliquen.\n"
                    f"**Generación de Consulta**: Asegúrate de que las consultas sean claras y sin palabras adicionales como '¿Podrías...?'. Utiliza los datos específicos proporcionados (nombre, fecha, tarea, etc.) para generar las queries."
                    f"**Estructura del JSON para la respuesta (con acciones del usuario):**\n"
                    f"{{\n"
                    f"    \"gmail\": \"<query para Gmail, como 'Eliminar todos los correos de Dominos Pizza' o 'Mover a spam los correos de tal empresa'>\",\n"
                    f"    \"notion\": \"<query para Notion, como 'Marca como completada la tarea tal'>\",\n"
                    f"    \"slack\": \"<query para Slack, adaptada de forma informal si aplica>\",\n"
                    f"    \"hubspot\": \"<query para HubSpot si se menciona contacto o negocio>\",\n"
                    f"    \"outlook\": \"<query para Outlook, igual que Gmail>\",\n"
                    f"    \"clickup\": \"<query para ClickUp, 'N/A' si no aplica>\",\n"
                    f"    \"dropbox\": \"<query para Dropbox, 'N/A' si no aplica>\",\n"
                    f"    \"asana\": \"<query para Asana, 'N/A' si no aplica>\",\n"
                    f"    \"googledrive\": \"<query para Google Drive, 'N/A' si no aplica>\",\n"
                    f"    \"onedrive\": \"<query para OneDrive, 'N/A' si no aplica>\",\n"
                    f"    \"teams\": \"<query para Teams, 'N/A' si no aplica>\"\n"
                    f"}}\n"
                    f"El JSON debe incluir solo información relevante extraída del mensaje del usuario y ser fácilmente interpretable por sistemas automatizados. "
                    f"Usa 'N/A' si una API no aplica a la solicitud.\n"
                    f"Los saludos posibles que deberías detectar incluyen, pero no se limitan a: 'Hola', '¡Hola!', 'Buenos días', 'Buenas', 'Hey', 'Ciao', 'Bonjour', 'Hola a todos', '¡Qué tal!'. "
                    f"Si detectas un saludo, simplemente responde con 'Es un saludo'."
                )
                
                if last_ai_response:
                    prompt += f"\nLa última respuesta de la IA fue: '{last_ai_response}'.\n"

                response = openai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "Eres un asistente que identifica saludos o solicitudes."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=1800
                )
                ia_interpretation = response.choices[0].message.content.strip().lower()
                print(ia_interpretation)

                if 'saludo' in ia_interpretation:
                    prompt_greeting = f"Usuario: {last_message}\nResponde de manera cálida y amigable, como si fuera una conversación normal."

                    response_greeting = openai.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[{
                            "role": "system",
                            "content": "Eres un asistente virtual cálido y amigable. Responde siempre de manera conversacional a los saludos."
                        }, {
                            "role": "user",
                            "content": prompt_greeting
                        }],
                        max_tokens=150
                    )

                    ia_response = response_greeting.choices[0].message.content.strip()

                elif 'get' in ia_interpretation:
                    print("SOLICITUUUD")
                    match = re.search(r'\{[^}]*\}', ia_interpretation, re.DOTALL | re.MULTILINE)
                    print(match)
                    if match:
                        try:
                            queries = json.loads(match.group(0))
                            print(queries)
                            
                            gmail_query = queries.get('gmail', 'n/a')
                            notion_query = queries.get('notion', 'n/a')
                            slack_query = queries.get('slack', 'n/a')
                            hubspot_query = queries.get('hubspot', 'n/a')
                            outlook_query = queries.get('outlook', 'n/a')
                            clickup_query = queries.get('clickup', 'n/a')
                            dropbox_query = queries.get('dropbox', 'n/a')
                            asana_query = queries.get('asana', 'n/a')
                            googledrive_query = queries.get('googledrive', 'n/a')
                            onedrive_query = queries.get('onedrive', 'n/a')
                            teams_query = queries.get('teams', 'n/a')

                            email = request.args.get('email')
                            if not email:
                                return jsonify({"error": "Se deben proporcionar tanto el email como la consulta"}), 400

                            try:
                                user = mongo.database.usuarios.find_one({'correo': email})
                                if not user:
                                    return jsonify({"error": "Usuario no encontrado"}), 404
                            except Exception as e:
                                return jsonify({"error": f"Error al procesar la solicitud: {str(e)}"}), 500

                            search_results_data = {
                                'gmail': [],
                                'slack': [],
                                'notion': [],
                                'outlook': [],
                                'hubspot': [],
                                'clickup': [],
                                'dropbox': [],
                                'asana': [],
                                'onedrive': [],
                                'teams': [], 
                                'googledrive': [],
                            }

                            try:
                                gmail_results = search_gmail(gmail_query)
                                search_results_data['gmail'] = gmail_results.get_json() if hasattr(gmail_results, 'get_json') else gmail_results
                            except Exception:
                                search_results_data['gmail'] = ["No se encontró ningún valor en Gmail"]

                            try:
                                notion_results = search_notion(notion_query)
                                search_results_data['notion'] = notion_results.get_json() if hasattr(notion_results, 'get_json') else notion_results
                            except Exception:
                                search_results_data['notion'] = ["No se encontró ningún valor en Notion"]

                            try:
                                slack_results = search_slack(slack_query)
                                search_results_data['slack'] = slack_results.get_json() if hasattr(slack_results, 'get_json') else slack_results
                            except Exception:
                                search_results_data['slack'] = ["No se encontró ningún valor en Slack"]

                            try:
                                outlook_results = search_outlook(outlook_query)
                                search_results_data['outlook'] = outlook_results.get_json() if hasattr(outlook_results, 'get_json') else outlook_results
                            except Exception:
                                search_results_data['outlook'] = ["No se encontró ningún valor en Outlook"]

                            try:
                                hubspot_results = search_hubspot(hubspot_query)
                                search_results_data['hubspot'] = hubspot_results.get_json() if hasattr(hubspot_results, 'get_json') else hubspot_results
                            except Exception:
                                search_results_data['hubspot'] = ["No se encontró ningún valor en HubSpot"]

                            try:
                                clickup_results = search_clickup(clickup_query)
                                search_results_data['clickup'] = clickup_results.get_json() if hasattr(clickup_results, 'get_json') else clickup_results
                            except Exception:
                                search_results_data['clickup'] = ["No se encontró ningún valor en ClickUp"]

                            try:
                                dropbox_results = search_dropbox(dropbox_query)
                                search_results_data['dropbox'] = dropbox_results.get_json() if hasattr(dropbox_results, 'get_json') else dropbox_results
                            except Exception:
                                search_results_data['dropbox'] = ["No se encontró ningún valor en Dropbox"]

                            try:
                                asana_results = search_asana(asana_query)
                                search_results_data['asana'] = asana_results.get_json() if hasattr(asana_results, 'get_json') else asana_results
                            except Exception:
                                search_results_data['asana'] = ["No se encontró ningún valor en Asana"]

                            try:
                                onedrive_results = search_onedrive(onedrive_query)
                                search_results_data['onedrive'] = onedrive_results.get_json() if hasattr(onedrive_results, 'get_json') else onedrive_results
                            except Exception:
                                search_results_data['onedrive'] = ["No se encontró ningún valor en OneDrive"]

                            try:
                                googledrive = search_google_drive(googledrive_query)
                                search_results_data['googledrive'] = googledrive.get_json() if hasattr(googledrive, 'get_json') else googledrive
                            except Exception:
                                search_results_data['onedrive'] = ["No se encontró ningún valor en OneDrive"]

                            try:
                                teams_results = search_teams(teams_query)
                                search_results_data['teams'] = teams_results.get_json() if hasattr(teams_results, 'get_json') else teams_results
                            except Exception:
                                search_results_data['teams'] = ["No se encontró ningún valor en Teams"]
                            print("DATA", search_results_data["googledrive"])
                            links = extract_links_from_datas(datas=search_results_data)
                            print("LINKS", links)
                            prompt = generate_prompt(last_message, search_results_data)
                            global last_response
                            last_response = prompt
                            response = openai.chat.completions.create(
                                model="gpt-3.5-turbo",
                                messages=[{
                                    "role": "system",
                                    "content": "Eres un asistente útil que automatiza el proceso de búsqueda en diversas aplicaciones según la consulta proporcionada."
                                }, {
                                    "role": "user",
                                    "content": prompt
                                }],
                                max_tokens=4096
                            )
                            responses = response.choices[0].message.content.strip()
                            print("RESPONSES: ",responses)

                            if not responses:
                                return jsonify({"error": "La respuesta de la IA está vacía"}), 500

                            return jsonify({"message": responses, "links": links})
                        except Exception as e:
                            return jsonify({"error": f"Error al procesar la solicitud: {str(e)}"}), 500
                elif 'post' in ia_interpretation:
                    match = re.search(r'\{[^}]*\}', ia_interpretation, re.DOTALL | re.MULTILINE)
                    if match:
                        try:
                            queries = json.loads(match.group(0))
                            gmail_data = queries.get('gmail', {})
                            notion_data = queries.get('notion', {})
                            slack_data = queries.get('slack', {})
                            hubspot_data = queries.get('hubspot', {})
                            outlook_data = queries.get('outlook', {})
                            clickup_data = queries.get('clickup', {})
                            dropbox_data = queries.get('dropbox', {})
                            asana_data = queries.get('asana', {})
                            googledrive_data = queries.get('googledrive', {})
                            onedrive_data = queries.get('onedrive', {})
                            teams_data = queries.get('teams', {})

                            email = request.args.get('email')
                            if not email:
                                return jsonify({"error": "Se deben proporcionar tanto el email como los datos"}), 400

                            try:
                                user = mongo.database.usuarios.find_one({'correo': email})
                                if not user:
                                    return jsonify({"error": "Usuario no encontrado"}), 404

                                post_results_data = {}
                                apis = {
                                    'gmail': post_to_gmail,
                                    'notion': post_to_notion,
                                    # 'slack': post_to_slack,
                                    # 'hubspot': post_to_hubspot,
                                    'outlook': post_to_outlook,
                                    'clickup': post_to_clickup,
                                    # 'dropbox': post_to_dropbox,
                                    'asana': post_to_asana,
                                    # 'googledrive': post_to_googledrive,
                                    # 'onedrive': post_to_onedrive,
                                    # 'teams': post_to_teams,
                                }
                                
                                # Ejecutar las funciones de las APIs correspondientes
                                for service, query in queries.items():
                                    if query.lower() != 'n/a' and service in apis:
                                        try:
                                            response = apis[service](query)
                                            message = response.get('message', None)
                                            # Solo guardamos si hay un mensaje y es distinto a "Sin mensaje"
                                            if message and message != "Sin mensaje":
                                                post_results_data[service] = message
                                        except Exception as e:
                                            # Puedes decidir cómo manejar el error, aquí se ignora si falla
                                            pass

                                # Si se obtuvo algún mensaje, tomamos el primero
                                final_message = None
                                if post_results_data:
                                    # Extraemos el primer mensaje válido
                                    for service, msg in post_results_data.items():
                                        final_message = msg
                                        break

                                # Si no se obtuvo mensaje válido, se puede definir un valor por defecto
                                if not final_message:
                                    final_message = "Sin mensaje"

                                return jsonify({"message": final_message})
                            except Exception as e:
                                return jsonify({"error": f"Error al procesar la solicitud: {str(e)}"}), 500
                        except json.JSONDecodeError:
                            return jsonify({"error": "Formato JSON inválido"}), 400
                elif 'anterior' in ia_interpretation:
                    reference_prompt = f"El usuario dijo: '{last_message}'\n"
                    reference_prompt += f"La última respuesta de la IA fue: '{last_response}'.\n"
                    reference_prompt += "Responde al usuario considerando la respuesta anterior."

                    response_reference = openai.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "system", "content": "Eres un asistente que recuerda la última respuesta."},
                                {"role": "user", "content": reference_prompt}],
                        max_tokens=150
                    )
                    ia_response = response_reference.choices[0].message.content.strip()
                else:
                    ia_response = "Lo siento, no entendí el mensaje. ¿Puedes especificar más sobre lo que necesitas?"

            except Exception as e:
                ia_response = f"Lo siento, ocurrió un error al procesar tu mensaje: {e}"

        return jsonify({"message": ia_response})


    @app.route("/api/chat", methods=["POST"])
    def chat():
        data = request.get_json()
        user_messages = data.get("messages", [])
        
        # Mensaje del sistema para guiar las respuestas
        system_message = """
        Eres Shiffu, un asistente virtual amigable y útil en su versión alfa. 
        Ayudas a los usuarios respondiendo preguntas de manera clara y humana. 
        Si el usuario pregunta "¿Qué es Shiffu?" o menciona "tu propósito" o algo parecido a tu funcionalidad, explica lo siguiente:
        "Soy Shiffu, un asistente en su versión alfa. Estoy diseñado para ayudar a automatizar procesos de búsqueda y conectar aplicaciones como Gmail, Notion, Slack, Outlook y HubSpot. Mi objetivo es simplificar la gestión de tareas y facilitar la integración entre herramientas para que los usuarios puedan iniciar sesión, gestionar datos y colaborar de forma eficiente."
        Responde saludos como "Hola" o "Saludos" con algo cálido como "¡Hola! Soy Shiffu, tu asistente virtual. ¿En qué puedo ayudarte hoy? 😊".
        Para cualquier otra consulta, proporciona una respuesta útil y adaptada al contexto del usuario y lo más importante siempre menciona que ingresen sesion primero con Shiffu y luego con sus aplicaciones para ayudarlos de una mejor manera. Si te preguntan como iniciar sesión en shiffu menciona que arriba se encuentran dos botones y uno sirve para registrarse en Shiffu y el otro para iniciar sesión en
        """
        
        ia_response = "Lo siento, no entendí tu mensaje. ¿Puedes reformularlo?"

        if user_messages:
            try:
                # Llamada a OpenAI para procesar la conversación
                response = openai.chat.completions.create(
                    model="gpt-3.5-turbo",  # Cambiar si tienes acceso a otro modelo
                    messages=[
                        {"role": "system", "content": system_message},
                        *user_messages  # Mensajes enviados por el usuario
                    ],
                    max_tokens=150  # Limita el tamaño de la respuesta
                )
                # Extraemos la respuesta de OpenAI
                ia_response = response.choices[0].message.content.strip()
            except Exception as e:
                ia_response = f"Lo siento, ocurrió un error al procesar tu mensaje: {e}"
        
        # Retornamos la respuesta al frontend
        return jsonify({"message": ia_response})

    @app.route("/clickup-proxy", methods=["POST"])
    def clickup_proxy():
        try:
            data = request.json

            client_id = data.get("client_id")
            client_secret = data.get("client_secret")
            code = data.get("code")
            redirect_uri = data.get("redirect_uri")

            if not all([client_id, client_secret, code, redirect_uri]):
                return jsonify({"error": "Missing required fields"}), 400

            token_url = "https://api.clickup.com/api/v2/oauth/token"
            payload = {
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri
            }

            response = requests.post(token_url, json=payload)
            data = response.json()

            if "access_token" in data:
                return jsonify({
                    "access_token": data["access_token"],
                    "expires_in": data.get("expires_in", "unknown")  # Retorna el tiempo de expiración si está disponible
                })
            else:
                return jsonify({"error": "Failed to retrieve access token", "details": data}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/dropbox-proxy", methods=["POST"])
    def dropbox_proxy():
        try:
            data = request.json

            client_id = data.get("client_id")
            client_secret = data.get("client_secret")
            code = data.get("code")
            redirect_uri = data.get("redirect_uri")

            if not all([client_id, client_secret, code, redirect_uri]):
                return jsonify({"error": "Missing required fields"}), 400

            # URL para obtener el token de acceso
            token_url = "https://api.dropbox.com/oauth2/token"
            payload = {
                "code": code,
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri
            }

            response = requests.post(token_url, data=payload)
            data = response.json()

            return jsonify({
                    "access_token": data
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        
    @app.route("/asana-proxy", methods=["POST"])
    def asana():
        try:
            data = request.json
            client_id = data.get("client_id")
            client_secret = data.get("client_secret")
            code = data.get("code")
            redirect_uri = data.get("redirect_uri")

            if not all([client_id, client_secret, code, redirect_uri]):
                return jsonify({"error": "Missing required fields"}), 400

            token_url = "https://app.asana.com/-/oauth_token"

            payload = {
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri
            }

            headers = {"Content-Type": "application/x-www-form-urlencoded"}

            response = requests.post(token_url, data=payload, headers=headers)
            data = response.json()

            access_token = data.get("access_token")
            expires_in = data.get("expires_in")

            return jsonify({
                "access_token": access_token,
                "expires_in": expires_in
            })

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/search/clickup', methods=["GET"])
    def search_clickup(query):
        email = request.args.get('email')
        try:
            user = mongo.database.usuarios.find_one({'correo': email})
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            clickup_integration = user.get('integrations', {}).get('ClickUp', None)
            if clickup_integration:
                clickup_token = clickup_integration.get('token', None)
            else:
                clickup_token = None
            
            if not clickup_token:
                return jsonify({"error": "Token de ClickUp no disponible"}), 400
            
            if not query:
                return jsonify({"error": "No se proporcionó un término de búsqueda"}), 400

            if not query or query.lower() == "n/a":
                        return jsonify({"message": "No se encontraron resultados en ClickUp"}), 200

            team_url = "https://api.clickup.com/api/v2/team"
            headers = {
                'Authorization': f"Bearer {clickup_token}"
            }
            team_response = requests.get(team_url, headers=headers)

            if team_response.status_code != 200:
                return jsonify({"error": "No se pudo obtener el team_id", "details": team_response.text}), team_response.status_code

            teams = team_response.json().get('teams', [])
            if not teams:
                return jsonify({"error": "El usuario no pertenece a ningún equipo en ClickUp"}), 400

            team_id = teams[0].get('id')  # Usamos el primer equipo disponible

            # ✅ 2. Buscar tareas en ClickUp
            task_url = f"https://api.clickup.com/api/v2/team/{team_id}/task"
            params = {
                "query": query
            }

            response = requests.get(task_url, headers=headers, params=params)

            if response.status_code == 404:
                return jsonify({"error": "No se encontró la ruta en ClickUp. Verifica la URL y el team_id."}), 404

            response.raise_for_status()  # Lanzará error si el código de estado es 4xx o 5xx
            results = response.json().get('tasks', [])

            if not results:
                return jsonify({"message": "No se encontraron resultados en ClickUp"}), 200

            # ✅ 3. Filtrar manualmente las tareas basadas en el query (Filtro más flexible)
            filtered_results = [
                {
                    'task_name': task.get('name', 'Sin título'),
                    'status': task.get('status', {}).get('status', 'Sin estado'),
                    'priority': task.get('priority', 'Sin prioridad'),
                    'assignees': [assignee.get('username', 'Desconocido') for assignee in task.get('assignees', [])] or ['Sin asignar'],
                    'due_date': task.get('due_date', 'Sin fecha'),
                    'project': task.get('project', {}).get('name', 'Sin proyecto'),
                    'list': task.get('list', {}).get('name', 'Sin lista'),
                    'url': f"https://app.clickup.com/t/{task.get('id')}"
                }
                for task in results
            ]

            if not filtered_results:
                return jsonify({"message": "No se encontraron tareas que coincidan con el término de búsqueda."}), 200

            return jsonify(filtered_results)

        except requests.RequestException as e:
            return jsonify({"error": "Error al realizar la solicitud a ClickUp", "details": str(e)}), 500
        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500


    @app.route('/search/dropbox', methods=["GET"])
    def search_dropbox(query):
        email = request.args.get('email')
        try:
            user = mongo.database.usuarios.find_one({'correo': email})
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            dropbox_integration = user.get('integrations', {}).get('Dropbox', None)
            dropbox_token = dropbox_integration.get('token') if dropbox_integration else None

            if not dropbox_token:
                return jsonify({"error": "Token de Dropbox no disponible"}), 400

            if not query or query.lower() == "n/a":
                return jsonify({"message": "No se encontraron resultados en Dropbox"}), 200

            # 🔍 **Extraer filtros de la query**
            search_term = None
            search_type = None  # Puede ser "file" o "folder"

            parts = query.split()
            for part in parts:
                if part.startswith("carpeta:"):
                    search_term = part.replace("carpeta:", "").strip()
                    search_type = "folder"
                elif part.startswith("archivo:"):
                    search_term = part.replace("archivo:", "").strip()
                    search_type = "file"
                elif part.startswith("tipo:"):
                    tipo = part.replace("tipo:", "").strip().lower()
                    if tipo in ["file", "folder"]:
                        search_type = tipo

            if not search_term:
                return jsonify({"error": "El término de búsqueda es inválido"}), 400

            # 🔎 **Buscar en Dropbox**
            url = "https://api.dropboxapi.com/2/files/search_v2"
            headers = {
                'Authorization': f"Bearer {dropbox_token}",
                'Content-Type': 'application/json'
            }
            params = {
                "query": search_term,
                "options": {
                    "max_results": 10,
                    "file_status": "active"
                }
            }

            response = requests.post(url, headers=headers, json=params)
            response.raise_for_status()

            results = response.json().get('matches', [])
            if not results:
                return jsonify({"message": "No se encontraron resultados en Dropbox"}), 200

            # 🎯 **Procesar resultados**
            filtered_results = []

            for result in results:
                raw_metadata = result.get('metadata', {})
                metadata = raw_metadata.get('metadata', {})  # Extraer el diccionario interno correcto

                name = metadata.get('name', 'Sin nombre')
                path = metadata.get('path_display', 'Sin ruta')
                tag = metadata.get('.tag', '')  # Puede ser "file" o "folder"

                if search_type == "folder" and tag == "folder":
                    # 📂 Si es una carpeta, listar su contenido
                    list_folder_url = "https://api.dropboxapi.com/2/files/list_folder"
                    list_folder_headers = {
                        'Authorization': f"Bearer {dropbox_token}",
                        'Content-Type': 'application/json'
                    }
                    list_folder_params = {
                        "path": path
                    }

                    try:
                        list_response = requests.post(list_folder_url, headers=list_folder_headers, json=list_folder_params)
                        list_response.raise_for_status()
                        folder_contents = list_response.json().get('entries', [])

                        # Agregar solo archivos dentro de la carpeta
                        for item in folder_contents:
                            if item['.tag'] == 'file':  # Solo archivos
                                file_link = generate_dropbox_link(dropbox_token, item['path_display'])
                                filtered_results.append({
                                    'name': item['name'],
                                    'path': item['path_display'],
                                    'type': 'file',
                                    'download_link': file_link
                                })
                    except requests.RequestException as e:
                        return jsonify({"error": "Error al listar los archivos dentro de la carpeta", "details": str(e)}), 500
                else:
                    # Agregar archivos/carpetas que coincidan con la búsqueda
                    if not search_type or tag == search_type:
                        file_link = generate_dropbox_link(dropbox_token, path) if tag == "file" else None
                        filtered_results.append({
                            'name': name,
                            'path': path,
                            'type': tag,
                            'download_link': file_link
                        })

            if not filtered_results:
                return jsonify({"message": "No se encontraron archivos o carpetas que coincidan con el término de búsqueda."}), 200

            return jsonify(filtered_results)

        except requests.RequestException as e:
            return jsonify({"error": "Error al realizar la solicitud a Dropbox", "details": str(e)}), 500
        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500
    
    def generate_dropbox_link(token, file_path):
        """Genera un link de descarga temporal para un archivo en Dropbox"""
        url = "https://api.dropboxapi.com/2/files/get_temporary_link"
        headers = {
            'Authorization': f"Bearer {token}",
            'Content-Type': 'application/json'
        }
        params = {"path": file_path}

        try:
            response = requests.post(url, headers=headers, json=params)
            response.raise_for_status()
            return response.json().get("link")
        except requests.RequestException as e:
            print(f"Error al generar link para {file_path}: {e}")
            return None

    @app.route('/search/asana', methods=["GET"])
    def search_asana(query):
        email = request.args.get('email')
        try:
            user = mongo.database.usuarios.find_one({'correo': email})
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            asana_integration = user.get('integrations', {}).get('Asana', None)
            asana_token = asana_integration.get('token') if asana_integration else None

            if not asana_token:
                return jsonify({"error": "Token de Asana no disponible"}), 400

            # ✅ 1. Obtener el Workspace ID
            workspace_url = "https://app.asana.com/api/1.0/workspaces"
            headers = {'Authorization': f"Bearer {asana_token}"}
            workspace_response = requests.get(workspace_url, headers=headers)

            if workspace_response.status_code != 200:
                return jsonify({"error": "No se pudieron obtener los espacios de trabajo", "details": workspace_response.text}), workspace_response.status_code

            workspaces = workspace_response.json().get('data', [])
            if not workspaces:
                return jsonify({"error": "El usuario no tiene espacios de trabajo en Asana"}), 400

            workspace_id = workspaces[0].get('gid')  # Tomamos el primer workspace disponible

            # ✅ 2. Configurar la consulta según el tipo de búsqueda
            params = {
                "opt_fields": "name,gid,completed,assignee.name,due_on,projects.name"
            }

            from datetime import datetime, timedelta

            today = datetime.today().strftime('%Y-%m-%d')
            tomorrow = (datetime.today() + timedelta(days=1)).strftime('%Y-%m-%d')

            if "hoy" in query:  # Buscar tareas con fecha de hoy
                params["due_on"] = today
            elif "mañana" in query:  # Buscar tareas con fecha de mañana
                params["due_on"] = tomorrow
            elif "pendientes" in query:  # Buscar solo tareas no completadas
                params["completed"] = False
            else:  # Búsqueda por texto (nombre o descripción)
                params["text"] = query  

            # ✅ 3. Realizar la búsqueda
            search_url = f"https://app.asana.com/api/1.0/workspaces/{workspace_id}/tasks/search"
            response = requests.get(search_url, headers=headers, params=params)

            if response.status_code == 404:
                return jsonify({"error": "No se encontró la ruta en Asana. Verifica la URL y el workspace_id."}), 404

            response.raise_for_status()
            results = response.json().get('data', [])

            if not results:
                return jsonify({"message": "No se encontraron resultados en Asana"}), 200

            search_results = []
            for task in results:
                task_name = task.get('name', 'Sin título')
                status = 'Completada' if task.get('completed') else 'Pendiente'
                assignee = task.get('assignee', {}).get('name', 'Sin asignar')
                due_date = task.get('due_on', 'Sin fecha')
                projects = ', '.join([p.get('name', 'Sin nombre') for p in task.get('projects', [])]) if task.get('projects') else "Sin proyectos asignados"
                task_url = f"https://app.asana.com/0/{workspace_id}/{task.get('gid')}"

                search_results.append({
                    'task_name': task_name,
                    'status': status,
                    'assignee': assignee,
                    'due_date': due_date,
                    'projects': projects,
                    'url': task_url
                })

            return jsonify(search_results)

        except requests.RequestException as e:
            return jsonify({"error": "Error al realizar la solicitud a Asana", "details": str(e)}), 500
        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500

    @app.route('/search/onedrive', methods=["GET"])
    def search_onedrive(query):        
        email = request.args.get('email')

        if not email or not query:
            return jsonify({"error": "Faltan parámetros (email y query)"}), 400

        try:
            user = mongo.database.usuarios.find_one({'correo': email})
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            onedrive_integration = user.get('integrations', {}).get('OneDrive', None)
            onedrive_token = onedrive_integration.get('token') if onedrive_integration else None

            if not onedrive_token:
                return jsonify({"error": "Token de OneDrive no disponible"}), 400

            # 🛠️ Limpiar la query para obtener solo el nombre de la carpeta
            query_clean = query.split(":")[-1].strip()

            # 🔍 **Buscar la carpeta directamente por nombre**
            folder_url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{query_clean}"
            headers = {
                'Authorization': f"Bearer {onedrive_token}",
                'Accept': 'application/json'
            }


            folder_response = requests.get(folder_url, headers=headers)
            if folder_response.status_code == 404:
                return jsonify({"error": f"No se encontró la carpeta '{query_clean}' en OneDrive."}), 404

            folder_data = folder_response.json()
            folder_id = folder_data.get("id")

            if not folder_id:
                return jsonify({"error": "No se pudo obtener el ID de la carpeta"}), 500

            # 🔎 **Buscar archivos dentro de la carpeta**
            files_url = f"https://graph.microsoft.com/v1.0/me/drive/items/{folder_id}/children"
            files_response = requests.get(files_url, headers=headers)

            if files_response.status_code != 200:
                return jsonify({"error": "Error al obtener archivos de la carpeta"}), files_response.status_code

            files = files_response.json().get('value', [])

            if not files:
                return jsonify({"message": f"No se encontraron archivos en la carpeta '{query_clean}'."}), 200

            # 🎯 **Procesar resultados**
            search_results = []
            for file in files:
                search_results.append({
                    'name': file.get('name', 'Sin nombre'),
                    'type': file.get('file', {}).get('mimeType', 'Desconocido'),
                    'url': file.get('@microsoft.graph.downloadUrl', None)
                })

            return jsonify(search_results)

        except requests.RequestException as e:
            return jsonify({"error": "Error al realizar la solicitud a OneDrive", "details": str(e)}), 500
        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500

    @app.route('/search/teams', methods=["GET"])
    def search_teams(query):
        email = request.args.get('email')
        try:
            # Obtener el usuario desde la base de datos
            user = mongo.database.usuarios.find_one({'correo': email})
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            teams_integration = user.get('integrations', {}).get('Teams', None)
            teams_token = teams_integration.get('token', None) if teams_integration else None

            if not teams_token:
                return jsonify({"error": "Token de Teams no disponible"}), 400

            if not query:
                return jsonify({"error": "No se proporcionó un término de búsqueda"}), 400

            # Determinar tipo de búsqueda
            headers = {'Authorization': f"Bearer {teams_token}"}
            
            if query.startswith("conversation with:"):
                # Buscar un chat con el usuario especificado
                name, keywords = extract_conversation_query(query)
                chat_id = get_chat_id(name, headers)
                if not chat_id:
                    return jsonify({"error": f"No se encontró una conversación con {name}"}), 404
                
                url = f"https://graph.microsoft.com/v1.0/me/chats/{chat_id}/messages"
                params = {"search": keywords}

            elif query.startswith("channel:"):
                # Buscar mensajes en un canal específico
                channel_name, keywords = extract_channel_query(query)
                team_id, channel_id = get_channel_id(channel_name, headers)
                if not channel_id:
                    return jsonify({"error": f"No se encontró el canal {channel_name}"}), 404
                
                url = f"https://graph.microsoft.com/v1.0/teams/{team_id}/channels/{channel_id}/messages"
                params = {"search": keywords}

            elif query.startswith("message:"):
                # Buscar en todos los mensajes del usuario
                keywords = extract_message_query(query)
                url = "https://graph.microsoft.com/v1.0/me/messages"
                params = {"search": keywords}

            else:
                return jsonify({"error": "Formato de query no válido"}), 400

            # Hacer la solicitud a la API de Teams
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()

            results = response.json().get('value', [])
            if not results:
                return jsonify({"message": "No se encontraron resultados en Teams"}), 200

            # Formatear resultados
            search_results = []
            for result in results:
                search_results.append({
                    'message_subject': result.get('subject', 'Sin asunto'),
                    'from': result.get('from', {}).get('user', {}).get('displayName', 'Sin remitente'),
                    'content': result.get('body', {}).get('content', 'Sin contenido'),
                    'url': f"https://teams.microsoft.com/l/message/{result.get('id')}"
                })

            return jsonify(search_results)

        except requests.RequestException as e:
            return jsonify({"error": "Error al realizar la solicitud a Teams", "details": str(e)}), 500
        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500

    # Funciones auxiliares
    def extract_conversation_query(query):
        """ Extrae el nombre y palabras clave de 'conversation with:<nombre> <keywords>' """
        parts = query.replace("conversation with:", "").strip().split(" ", 1)
        name = parts[0]
        keywords = parts[1] if len(parts) > 1 else ""
        return name, keywords

    def extract_channel_query(query):
        """ Extrae el nombre del canal y palabras clave de 'channel:<nombre> <keywords>' """
        parts = query.replace("channel:", "").strip().split(" ", 1)
        channel_name = parts[0]
        keywords = parts[1] if len(parts) > 1 else ""
        return channel_name, keywords

    def extract_message_query(query):
        """ Extrae las palabras clave de 'message:<keywords>' """
        return query.replace("message:", "").strip()

    def get_chat_id(name, headers):
        """ Busca el chat ID de un usuario por su nombre en Teams. """
        url_chats = "https://graph.microsoft.com/v1.0/me/chats"
        response_chats = requests.get(url_chats, headers=headers)
        response_chats.raise_for_status()

        chats = response_chats.json().get('value', [])
        
        for chat in chats:
            members = chat.get('members', [])
            for member in members:
                if name.lower() in member.get('displayName', '').lower():
                    return chat.get('id')

        return None  # Si no se encontró el chat

    def get_channel_id(channel_name, headers):
        """ Busca el team ID y channel ID de un canal por su nombre en Teams """
        teams_url = "https://graph.microsoft.com/v1.0/me/joinedTeams"
        teams_response = requests.get(teams_url, headers=headers)
        teams_response.raise_for_status()

        teams = teams_response.json().get('value', [])
        for team in teams:
            team_id = team.get('id')
            channels_url = f"https://graph.microsoft.com/v1.0/teams/{team_id}/channels"
            channels_response = requests.get(channels_url, headers=headers)
            channels_response.raise_for_status()

            channels = channels_response.json().get('value', [])
            for channel in channels:
                if channel.get('displayName', '').lower() == channel_name.lower():
                    return team_id, channel.get('id')
            return None, None
        
    @app.route('/search/google_drive', methods=["GET"])
    def search_google_drive(query):
        email = request.args.get('email')

        if not query:
            return jsonify({"error": "No se proporcionó una consulta válida."}), 400

        try:
            # 📌 Recuperar token de Google Drive
            user = mongo.database.usuarios.find_one({'correo': email})
            if not user:
                return jsonify({"error": "Usuario no encontrado."}), 404

            google_drive_token = user.get('integrations', {}).get('Drive', {}).get('token')
            if not google_drive_token:
                return jsonify({"error": "Token de Google Drive no disponible."}), 400

            headers = {
                "Authorization": f"Bearer {google_drive_token}",
                "Accept": "application/json"
            }
            
            # Reformatear la consulta para eliminar "carpeta:" si está presente
            if query.startswith("carpeta:"):
                query = query[len("carpeta:"):]

            # Ahora query solo contendrá "prueba" y será válida para la búsqueda en Google Drive
            folder_query = f"name = '{query}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"

            folder_params = {
                "q": folder_query,
                "fields": "files(id, name)"
            }
            folder_response = requests.get("https://www.googleapis.com/drive/v3/files", headers=headers, params=folder_params)
            folder_data = folder_response.json()
            if "files" not in folder_data or not folder_data["files"]:
                return []  # No se encontraron carpetas
            
            folder_id = folder_data["files"][0]["id"]
            
            # Buscar archivos dentro de la carpeta
            files_query = f"'{folder_id}' in parents and trashed = false"
            files_params = {
                "q": files_query,
                "fields": "files(id, name, mimeType, webViewLink)"
            }
            files_response = requests.get("https://www.googleapis.com/drive/v3/files", headers=headers, params=files_params)
            files_data = files_response.json()

            search_results = []
            for file in files_data.get("files", []):
                search_results.append({
                    "title": file["name"],
                    "type": file["mimeType"],
                    "url": file["webViewLink"]
                })
            return jsonify(search_results)

        except requests.RequestException as e:
            return jsonify({"error": "Error en la solicitud a Google Drive", "details": str(e)}), 500
        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500

# SECRETARIA
    def get_gmail_headers(token):
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    def get_outlook_headers(token):
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    def get_slack_headers(token):
        return {"Authorization": f"Bearer {token}"}

    def get_hubspot_headers(api_key):
        return {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json"
        }

    def get_notion_headers(token):
        return {
            "Authorization": f"Bearer {token}",
            'Notion-Version': '2022-06-28',
            'Content-Type': 'application/json'
        }

    def get_clickup_headers(token):
        return {
            "Authorization": token,
            "Content-Type": "application/json"
        }

    def get_dropbox_headers(token):
        return {"Authorization": f"Bearer {token}"}

    def get_google_drive_headers(token):
        return {"Authorization": f"Bearer {token}"}

    def get_onedrive_headers(token):
        return {"Authorization": f"Bearer {token}"}

    def get_teams_headers(token):
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    def get_asana_headers(token):
        return {
            "Authorization": f"Bearer {token}",
        }


    def interpretar_accion_email(texto):
        prompt = f"El usuario dijo: '{texto}'. Determina si quiere 'delete' (eliminar), 'reply' (responder) o 'spam' (mover a spam). Si no está claro, responde 'unknown'."
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": "Eres un asistente que analiza intenciones en correos electrónicos."},
                    {"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip().lower()

    def interpretar_accion_productividad(texto):
        prompt = f"El usuario dijo: '{texto}'. Determina si quiere 'mark_done' (marcar como completado), 'assign' (asignar a alguien más) o 'comment' (comentar en la tarea) o 'delete' (eliminar la tarea). Si no está claro, responde 'unknown'."
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": "Eres un asistente que analiza intenciones en plataformas de productividad."},
                    {"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip().lower()
    
    def interpretar_accion_hubspot(texto):
        prompt = f"El usuario dijo: '{texto}'. Determina si quiere 'follow_up' (hacer seguimiento a un cliente), 'close_deal' (cerrar un trato) o 'update_info' (actualizar la información de un cliente). Si no está claro, responde 'unknown'."
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": "Eres un asistente que analiza intenciones en un CRM de ventas."},
                    {"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip().lower()

    def interpretar_accion_archivos(texto):
        prompt = f"El usuario dijo: '{texto}'. Determina si quiere 'download' (descargar archivo), 'share' (compartir con alguien más) o 'delete' (eliminar archivo). Si no está claro, responde 'unknown'."
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": "Eres un asistente que analiza intenciones en plataformas de almacenamiento en la nube."},
                    {"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip().lower()

    def interpretar_accion_mensajeria(texto):
        prompt = f"El usuario dijo: '{texto}'. Determina si quiere 'reply' (responder un mensaje), 'react' (reaccionar con emoji) o 'mention' (mencionar a alguien). Si no está claro, responde 'unknown'."
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": "Eres un asistente que analiza intenciones en plataformas de mensajería."},
                    {"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip().lower()

    @app.route("/ultima-notificacion/gmail", methods=["GET"])
    def obtener_ultimo_correo_gmail():
        email = request.args.get("email")
        try:
            user = mongo.database.usuarios.find_one({'correo': email})
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            token = user.get("integrations", {}).get("Gmail", {}).get("token")
            if not token:
                return jsonify({"error": "Token no disponible"}), 400

            headers = get_gmail_headers(token)
            response = requests.get("https://www.googleapis.com/gmail/v1/users/me/messages?maxResults=1", headers=headers)

            if response.status_code != 200:
                return jsonify({"error": "Error al obtener correos"}), response.status_code

            messages = response.json().get("messages", [])
            if not messages:
                return jsonify({"error": "No hay correos"})

            message_id = messages[0]["id"]
            response = requests.get(f"https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}?format=full", headers=headers)
            message = response.json()
            headers_list = message.get("payload", {}).get("headers", [])

            subject = next((h["value"] for h in headers_list if h["name"] == "Subject"), "(Sin asunto)")
            sender = next((h["value"] for h in headers_list if h["name"] == "From"), "(Desconocido)")

            return jsonify({
                "id": message_id,
                "from": sender,
                "subject": subject,
                "snippet": message.get("snippet", "(Sin contenido)")
            })
        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500

    @app.route("/ultima-notificacion/outlook", methods=["GET"])
    def obtener_ultimo_correo_outlook():
        email = request.args.get("email")
        try:
            user = mongo.database.usuarios.find_one({'correo': email})
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            token = user.get("integrations", {}).get("Outlook", {}).get("token")
            if not token:
                return jsonify({"error": "Token no disponible"}), 400

            headers = get_outlook_headers(token)
            response = requests.get(
                "https://graph.microsoft.com/v1.0/me/messages?$top=1&$filter=parentFolderId ne 'JunkEmail'",
                headers=headers
            )

            if response.status_code != 200:
                return jsonify({"error": "Error al obtener correos"}), response.status_code

            messages = response.json().get("value", [])
            if not messages:
                return jsonify({"error": "No hay correos"}), 404

            message = messages[0]
            return jsonify({
                "id": message["id"],
                "from": message["from"]["emailAddress"]["address"],
                "subject": message["subject"],
                "snippet": message["bodyPreview"]
            })
        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500

    @app.route("/ultima-notificacion/notion", methods=["GET"])
    def obtener_ultima_notificacion_notion():

        email = request.args.get("email")

        try:
            user = mongo.database.usuarios.find_one({'correo': email})
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            notion_integration = user.get('integrations', {}).get('Notion', None)
            notion_token = notion_integration.get('token') if notion_integration else None

            if not notion_token:
                return jsonify({"error": "Token de Notion no disponible"}), 400

            headers = {
                "Authorization": f"Bearer {notion_token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json"
            }

            # 🔍 Buscar elementos ordenados por última edición
            payload = {
                "sort": {
                    "direction": "descending",
                    "timestamp": "last_edited_time"
                },
                "page_size": 5  # Buscamos más de 1 para poder filtrar
            }

            response = requests.post("https://api.notion.com/v1/search", headers=headers, json=payload)
            notion_data = response.json()

            if response.status_code != 200:
                return jsonify({"error": "Error al obtener notificaciones de Notion"}), response.status_code

            results = notion_data.get("results", [])
            if not results:
                return jsonify({"error": "No hay notificaciones"}), 404

            # ❌ Filtrar elementos archivados
            filtered_results = [
                item for item in results
                if not item.get("archived", False) and item.get("object") == "page"
            ]
            if not filtered_results:
                return jsonify({"error": "No hay notificaciones activas"}), 404

            # 📌 Tomar el más reciente después del filtro
            last_update = filtered_results[0]

            # 📝 Extraer título
            title_prop = last_update.get("properties", {}).get("title", {}).get("title", [])
            title = title_prop[0].get("text", {}).get("content", "(Sin título)") if title_prop else "(Sin título)"

            return jsonify({
                "from": "Notion",
                "subject": title,
                "snippet": f"Última edición: {last_update['last_edited_time']}",
                "id": last_update["id"]
            })

        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500
        
    @app.route("/ultima-notificacion/slack", methods=["GET"])
    def obtener_ultimo_mensaje_slack():
        email = request.args.get("email")
        try:
            user = mongo.database.usuarios.find_one({'correo': email})
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            token = user.get("integrations", {}).get("Slack", {}).get("token")
            if not token:
                return jsonify({"error": "Token no disponible"}), 400

            headers = get_slack_headers(token)

            # 1️⃣ Obtener la lista de DMs del usuario
            response = requests.get("https://slack.com/api/conversations.list?types=im", headers=headers)
            response_json = response.json()

            if not response_json.get("ok"):
                return jsonify({"error": "Error al obtener conversaciones", "details": response_json}), 400

            dms = response_json.get("channels", [])
            if not dms:
                return jsonify({"error": "No hay conversaciones directas"}), 404

            # 2️⃣ Ordenar DMs por el último mensaje recibido (latest)
            dms.sort(key=lambda x: x.get("latest", {}).get("ts", "0"), reverse=True)

            # 3️⃣ Tomar el canal más reciente y obtener mensajes
            for dm in dms:
                channel_id = dm["id"]

                history_response = requests.get(f"https://slack.com/api/conversations.history?channel={channel_id}&limit=1", headers=headers)
                history_json = history_response.json()

                if history_json.get("ok") and history_json.get("messages"):
                    message = history_json["messages"][0]  # Último mensaje en ese canal
                    return jsonify({
                        "id": message["ts"],
                        "name": "Slack",
                        "lastMessage": message["text"],
                        "from": f"Usuario {message['user']}",
                        "subject": "Mensaje de Slack",
                        "snippet": message["text"]
                    })

            return jsonify({"error": "No se encontraron mensajes"}), 404

        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500

    @app.route("/ultima-notificacion/onedrive", methods=["GET"])
    def obtener_ultimo_archivo_onedrive():
        email = request.args.get("email")
        try:
            user = mongo.database.usuarios.find_one({'correo': email})
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            token = user.get("integrations", {}).get("OneDrive", {}).get("token")
            if not token:
                return jsonify({"error": "Token no disponible"}), 400

            headers = get_onedrive_headers(token)
            response = requests.get("https://graph.microsoft.com/v1.0/me/drive/recent", headers=headers)

            if response.status_code != 200:
                return jsonify({"error": "Error al obtener archivos"})

            files = response.json().get("value", [])
            if not files:
                return jsonify({"error": "No hay archivos recientes"})

            file = files[0]
            return jsonify({
                "id": file["id"],
                "name": file["name"],
                "createdDateTime": file["createdDateTime"]
            })
        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500

    @app.route("/ultima-notificacion/asana", methods=["GET"])
    def obtener_ultima_notificacion_asana():
        email = request.args.get("email")
        try:
            user = mongo.database.usuarios.find_one({'correo': email})
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            token = user.get("integrations", {}).get("Asana", {}).get("token")
            if not token:
                return jsonify({"error": "Token no disponible"}), 400

            headers = {"Authorization": f"Bearer {token.strip()}"}

            # 🔹 Obtener workspace_id
            workspaces_response = requests.get("https://app.asana.com/api/1.0/workspaces", headers=headers)
            workspaces_data = workspaces_response.json()

            if workspaces_response.status_code != 200:
                return jsonify({"error": "No se pudo obtener el workspace"}), workspaces_response.status_code

            workspaces = workspaces_data.get("data", [])
            if not workspaces:
                return jsonify({"error": "No hay workspaces disponibles"}), 404

            workspace_id = workspaces[0]["gid"]  # 🏢 Tomamos el primero

            # 🔹 Obtener user_id del usuario autenticado
            user_response = requests.get("https://app.asana.com/api/1.0/users/me", headers=headers)
            user_data = user_response.json()

            if user_response.status_code != 200:
                return jsonify({"error": "No se pudo obtener el usuario"}), user_response.status_code

            user_id = user_data.get("data", {}).get("gid")
            if not user_id:
                return jsonify({"error": "No se encontró el ID del usuario"}), 404

            # 🔍 Obtener tareas asignadas al usuario en el workspace
            response = requests.get(
                f"https://app.asana.com/api/1.0/tasks?assignee={user_id}&workspace={workspace_id}&limit=1",
                headers=headers
            )
            response_data = response.json()

            if response.status_code != 200:
                return jsonify({"error": "Error al obtener tareas", "details": response_data}), response.status_code

            tasks = response_data.get("data", [])
            if not tasks:
                return jsonify({"error": "No hay tareas asignadas"}), 404

            task = tasks[0]
            return jsonify({
                "from": "Asana",
                "subject": task.get("name", "(Sin título)"),
                "snippet": f"Tarea asignada: {task.get('name', '(Sin título)')}",
                "id": task["gid"],
            })

        except Exception as e:
            print("❌ Error inesperado:", str(e))
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500


    @app.route("/ultima-notificacion/dropbox", methods=["GET"])
    def obtener_ultimo_archivo_dropbox():
        email = request.args.get("email")
        try:
            user = mongo.database.usuarios.find_one({'correo': email})
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            token = user.get("integrations", {}).get("Dropbox", {}).get("token")
            if not token:
                return jsonify({"error": "Token no disponible"}), 400

            headers = get_dropbox_headers(token)
            response = requests.post("https://api.dropboxapi.com/2/files/list_folder", headers=headers, json={"path": ""})

            if response.status_code != 200:
                return jsonify({"error": "Error al obtener archivos"}), response.status_code

            entries = response.json().get("entries", [])
            if not entries:
                return jsonify({"error": "No hay archivos nuevos"})

            file = entries[0]
            return jsonify({
                "from": "Dropbox",  # Nombre fijo para Dropbox
                "subject": file["name"],  # Usamos el nombre del archivo como el asunto
                "snippet": f"Archivo: {file['name']}",
                "id": file["id"],
                "server_modified": file.get("server_modified", "(Sin fecha de modificación)")  # Fecha de modificación
            })

        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500

    def parse_hubspot_date(date_str):
        """Convierte una fecha ISO8601 de HubSpot a timestamp en milisegundos"""
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ")
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
            return int(dt.timestamp() * 1000)  # Convertir a milisegundos
        except Exception as e:
            print(f"Error al convertir fecha: {date_str} -> {str(e)}")
            return 0  # Retorna 0 si hay error

    @app.route('/ultima-notificacion/hubspot', methods=['GET'])
    def get_last_notification_hubspot():

        email = request.args.get("email")
        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        hubspot_integration = user.get('integrations', {}).get('HubSpot', None)
        if not hubspot_integration:
            return jsonify({"error": "Integración con HubSpot no configurada"}), 400

        hubspot_token = hubspot_integration.get('token', None)
        if not hubspot_token:
            return jsonify({"error": "Token de HubSpot no disponible"}), 400

        headers = get_hubspot_headers(hubspot_token)

        # URLs de búsqueda para contactos, negocios y empresas
        endpoints = {
            "contacto": "https://api.hubapi.com/crm/v3/objects/contacts/search",
            "negocio": "https://api.hubapi.com/crm/v3/objects/deals/search",
            "empresa": "https://api.hubapi.com/crm/v3/objects/companies/search"
        }

        search_data = {
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": "hs_lastmodifieddate",
                            "operator": "GT",
                            "value": "0"
                        }
                    ]
                }
            ],
            "properties": ["hs_lastmodifieddate","dealname", "firstname", "lastname", "email", "hubspot_owner_id", "name"],
            "limit": 1,
            "sorts": ["-hs_lastmodifieddate"]
        }

        latest_update = None

        for entity, url in endpoints.items():
            try:
                response = requests.post(url, headers=headers, json=search_data)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("results"):
                        result = data["results"][0]
                        last_modified_str = result["properties"].get("hs_lastmodifieddate", "0")

                        # Convertir la fecha a timestamp en milisegundos
                        last_modified = parse_hubspot_date(last_modified_str) if isinstance(last_modified_str, str) else int(last_modified_str)

                        if latest_update is None or last_modified > latest_update["timestamp"]:
                            latest_update = {
                                "type": entity,
                                "data": result,
                                "timestamp": last_modified
                            }
                else:
                    print(f"Error al obtener {entity}: {response.status_code} - {response.text}")
            except Exception as e:
                print(f"Error en la consulta de {entity}: {str(e)}")

        if not latest_update:
            return jsonify({"message": "No se encontraron cambios recientes."}), 404

        # Formatear respuesta
        update_data = latest_update["data"]
        entity_type = latest_update["type"]
        properties = update_data["properties"]

        if entity_type == "contacto":
            subject = f"{properties.get('firstname', '')} {properties.get('lastname', '')}".strip()
            snippet = f"Nuevo contacto: {properties.get('email', '(sin email)')}"
        elif entity_type == "negocio":
            subject = properties.get("dealname", "(Sin nombre)")
            snippet = f"Nuevo negocio detectado."
        elif entity_type == "empresa":
            subject = properties.get("name", "(Sin nombre)")
            snippet = f"Nuevo cambio en la empresa."

        notification_data = {
            "from": "HubSpot",
            "type": entity_type,
            "subject": subject if subject else "(Sin título)",
            "snippet": snippet,
            "id": update_data.get("id", "N/A"),
            "last_modified": datetime.fromtimestamp(latest_update["timestamp"] / 1000).isoformat()
        }

        return jsonify(notification_data)

    def convertir_fecha(timestamp):
        if timestamp:
            return datetime.utcfromtimestamp(int(timestamp) / 1000).strftime('%Y-%m-%d %H:%M:%S')
        return "No definida"

    @app.route("/ultima-notificacion/clickup", methods=["GET"])
    def obtener_ultima_notificacion_clickup():
        email = request.args.get("email")
        try:
            user = mongo.database.usuarios.find_one({'correo': email})
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            token = user.get("integrations", {}).get("ClickUp", {}).get("token")
            if not token:
                return jsonify({"error": "Token no disponible"}), 400

            headers = get_clickup_headers(token)
            response = requests.get("https://api.clickup.com/api/v2/team", headers=headers)

            if response.status_code != 200:
                return jsonify({"error": "Error al obtener notificaciones"}), response.status_code

            teams = response.json().get("teams", [])
            if not teams:
                return jsonify({"error": "No hay equipos en ClickUp"})

            team_id = teams[0]["id"]
            response = requests.get(f"https://api.clickup.com/api/v2/team/{team_id}/task", headers=headers)

            tasks = response.json().get("tasks", [])
            if not tasks:
                return jsonify({"error": "No hay tareas nuevas"})

            task = tasks[0]
            due_date = convertir_fecha(task.get("due_date"))

            return jsonify({
                "id": task["id"],
                "name": task["name"],
                "status": task["status"]["status"],
                "due_date": due_date,
                "from": "ClickUp",  # ✅ Para que no falle en el frontend
                "subject": task["name"],  # ✅ Adaptación para React
                "snippet": f"Estado: {task['status']['status']}, Fecha límite: {due_date}"
            })
        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500

    @app.route("/ultima-notificacion/drive", methods=["GET"])
    def obtener_ultimo_archivo_drive():
        email = request.args.get("email")
        try:
            user = mongo.database.usuarios.find_one({'correo': email})
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            token = user.get("integrations", {}).get("Drive", {}).get("token")
            if not token:
                return jsonify({"error": "Token no disponible"}), 400

            headers = get_google_drive_headers(token)
            response = requests.get("https://www.googleapis.com/drive/v3/files?pageSize=1&orderBy=createdTime desc", headers=headers)

            if response.status_code != 200:
                return jsonify({"error": "Error al obtener archivos"}), response.status_code

            files = response.json().get("files", [])
            if not files:
                return jsonify({"error": "No hay archivos nuevos"})

            file = files[0]
            return jsonify({
                "id": file["id"],
                "name": file["name"],
                "createdTime": file["createdTime"]
            })
        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500

    @app.route("/ultima-notificacion/teams", methods=["GET"])
    def obtener_ultimo_mensaje_teams():
        email = request.args.get("email")
        try:
            user = mongo.database.usuarios.find_one({'correo': email})
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            token = user.get("integrations", {}).get("Teams", {}).get("token")
            if not token:
                return jsonify({"error": "Token no disponible"}), 400

            headers = get_teams_headers(token)
            response = requests.get("https://graph.microsoft.com/v1.0/me/chats?$top=1", headers=headers)

            if response.status_code != 200:
                return jsonify({"error": "Error al obtener mensajes"}), response.status_code

            chats = response.json().get("value", [])
            if not chats:
                return jsonify({"error": "No hay mensajes recientes"})

            chat = chats[0]
            return jsonify({
                "id": chat["id"],
                "last_message_preview": chat["lastMessagePreview"]["body"]["content"]
            })
        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500


    @app.route("/accion-gmail", methods=["POST"])
    def ejecutar_accion_gmail():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        message_id = data.get("message_id")

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("Gmail", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        action = interpretar_accion_email(user_text)
        headers = get_gmail_headers(token)

        if "delete" in action:
            response = requests.post(f"https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}/trash", headers=headers)
            return jsonify({"success": "Correo eliminado"}) if response.status_code == 204 else jsonify({"success": "Correo eliminado"})

        elif "reply" in action:
            reply_text = data.get("reply_text", "")
            response = requests.post("https://www.googleapis.com/gmail/v1/users/me/messages/send", headers=headers, json={"raw": reply_text})
            return jsonify({"success": "Respuesta enviada"}) if response.status_code == 200 else jsonify({"error": "Error al responder correo"}), response.status_code

        elif "spam" in action:
            response = requests.post(f"https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}/modify",
                                    headers=headers, json={"addLabelIds": ["SPAM"], "removeLabelIds": ["INBOX"]})
            return jsonify({"success": "Correo marcado como spam"}) if response.status_code == 200 else jsonify({"error": "Error al marcar correo como spam"}), response.status_code

        return jsonify({"error": "Acción no reconocida"}), 400

    @app.route("/accion-outlook", methods=["POST"])
    def ejecutar_accion_outlook():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        message_id = data.get("message_id")

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("Outlook", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        action = interpretar_accion_email(user_text)
        headers = get_outlook_headers(token)

        if "delete" in action:
            response = requests.delete(f"https://graph.microsoft.com/v1.0/me/messages/{message_id}", headers=headers)
            return jsonify({"success": "Correo eliminado"}) if response.status_code == 204 else jsonify({"success": "Correo eliminado"})

        elif "reply" in action:
            reply_text = data.get("reply_text", "")
            response = requests.post(f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/reply",
                                    headers=headers, json={"comment": reply_text})
            return jsonify({"success": "Respuesta enviada"}) if response.status_code == 200 else jsonify({"error": "Error al responder correo"}), response.status_code

        elif "spam" in action:
            response = requests.post(f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/move",
                                    headers=headers, json={"destinationId": "JunkEmail"})
            return jsonify({"success": "Correo marcado como spam"}) if response.status_code == 200 else jsonify({"success": "Correo marcado como spam"})

        return jsonify({"error": "Acción no reconocida"}), 400

    @app.route("/accion-notion", methods=["POST"])
    def ejecutar_accion_notion():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        page_id = data.get("message_id")

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("Notion", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        action = interpretar_accion_productividad(user_text)
        headers = get_notion_headers(token)

        if "mark_done" in action:
            response = requests.patch(f"https://api.notion.com/v1/pages/{page_id}",
                                    headers=headers,
                                    json={"properties": {"status": {"select": {"name": "Listo"}}}})
            return jsonify({"success": "Página marcada como completada"}) if response.status_code == 200 else jsonify({"error": "Error al actualizar estado"}), response.status_code

        elif "delete" in action:
            response = requests.patch(f"https://api.notion.com/v1/pages/{page_id}",
                                    headers=headers, json={"archived": True})  # No puedes eliminar, solo archivar
            return jsonify({"success": "Página archivada"}) if response.status_code == 200 else jsonify({"error": "Error al archivar"}), response.status_code


        return jsonify({"error": "Acción no reconocida"}), 400

    @app.route("/accion-drive", methods=["POST"])
    def ejecutar_accion_drive():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        file_id = data.get("file_id")

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("Drive", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        action = interpretar_accion_archivos(user_text)
        headers = get_google_drive_headers(token)

        if "delete" in action:
            response = requests.delete(f"https://www.googleapis.com/drive/v3/files/{file_id}", headers=headers)
            return jsonify({"success": "Archivo eliminado"}) if response.status_code == 204 else jsonify({"error": "Error al eliminar archivo"}), response.status_code

        elif "rename" in action:
            new_name = data.get("new_name", "")
            response = requests.patch(f"https://www.googleapis.com/drive/v3/files/{file_id}",
                                    headers=headers, json={"name": new_name})
            return jsonify({"success": "Archivo renombrado"}) if response.status_code == 200 else jsonify({"error": "Error al renombrar archivo"}), response.status_code

        return jsonify({"error": "Acción no reconocida"}), 400

    @app.route("/accion-slack", methods=["POST"])
    def ejecutar_accion_slack():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        message_ts = data.get("message_id")
        channel = data.get("channel")

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("Slack", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        action = interpretar_accion_mensajeria(user_text)
        headers = get_slack_headers(token)

        if "reply" in action:
            reply_text = data.get("reply_text", "")
            response = requests.post("https://slack.com/api/chat.postMessage",
                                    headers=headers, json={"channel": channel, "thread_ts": message_ts, "text": reply_text})
            return jsonify({"success": "Mensaje respondido"}) if response.status_code == 200 else jsonify({"error": "Error al responder"}), response.status_code

        return jsonify({"error": "Acción no reconocida"}), 400


    @app.route("/accion-asana", methods=["POST"])
    def ejecutar_accion_asana():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        task_id = data.get("message_id")

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("Asana", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        action = interpretar_accion_productividad(user_text)
        headers = get_asana_headers(token)

        if "complete" in action:
            # Realizar la solicitud PUT para marcar la tarea como completada
            response = requests.put(f"https://app.asana.com/api/1.0/tasks/{task_id}", headers=headers, json={"data": {"completed": True}})
            if response.status_code == 200:
                return jsonify({"success": "Tarea completada"})
            else:
                return jsonify({"error": "Error al completar tarea"}), response.status_code

        elif "delete" in action:
            # Realizar la solicitud DELETE para eliminar la tarea
            response = requests.delete(f"https://app.asana.com/api/1.0/tasks/{task_id}", headers=headers)
            if response.status_code == 204:
                return jsonify({"success": "Tarea eliminada"})
            else:
                return jsonify({"success": "Tarea eliminada"})

        return jsonify({"error": "Acción no reconocida"}), 400

    @app.route("/accion-clickup", methods=["POST"])
    def ejecutar_accion_clickup():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        task_id = data.get("message_id")

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("ClickUp", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        action = interpretar_accion_productividad(user_text)
        headers = {
            "Authorization": token,
            "Content-Type": "application/json"
        }
    
        if "mark_done" in action:
            response = requests.put(f"https://api.clickup.com/api/v2/task/{task_id}", headers=headers, json={"status": "complete"})
            return jsonify({"success": "Tarea completada"}) if response.status_code == 200 else jsonify({"error": "Error al completar tarea"}), response.status_code

        elif "delete" in action:
            response = requests.delete(f"https://api.clickup.com/api/v2/task/{task_id}", headers=headers)
            return jsonify({"success": "Tarea eliminada"}) if response.status_code == 204 else jsonify({"success": "Tarea eliminada"})

        return jsonify({"error": "Acción no reconocida"}), 400

    @app.route("/accion-hubspot", methods=["POST"])
    def ejecutar_accion_hubspot():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        deal_id = data.get("deal_id")

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("HubSpot", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        action = interpretar_accion_hubspot(user_text)
        headers = get_hubspot_headers(token)

        if "update" in action:
            new_stage = data.get("new_stage", "")
            response = requests.patch(f"https://api.hubapi.com/crm/v3/objects/deals/{deal_id}", headers=headers, json={"properties": {"dealstage": new_stage}})
            return jsonify({"success": "Negocio actualizado"}) if response.status_code == 200 else jsonify({"error": "Error al actualizar negocio"}), response.status_code

        return jsonify({"error": "Acción no reconocida"}), 400

    @app.route("/accion-dropbox", methods=["POST"])
    def ejecutar_accion_dropbox():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        file_path = data.get("file_path")

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("Dropbox", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        action = interpretar_accion_archivos(user_text)
        headers = get_dropbox_headers(token)

        if "delete" in action:
            response = requests.post("https://api.dropboxapi.com/2/files/delete_v2", headers=headers, json={"path": file_path})
            return jsonify({"success": "Archivo eliminado"}) if response.status_code == 200 else jsonify({"error": "Error al eliminar archivo"}), response.status_code

        return jsonify({"error": "Acción no reconocida"}), 400

    @app.route("/accion-onedrive", methods=["POST"])
    def ejecutar_accion_onedrive():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        file_id = data.get("file_id")

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("OneDrive", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        action = interpretar_accion_archivos(user_text)
        headers = get_onedrive_headers(token)

        if "delete" in action:
            response = requests.delete(f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}", headers=headers)
            return jsonify({"success": "Archivo eliminado"}) if response.status_code == 204 else jsonify({"error": "Error al eliminar archivo"}), response.status_code

        return jsonify({"error": "Acción no reconocida"}), 400

    @app.route("/accion-teams", methods=["POST"])
    def ejecutar_accion_teams():
        data = request.json
        email = data.get("email")
        user_text = data.get("action_text")
        message_id = data.get("message_id")
        channel_id = data.get("channel_id")

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        token = user.get("integrations", {}).get("Teams", {}).get("token")
        if not token:
            return jsonify({"error": "Token no disponible"}), 400

        action = interpretar_accion_mensajeria(user_text)
        headers = get_teams_headers(token)

        if "reply" in action:
            reply_text = data.get("reply_text", "")
            response = requests.post(f"https://graph.microsoft.com/v1.0/teams/{channel_id}/messages/{message_id}/replies",
                                    headers=headers, json={"body": {"content": reply_text}})
            return jsonify({"success": "Mensaje respondido"}) if response.status_code == 201 else jsonify({"error": "Error al responder"}), response.status_code

        return jsonify({"error": "Acción no reconocida"}), 400

    def post_to_gmail(query):
        """Procesa la consulta y ejecuta la acción en Gmail API o Google Calendar si aplica."""
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        gmail_token = user.get('integrations', {}).get('Gmail', {}).get('token')
        if not gmail_token:
            return jsonify({"error": "Token de Gmail no disponible"}), 400

        match = re.search(r'todos los correos de (.+)', query, re.IGNORECASE)
        if match:
            sender = match.group(1)
            # Determinar la acción: "delete" para eliminar, "spam" para mover a spam.
            action = "delete" if "eliminar" in query.lower() else "spam" if "mover a spam" in query.lower() else None

            if not action:
                return {"error": "Acción no reconocida para Gmail"}

            headers = {"Authorization": f"Bearer {gmail_token}", "Content-Type": "application/json"}
            
            if action == "delete":
                # Primero, buscamos los mensajes del remitente especificado
                list_url = "https://www.googleapis.com/gmail/v1/users/me/messages"
                params = {"q": f"from:{sender}"}
                list_response = requests.get(list_url, headers=headers, params=params)
                messages = list_response.json().get("messages", [])
                
                if not messages:
                    return {"error": f"No se encontraron correos del remitente {sender}"}
                
                delete_results = []
                # Para cada mensaje, movemos a la papelera
                for msg in messages:
                    message_id = msg["id"]
                    delete_url = f"https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}/trash"
                    delete_response = requests.post(delete_url, headers=headers)
                    delete_results.append(delete_response.json())
                
                if delete_results:
                    return {"message": f"Se han eliminado {len(delete_results)} correos del remitente {sender}"}
            
            elif action == "spam":
                # Primero, buscamos los mensajes del remitente especificado
                list_url = "https://www.googleapis.com/gmail/v1/users/me/messages"
                params = {"q": f"from:{sender}"}
                list_response = requests.get(list_url, headers=headers, params=params)
                messages = list_response.json().get("messages", [])
                
                if not messages:
                    return {"error": f"No se encontraron correos del remitente {sender}"}
                
                spam_results = []
                # Para cada mensaje, modificamos las etiquetas para agregar "SPAM"
                for msg in messages:
                    message_id = msg["id"]
                    modify_url = f"https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}/modify"
                    modify_payload = {"addLabelIds": ["SPAM"]}
                    modify_response = requests.post(modify_url, headers=headers, json=modify_payload)
                    spam_results.append(modify_response.json())
                
                if spam_results:
                    return {"message": f"Se han movido {len(spam_results)} correos del remitente {sender} a spam"}
        if "agendar" or "agendame" in query:
            prompt = f"El usuario dijo: '{query}'. Devuelve un JSON con los campos 'date', 'time' y 'subject' que representen la fecha, hora y asunto de la cita agendada (el asunto ponlo con inicial mayuscula en la primer palabra) .Si no se puede extraer la información, devuelve 'unknown'."
        
            response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Eres un asistente que ayuda a organizar citas en Google Calendar."},
                    {"role": "user", "content": prompt}
                ]
            )
            ia_response = response.choices[0].message.content.strip().lower()
            try:
                match = re.search(r'\{[^}]*\}', ia_response, re.DOTALL | re.MULTILINE)
                parsed_info = json.loads(match.group(0))
                if parsed_info == 'unknown':
                    return {"error": "No se pudo interpretar la consulta."}

                date_str = parsed_info['date']
                time_str = parsed_info['time']
                subject = parsed_info['subject']

                months = {
                    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
                    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
                }
                day, month_name = date_str.split(" de ")
                month = months.get(month_name.lower())

                if not month:
                    return {"error": "Mes no válido en la consulta"}

                current_year = datetime.now().year
                hour = int(re.search(r'\d+', time_str).group())
                if "pm" in time_str.lower() and hour != 12:
                    hour += 12
                if "am" in time_str.lower() and hour == 12:
                    hour = 0

                event_datetime = datetime(current_year, month, int(day), hour, 0, 0, tzinfo=ZoneInfo("UTC"))

                event = {
                    "summary": subject,
                    "start": {"dateTime": event_datetime.isoformat(), "timeZone": "UTC"},
                    "end": {"dateTime": (event_datetime.replace(hour=event_datetime.hour + 1)).isoformat(), "timeZone": "UTC"}
                }


                url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
                headers = {"Authorization": f"Bearer {gmail_token}", "Content-Type": "application/json"}
                response = requests.post(url, json=event, headers=headers)
                return {"message": "Se ha agendado tu cita"}
            except Exception as e:
                print(f"Error al procesar la respuesta: {e}")
        return {"error": "No se encontró una acción válida en la consulta"}

    def post_to_outlook(query):
        """Procesa la consulta y ejecuta la acción en Outlook API."""
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        outlook_token = user.get('integrations', {}).get('Outlook', {}).get('token')
        if not outlook_token:
            return jsonify({"error": "Token de Outlook no disponible"}), 400

        match = re.search(r'todos los correos de (.+)', query, re.IGNORECASE)
        if match:
            sender = match.group(1)
            action = "delete" if "eliminar" in query else "spam" if "mover a spam" in query else None

            if not action:
                return {"error": "Acción no reconocida para Outlook"}

            url = "https://graph.microsoft.com/v1.0/me/messages"
            headers = {"Authorization": f"Bearer {outlook_token}", "Content-Type": "application/json"}
            
            # Primero, obtener todos los mensajes del remitente especificado
            params = {"$filter": f"from/emailAddress/address eq '{sender}'"}
            list_response = requests.get(url, headers=headers, params=params)
            messages = list_response.json().get("value", [])

            if not messages:
                return {"error": f"No se encontraron correos del remitente {sender}"}
            
            results = []

            for msg in messages:
                message_id = msg["id"]
                if action == "delete":
                    # Eliminar el correo
                    delete_url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/move"
                    response = requests.post(delete_url, headers=headers, json={"destinationId": "deleteditems"})
                    results.append(response.json())
                
                elif action == "spam":
                    # Mover el correo a la carpeta de "Junk Email"
                    move_url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/move"
                    response = requests.post(move_url, headers=headers, json={"destinationId": "JunkEmail"})
                    results.append(response.json())

            if results:
                if action == "delete":
                    return jsonify({"message": f"Se han eliminado {len(results)} correos del remitente {sender}"})
                elif action == "spam":
                    return jsonify({"message": f"Se han movido {len(results)} correos del remitente {sender} a spam"})
            else:
                return {"error": "No se pudo realizar la acción"}

        return {"error": "No se encontró un remitente válido en la consulta"}
    
    def get_task_id_clickup(name, token):
        headers = get_clickup_headers(token)
        
        # Obtener el equipo
        response = requests.get("https://api.clickup.com/api/v2/team", headers=headers)
        if response.status_code != 200:
            return {"error": "Error al obtener equipos de ClickUp"}, response.status_code
        
        teams = response.json().get("teams", [])
        if not teams:
            return {"error": "No hay equipos en ClickUp"}

        # Seleccionar el primer equipo (puedes personalizar esto si tienes múltiples equipos)
        team_id = teams[0]["id"]

        # Obtener las tareas del equipo
        response = requests.get(f"https://api.clickup.com/api/v2/team/{team_id}/task", headers=headers)
        if response.status_code != 200:
            return {"error": "Error al obtener tareas del equipo"}, response.status_code
        
        tasks = response.json().get("tasks", [])
        if not tasks:
            return {"error": "No hay tareas disponibles en el equipo"}
        
        # Buscar la tarea que coincida con el nombre proporcionado
        for task in tasks:
            if task["name"].lower() == name.lower():
                return task["id"]  # Retorna el ID de la tarea si coincide el nombre

        return {"error": f"No se encontró la tarea con el nombre {name}"}

    def get_task_id_asana(name, token):
        url = "https://app.asana.com/api/1.0/tasks"
        headers = {"Authorization": f"Bearer {token}"}
        params = {"name": name}  # Asumiendo que Asana permite buscar tareas por nombre (verificar en la API de Asana)

        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            tasks = response.json().get('data', [])
            if tasks:
                return tasks[0]["gid"]  # Asana usa "gid" como el identificador de la tarea
        return None

    def get_task_id_notion(name, token):
        url = "https://api.notion.com/v1/databases/YOUR_DATABASE_ID/query"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        data = {
            "filter": {
                "property": "Name",  # Asegúrate de que "Name" es el nombre correcto de la propiedad en tu base de datos
                "rich_text": {
                    "equals": name
                }
            }
        }
        
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            results = response.json().get('results', [])
            if results:
                return results[0]["id"]  # Notion utiliza el "id" de cada página
        return None

    def post_to_notion(query):
        """Procesa la consulta y ejecuta la acción en la API de Notion."""
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        notion_token = user.get('integrations', {}).get('Notion', {}).get('token')
        if not notion_token:
            return jsonify({"error": "Token de Notion no disponible"}), 400

        match = re.search(r'marca como completada la tarea (.+)', query, re.IGNORECASE)
        if match:
            task_name = match.group(1)

            task_id = get_task_id_notion(task_name, notion_token)
            if not task_id:
                return {"error": f"No se encontró la tarea {task_name} en Notion"}

            url = f"https://api.notion.com/v1/pages/{task_id}"
            headers = {
                "Authorization": f"Bearer {notion_token}",
                "Content-Type": "application/json",
                "Notion-Version": "2021-05-13"
            }

            # Marcar la tarea como completada
            data = {
                "properties": {
                    "Status": {
                        "select": {
                            "name": "Completed"  # Asume que "Completed" es el estado de completado
                        }
                    }
                }
            }
            response = requests.patch(url, headers=headers, json=data)
            if response.status_code == 200:
                return jsonify({"message": f"Tarea {task_name} completada correctamente"})
            else:
                return jsonify({"error": "No se pudo completar la tarea"}), 400

        return {"error": "No se encontró una tarea válida en la consulta"}

    def post_to_clickup(query):
        """Procesa la consulta y ejecuta la acción en la API de ClickUp."""
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        clickup_token = user.get('integrations', {}).get('ClickUp', {}).get('token')
        if not clickup_token:
            return jsonify({"error": "Token de ClickUp no disponible"}), 400

        match = re.search(r'(marca como completada|cambia el estado a|elimina) la tarea (.+)', query, re.IGNORECASE)
        if match:
            action = match.group(1).lower()
            task_name = match.group(2)
            
            # Obtener el ID de la tarea
            task_id = get_task_id_clickup(task_name, clickup_token)
            if not task_id:
                return jsonify({"error": f"No se encontró la tarea {task_name} en ClickUp"}), 404

            url = f"https://api.clickup.com/api/v2/task/{task_id}"
            headers = {
                "Authorization": f"Bearer {clickup_token}",
                "Content-Type": "application/json"
            }

            # Acción según la consulta
            if "completada" in action:
                data = {"status": "complete"}  # Asume que "complete" es el estado para tarea completada
                response = requests.put(url, headers=headers, json=data)
                if response.status_code == 200:
                    return jsonify({"message": f"Tarea {task_name} completada correctamente"})
                else:
                    return jsonify({"error": "No se pudo completar la tarea"}), 400
            
            elif "cambia el estado" in action:
                # Extraer el nuevo estado del query
                new_status_match = re.search(r'cambia el estado a (.+)', query, re.IGNORECASE)
                if new_status_match:
                    new_status = new_status_match.group(1)
                    data = {"status": new_status}
                    response = requests.put(url, headers=headers, json=data)
                    if response.status_code == 200:
                        return jsonify({"message": f"Estado de la tarea {task_name} cambiado a {new_status}"})
                    else:
                        return jsonify({"error": "No se pudo cambiar el estado de la tarea"}), 400
                else:
                    return jsonify({"error": "No se proporcionó un nuevo estado"}), 400

            elif "elimina" in action:
                # Eliminar la tarea
                response = requests.delete(f"https://api.clickup.com/api/v2/task/{task_id}", headers=headers)
                if response.status_code == 204:  # El código 204 indica que la tarea se eliminó exitosamente
                    return jsonify({"message": f"Tarea {task_name} eliminada correctamente"})
                else:
                    return jsonify({"error": "No se pudo eliminar la tarea"}), 400

            return jsonify({"error": "Acción no reconocida para ClickUp"}), 400

        return jsonify({"error": "No se encontró una tarea válida en la consulta"}), 400


    def post_to_asana(query):
        """Procesa la consulta y ejecuta la acción en la API de Asana."""
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Se debe proporcionar un email"}), 400

        user = mongo.database.usuarios.find_one({'correo': email})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        asana_token = user.get('integrations', {}).get('Asana', {}).get('token')
        if not asana_token:
            return jsonify({"error": "Token de Asana no disponible"}), 400

        match = re.search(r'marca como completada la tarea (.+)', query, re.IGNORECASE)
        if match:
            task_name = match.group(1)

            task_id = get_task_id_asana(task_name, asana_token)
            if not task_id:
                return {"error": f"No se encontró la tarea {task_name} en Asana"}

            url = f"https://app.asana.com/api/1.0/tasks/{task_id}"
            headers = {
                "Authorization": f"Bearer {asana_token}",
                "Content-Type": "application/json"
            }

            data = {"data": {"completed": True}}
            response = requests.put(url, headers=headers, json=data)
            if response.status_code == 200:
                return jsonify({"message": f"Tarea {task_name} completada correctamente"})
            else:
                return jsonify({"error": "No se pudo completar la tarea"}), 400

        return {"error": "No se encontró una tarea válida en la consulta"}