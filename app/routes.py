from flask import redirect, Blueprint, url_for, session, request, jsonify
import requests
import time
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
        print(user_email)
        integration_name = request_data.get("integration")
        print(integration_name)
        token = request_data.get("token")
        print(token)
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
        if integration_name not in ["Notion", "Slack"]:
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
    def search_gmail():
        time.sleep(4)
        email = request.args.get('email')
        query = request.args.get('solicitud')
        proyecto = request.args.get('proyecto')
        persona = request.args.get('persona')
        company = request.args.get('company')

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

            if company:
                query += f'" {company}"' 
            
            if any(palabra in query.lower() for palabra in ["ultimo", "último"]):    
                if any(palabra in query.lower() for palabra in ["mi", "mí", "mis"]):
                    query = "is:inbox"

            if any(palabra in query.lower() for palabra in ["buscar", "busca", "buscame"]):
                query = f'from:"{persona}"'
                    
            url = "https://www.googleapis.com/gmail/v1/users/me/messages"
            headers = {
                'Authorization': f"Bearer {gmail_token}"
            }
            print("ANTES DEL RESPONSE",query)
            params = {"q": query, "maxResults": 5 }
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()

            messages = response.json().get('messages', [])
            print(messages)
            if not messages:
                return jsonify({"message": "No se encontraron resultados en Gmail"}), 200

            keywords = query.lower().split()
            print(keywords)
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
            # Añadir los detalles del mensaje a la lista
            if any(palabra in request.args.get('solicitud').lower() for palabra in ["buscar", "busca", "buscame", "ultimo", "último", "mi", "mí"]):
                search_results.append({
                    'from': sender,
                    'date': date,
                    'subject': subject,
                    'body': body,
                    'link': mail_url
                })
            if any(keyword in subject.lower() for keyword in keywords):
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
    def search_notion():
        email = request.args.get('email')
        proyecto = request.args.get('proyecto')
        compañia= request.args.get('company')
        empresa = request.args.get('empresa')
        query = ""
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

            if proyecto:
                query = proyecto
            if compañia:
                query = compañia
            if empresa:
                query = empresa

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

            # Procesar resultados
            results = response.json().get("results", [])
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
                    # Verificar y extraer status de configuraciones complejas
                    if property_value.get("type") == "status":
                        page_info["properties"][property_name] = property_value["status"].get("name", None)
                    elif property_value.get("type") == "table" or property_value.get("type") == "collection":
                        # Procesar tablas o bloques anidados
                        table_results = property_value.get("results", [])
                        for table_entry in table_results:
                            if "status" in table_entry.get("properties", {}):
                                page_info["properties"][property_name] = table_entry["properties"]["status"].get("name", None)
                    elif property_name in ["Nombre de tarea", "Nombre del proyecto"] and property_value.get("title"):
                        page_info["properties"][property_name] = property_value["title"][0]["plain_text"]
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

                # Filtrar resultados relevantes
                if (
                    'Resumen' in page_info["properties"]
                    and page_info["properties"]["Resumen"]
                    and query.lower() in page_info["properties"]["Resumen"][0].lower()
                ):
                    simplified_results.append(page_info)
                elif (
                    'Nombre de tarea' in page_info["properties"]
                    and query.lower() in page_info["properties"]["Nombre de tarea"].lower()
                ):
                    simplified_results.append(page_info)
                elif (
                    'Nombre del proyecto' in page_info["properties"]
                    and query.lower() in page_info["properties"]["Nombre del proyecto"].lower()
                ):
                    simplified_results.append(page_info)

            # Si no hay resultados simplificados
            if not simplified_results:
                return jsonify({"error": "No se encontraron resultados en Notion"}), 404

            return jsonify(simplified_results)

        except requests.RequestException as e:
            return jsonify({"error": "Error al realizar la solicitud a Notion", "details": str(e)}), 500
        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500

    @app.route('/search/slack', methods=['GET'])
    def search_slack():
        email = request.args.get('email')
        query = request.args.get('solicitud')

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
                return jsonify({"error": "Error al buscar en Slack", "details": data}), response.status_code

            # Extraer y procesar resultados
            messages = data.get("messages", {}).get("matches", [])
            if not messages:
                return jsonify({"message": "No se encontraron resultados en Slack"}), 200

            slack_results = [
                {
                    "channel": message.get("channel", {}).get("name"),
                    "user": message.get("username"),
                    "text": message.get("text"),
                    "ts": message.get("ts"),
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
    def search_outlook():
        email = request.args.get('email')
        query = request.args.get('solicitud')
        persona = request.args.get('persona')
        fecha = request.args.get('fecha')

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

            # Si se especifica una persona (debe ser una dirección de correo electrónico)
            if persona:
                search_query += f' from{persona}'

            # Si se especifica una fecha, filtrar por fecha de recepción
            if fecha:
                try:
                    fecha_relativa = parse_fecha_relativa(fecha)
                    # Formatear la fecha a ISO 8601
                    fecha_formateada = fecha_relativa.strftime('%Y-%m-%dT%H:%M:%SZ')
                    search_query += f' received ge {fecha_formateada}'
                except ValueError:
                    return jsonify({"error": "Formato de fecha relativa inválido"}), 400

            url = 'https://graph.microsoft.com/v1.0/me/messages'
            headers = {
                'Authorization': f"Bearer {outlook_token}",
                'Content-Type': 'application/json'
            }

            print("OUTLOOK")
            # Aquí puedes agregar los parámetros como $top y $orderby
            params = {
                '$search': search_query, '$top':10
            }

            response = requests.get(url, headers=headers, params=params)
            keywords = query.lower().split()
            print(keywords)
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
                # Filtrar palabras clave en el cuerpo del mensaje
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
            'Authorization': f"Bearer {token}",
            'Content-Type': 'application/json'
        }

    @app.route('/search/hubspot', methods=['GET'])
    def search_hubspot():
        time.sleep(4)
        # Obtener los parámetros del cuerpo de la solicitud
        solicitud =  request.args.get("solicitud")
        print(solicitud)
        empresa = request.args.get("empresa")
        compania =  request.args.get("compañia")
        persona =  request.args.get("persona")
        datos_adicionales =  request.args.get("datos_adicionales")

        # Si no se proporcionó solicitud, retornar error
        if not solicitud:
            return jsonify({"error": "No se proporcionó un término de búsqueda"}), 400

        # Buscar usuario en la base de datos
        email =  request.args.get("email")
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

        # Manejo de las solicitudes según el prompt
        if solicitud == "todos mis contactos":
            # Realizar búsqueda de todos los contactos
            search_data = {
                "filters": [],
                "properties": ["firstname", "lastname", "email", "hubspot_owner_id"]
            }
            response = requests.post(
                "https://api.hubapi.com/crm/v3/objects/contacts/search",
                headers=headers,
                json=search_data
            )
            print("HUBSPOT",response)
            if response.status_code == 200:
                contacts = response.json().get("results", [])
                search_results["contacts"] = [
                    {
                        "firstname": contact["properties"].get("firstname", "N/A"),
                        "lastname": contact["properties"].get("lastname", "N/A"),
                        "email": contact["properties"].get("email", "N/A"),
                        "owner": contact["properties"].get("hubspot_owner_id", "N/A")
                    }
                    for contact in contacts
                ]
                if not search_results["contacts"]:
                    search_results["contacts"] = {"message": "No se encontraron contactos."}
            else:
                return jsonify({"error": f"Error al buscar en HubSpot: {response.status_code} {response.text}"}), response.status_code

        elif "contactos" in solicitud.lower():
            print("HOLALALA SOLICITUD")
            # Si no se proporcionó compañía, buscar todos los contactos
            if compania:
                print(compania)
                # Buscar contactos de una compañía específica
                search_data = {
                    "filters": [{"propertyName": "company", "operator": "EQ", "value": compania}],
                    "properties": ["firstname", "lastname", "email", "company", "hubspot_owner_id"]
                }
            else:
                # Buscar todos los contactos (sin filtro por compañía)
                search_data = {
                    "filters": [],
                    "properties": ["firstname", "lastname", "email", "company", "hubspot_owner_id"]
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
                        "owner": contact["properties"].get("hubspot_owner_id", "N/A")
                    }
                    for contact in contacts
                ]
                if not search_results["contacts"]:
                    search_results["contacts"] = {"message": f"No se encontraron contactos{(' para ' + compania) if compania else ''}."}
            else:
                return jsonify({"error": f"Error al buscar en HubSpot: {response.status_code} {response.text}"}), response.status_code
        elif "empresa" in solicitud.lower() or "company" in solicitud.lower() and persona:
            print("HOLAAA")
            # Verificar si se proporcionó el nombre de la persona
            if not persona:
                return jsonify({"error": "Persona no proporcionada"}), 400

            # Dividir el nombre completo de la persona en primer nombre y apellido
            persona_nombre = persona.split()
            if len(persona_nombre) < 2:
                return jsonify({"error": "Nombre completo de la persona no válido"}), 400

            search_data = {
                "filters": [
                    {"propertyName": "firstname", "operator": "EQ", "value": persona_nombre[0]},  # Primer nombre
                    {"propertyName": "lastname", "operator": "EQ", "value": persona_nombre[1]}   # Apellido
                ],
                "properties": ["firstname", "lastname", "company", "hubspot_owner_id"]
            }

            response = requests.post(
                "https://api.hubapi.com/crm/v3/objects/contacts/search",
                headers=headers,
                json=search_data
            )

            print(response)
            print(response.status_code)


            if response.status_code == 200:
                contacts = response.json().get("results", [])
                search_results["contacts"] = [
                    {
                        "firstname": contact["properties"].get("firstname", "N/A"),
                        "lastname": contact["properties"].get("lastname", "N/A"),
                        "company": contact["properties"].get("company", "N/A"),
                        "owner": contact["properties"].get("hubspot_owner_id", "N/A")
                    }
                    for contact in contacts
                ]
                
                # Si no se encuentran contactos, se envía un mensaje indicando que no se encontraron empresas
                if not search_results["contacts"]:
                    search_results["contacts"] = {"message": f"No se encontraron empresas para {persona}."}
            else:
                return jsonify({"error": f"Error al buscar en HubSpot: {response.status_code} {response.text}"}), response.status_code

        else:
            return jsonify({"error": "Tipo de solicitud no soportado"}), 400
        print ("RESPUESTA" , (search_results))
        return jsonify(search_results)

    @app.route('/askIa', methods=['GET'])
    def ask():
        email = request.args.get('email')
        query = request.args.get('query')
        datos_adicionales = request.args.get('datos_adicionales')

        if not email or not query:
            return jsonify({"error": "Se deben proporcionar tanto el email como la consulta"}), 400

        try:
            user = mongo.database.usuarios.find_one({'correo': email})
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404
            search_results_data = {
                'gmail': [],
                'slack': [],
                'notion': [],
                'outlook': [],
                'hubspot': {}
            }

            try:
                notion_results = search_notion()
                search_results_data['notion'] = (
                    notion_results.get_json() 
                    if hasattr(notion_results, 'get_json') 
                    else notion_results
                )
            except Exception as e:
                search_results_data['notion'] = [f"Error al buscar en Notion: {str(e)}"]
            
            try:
                gmail_results = search_gmail()
                search_results_data['gmail'] = (
                    gmail_results.get_json() 
                    if hasattr(gmail_results, 'get_json') 
                    else gmail_results
                )
            except Exception as e:
                search_results_data['gmail'] = [f"Error al buscar en Gmail: {str(e)}"]

            try:
                slack_results = search_slack()
                search_results_data['slack'] = (
                    slack_results.get_json() 
                    if hasattr(slack_results, 'get_json') 
                    else slack_results
                )
            except Exception as e:
                search_results_data['slack'] = [f"Error al buscar en Slack: {str(e)}"]

            try:
                outlook_results = search_outlook()
                search_results_data['outlook'] = (
                    outlook_results.get_json() 
                    if hasattr(outlook_results, 'get_json') 
                    else outlook_results
                )
            except Exception as e:
                search_results_data['outlook'] = [f"Error al buscar en Outlook: {str(e)}"]

            try:
                hubspot_results = search_hubspot()
                search_results_data['hubspot'] = (
                    hubspot_results.get_json() 
                    if hasattr(hubspot_results, 'get_json') 
                    else hubspot_results
                )
            except Exception as e:
                search_results_data['hubspot'] = [f"Error al buscar en HubSpot: {str(e)}"]

            try:
                prompt = generate_prompt(query, search_results_data)
                response = openai.chat.completions.create(
                    model="gpt-4-turbo",
                    messages=[{
                        "role": "system",
                        "content": "Eres un asistente útil el cual está conectado con diversas aplicaciones y automatizarás el proceso de buscar información en base a la query que se te envie, tomando toda la información necesaria"
                    }, {
                        "role": "user",
                        "content": prompt
                    }],
                    max_tokens=4096
                )
                ia_response = response.choices[0].message.content.strip()
                
                if not ia_response:
                    return jsonify({"error": "La respuesta de la IA está vacía"}), 500
                
                return jsonify({"response": to_ascii(ia_response)})

            except Exception as e:
                return jsonify({"error": f"Error al generar la respuesta de la IA: {str(e)}"}), 500

        except Exception as e:
            return jsonify({"error": f"Error general: {str(e)}"}), 500
    
    def generate_prompt(query, search_results):
        contact_keywords = ['contacto', 'contactos', 'persona', 'personas', 'cliente', 'clientes', 'representante','teléfono']
        is_contact_query = any(keyword in query.lower() for keyword in contact_keywords)

        has_results = any(
            search_results.get(platform, []) 
            for platform in ['gmail', 'slack', 'notion', 'outlook', 'hubspot']
        )
        
        if not has_results:
            return """Lo siento, no encontré información relacionada con tu consulta. 
            ¿Podrías reformular tu pregunta o proporcionar más detalles? 
            Por ejemplo, puedes especificar:
            - Un período de tiempo específico
            - Nombres o correos electrónicos específicos
            - Palabras clave más precisas
            - O el contexto específico que estás buscando"""

        gmail_results = "\n".join([
            f"De: {email.get('from', 'Desconocido')} | Asunto: {email.get('subject', 'Sin asunto')} | Fecha: {email.get('date', 'Sin fecha')} | Body: {email.get('body', 'Sin cuerpo')}"
            for email in search_results.get('gmail', []) if isinstance(email, dict)
        ]) or "No se encontraron correos relacionados en Gmail."

        slack_results = "\n".join([
            f"Canal: {msg.get('channel', 'Desconocido')} | Usuario: {msg.get('user', 'Desconocido')} | Mensaje: {msg.get('text', 'Sin mensaje')} | Fecha: {msg.get('ts', 'Sin fecha')}"
            for msg in search_results.get('slack', []) if isinstance(msg, dict)
        ]) or "No se encontraron mensajes relacionados en Slack."

        notion_results = "\n".join([
            f"Página ID: {page.get('id', 'Sin ID')} | URL: {page.get('url', 'Sin URL')} | Estado: {page['properties'].get('Estado', 'Sin estado')} | Nombre del proyecto: {page['properties'].get('Nombre del proyecto', 'Sin título')} | Resumen: {', '.join(page['properties'].get('Resumen', ['Sin resumen']))}"
            for page in search_results.get('notion', []) if isinstance(page, dict)
        ]) or "No se encontraron notas relacionadas en Notion."

        outlook_results = "\n".join([
            f"De: {email.get('sender', 'Desconocido')} | Asunto: {email.get('subject', 'Sin asunto')} | Fecha: {email.get('receivedDateTime', 'Sin fecha')}"
            for email in search_results.get('outlook', []) if isinstance(email, dict)
        ]) or "No se encontraron correos relacionados en Outlook."

        hubspot_results = []
        hubspot_data = search_results.get("hubspot", {})

        try:
            if "contacts" in hubspot_data:
                contacts = hubspot_data["contacts"]
                if isinstance(contacts, list) and contacts:
                    hubspot_results.append("Contactos:\n" + "\n".join([
                        f"Nombre: {contact.get('firstname', 'N/A')} {contact.get('lastname', 'N/A')} | "
                        f"Correo: {contact.get('email', 'N/A')} | "
                        f"Compañía: {contact.get('company', 'N/A')} | "
                        f"Teléfono: {contact.get('phone', 'N/A')} | "
                        f"Cargo: {contact.get('jobtitle', 'N/A')}"
                        for contact in contacts
                    ]))

            if "companies" in hubspot_data:
                companies = hubspot_data["companies"]
                if isinstance(companies, list) and companies:
                    hubspot_results.append("Compañías:\n" + "\n".join([
                        f"Compañía: {company.get('company', 'N/A')} | "
                        f"Teléfono: {company.get('phone', 'N/A')} | "
                        f"Industria: {company.get('industry', 'N/A')} | "
                        f"Sitio web: {company.get('website', 'N/A')}"
                        for company in companies
                    ]))

            if "deals" in hubspot_data:
                deals = hubspot_data["deals"]
                if isinstance(deals, list) and deals:
                    hubspot_results.append("Negocios:\n" + "\n".join([
                        f"Negocio: {deal.get('name', 'N/A')} | "
                        f"Monto: {deal.get('price', 'N/A')} | "
                        f"Estado: {deal.get('stage', 'N/A')} | "
                        f"Fecha cierre: {deal.get('closedate', 'N/A')}"
                        for deal in deals
                    ]))

        except Exception as e:
            hubspot_results.append(f"Error procesando datos de HubSpot: {str(e)}")

        hubspot_results = "\n".join(hubspot_results) or "No se encontraron resultados relacionados en HubSpot."

        # Ajustar el prompt según el tipo de consulta
        if is_contact_query:
            prompt = f"""Respuesta concisa a la consulta: "{query}"

            Información principal de HubSpot:
            {hubspot_results}

            Información complementaria:
            Gmail:
            {gmail_results}

            Outlook:
            {outlook_results}

            Slack:
            {slack_results}

            Notion:
            {notion_results}

            Instrucciones de respuesta:
            1. Prioriza la información de contactos y empresas de HubSpot
            2. Complementa con información relevante de correos o mensajes si es necesario
            3. Proporciona una respuesta directa y estructurada
            4. Incluye detalles de contacto específicos cuando estén disponibles
            5. No repitas información innecesariamente
            6. Menciona URLs solo una vez
            7. Si la información parece inconsistente o incompleta, indícalo
            """
        else:
            prompt = f"""Respuesta concisa a la consulta: "{query}"

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

            Instrucciones de respuesta:
            1. Responde de forma concisa y directa
            2. Enfócate solo en la información más relevante para la consulta
            3. No repitas detalles innecesarios
            4. Incluye fechas y URLs importantes (solo una vez)
            5. Asegúrate de que la respuesta sea coherente y fácil de entender
            6. Si la información parece incompleta o inconsistente, indícalo
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
        

    @app.route("/api/chatAi", methods=["POST"])
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
        Para cualquier otra consulta, proporciona una respuesta útil y adaptada al contexto del usuario y lo más importante siempre menciona que ingresen sesión primero con Shiffu y luego con sus aplicaciones para ayudarlos de una mejor manera. Si te preguntan como iniciar sesión en shiffu menciona que arriba se encuentran dos botones y uno sirve para registrarse en Shiffu y el otro para iniciar sesión en Shiffu.
        """
        
        # Palabras clave para detectar saludos y peticiones
        saludos = ["hola", "buenos días", "buenas tardes", "saludos", "hey", "qué tal"]
        peticiones = ["buscar", "necesito", "quiero", "ayúdame", "consulta", "pregunta"]
        
        # Respuesta predeterminada
        ia_response = "Lo siento, no entendí tu mensaje. ¿Puedes reformularlo?"
        
        if user_messages:
            try:
                # Analizamos el último mensaje del usuario
                last_message = user_messages[-1].get("content", "").lower()
                
                # Detectamos si es un saludo
                if any(saludo in last_message for saludo in saludos):
                    ia_response = "¡Hola! Soy Shiffu, tu asistente virtual. ¿En qué puedo ayudarte hoy? 😊"
                
                # Detectamos si es una petición
                elif any(peticion in last_message for peticion in peticiones):
                    # Validamos si menciona "api" o "apis"
                    if "api" in last_message or "apis" in last_message:
                        # Procesar envío de email (simulación)
                        try:
                            email = request.args.get('email')

                            if not email:
                                return jsonify({"error": "Se deben proporcionar tanto el email como la consulta"}), 400

                            try:
                                user = mongo.database.usuarios.find_one({'correo': email})
                                if not user:
                                    return jsonify({"error": "Usuario no encontrado"}), 404

                                # Inicializar datos de resultados de búsqueda
                                search_results_data = {
                                    'gmail': [],
                                    'slack': [],
                                    'notion': [],
                                    'outlook': [],
                                    'hubspot': {}
                                }

                                # Consultar las APIs dependiendo de la consulta
                                if "notion" in last_message.lower():
                                    try:
                                        notion_results = search_notion()
                                        search_results_data['notion'] = (
                                            notion_results.get_json() 
                                            if hasattr(notion_results, 'get_json') 
                                            else notion_results
                                        )
                                    except Exception as e:
                                        search_results_data['notion'] = [f"Error al buscar en Notion: {str(e)}"]

                                if "gmail" in last_message.lower():
                                    try:
                                        gmail_results = search_gmail()
                                        search_results_data['gmail'] = (
                                            gmail_results.get_json() 
                                            if hasattr(gmail_results, 'get_json') 
                                            else gmail_results
                                        )
                                    except Exception as e:
                                        search_results_data['gmail'] = [f"Error al buscar en Gmail: {str(e)}"]

                                if "slack" in last_message.lower():
                                    try:
                                        slack_results = search_slack()
                                        search_results_data['slack'] = (
                                            slack_results.get_json() 
                                            if hasattr(slack_results, 'get_json') 
                                            else slack_results
                                        )
                                    except Exception as e:
                                        search_results_data['slack'] = [f"Error al buscar en Slack: {str(e)}"]

                                if "outlook" in last_message.lower():
                                    try:
                                        outlook_results = search_outlook()
                                        search_results_data['outlook'] = (
                                            outlook_results.get_json() 
                                            if hasattr(outlook_results, 'get_json') 
                                            else outlook_results
                                        )
                                    except Exception as e:
                                        search_results_data['outlook'] = [f"Error al buscar en Outlook: {str(e)}"]

                                if "hubspot" in last_message.lower():
                                    try:
                                        hubspot_results = search_hubspot()
                                        search_results_data['hubspot'] = (
                                            hubspot_results.get_json() 
                                            if hasattr(hubspot_results, 'get_json') 
                                            else hubspot_results
                                        )
                                    except Exception as e:
                                        search_results_data['hubspot'] = [f"Error al buscar en HubSpot: {str(e)}"]

                                # Generar el prompt usando los datos de búsqueda
                                try:
                                    prompt = generate_prompt(last_message, search_results_data)
                                    response = openai.ChatCompletion.create(
                                        model="gpt-4-turbo",
                                        messages=[{
                                            "role": "system",
                                            "content": "Eres un asistente útil el cual está conectado con diversas aplicaciones y automatizarás el proceso de buscar información en base a la query que se te envíe, tomando toda la información necesaria"
                                        }, {
                                            "role": "user",
                                            "content": prompt
                                        }],
                                        max_tokens=4096
                                    )
                                    ia_response = response.choices[0].message.content.strip()

                                    if not ia_response:
                                        return jsonify({"error": "La respuesta de la IA está vacía"}), 500

                                    return jsonify({"response": to_ascii(ia_response)})

                                except Exception as e:
                                    return jsonify({"error": f"Error al generar la respuesta de la IA: {str(e)}"}), 500

                            except Exception as e:
                                return jsonify({"error": f"Error general: {str(e)}"}), 500

                        except Exception as e:
                            ia_response = f"Lo siento, ocurrió un error al procesar tu solicitud: {e}"
                    else:
                        ia_response = "Por favor, indica cuáles son las APIs específicas que necesitas que busque información. 😊"
                
                else:
                    # Llamada a OpenAI para procesar la conversación
                    response = openai.ChatCompletion.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "system", "content": system_message},
                            *user_messages  # Mensajes enviados por el usuario
                        ],
                        max_tokens=150
                    )
                    # Extraemos la respuesta de OpenAI
                    ia_response = response.choices[0].message.content.strip()
            except Exception as e:
                ia_response = f"Lo siento, ocurrió un error al procesar tu mensaje: {e}"
        
        # Retornamos la respuesta al frontend
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