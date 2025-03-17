from flask import request, jsonify
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from dateutil.relativedelta import relativedelta
from config import Config
from urllib.parse import urlencode
import base64 
from bs4 import BeautifulSoup
from datetime import datetime
import unicodedata
import re
import json
import os
import quopri
import openai
openai.api_key=Config.CHAT_API_KEY

<<<<<<< HEAD
def setup_routes_searchs(app, mongo, cache):
=======
def setup_routes_searchs(app,mongo):
>>>>>>> 2ee3a3c5e48cf23453f0aefb56306d34c907b646
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
            
            if query == "n/a":
                return jsonify({"message": "No hay resultados en Gmail"}), 200

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

                        # Añadir a los resultados
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
        query = request.args.get('query')
        
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
            original_query = query
            if "tarea" in query.lower():
                query = query.lower().split("tarea", 1)[1].strip()
            elif "proyecto" in query.lower():
                query = query.lower().split("proyecto", 1)[1].strip()
            elif "compañia" in query.lower():
                query = query.lower().split("compañia", 1)[1].strip()
            elif "empresa" in query.lower():
                query = query.lower().split("empresa", 1)[1].strip()
            elif "estado" in query.lower():
                if "tarea" in query.lower():
                    query = query.lower().split("tarea", 1)[1].strip()
                elif "proyecto" in query.lower():
                    query = query.lower().split("proyecto", 1)[1].strip()
                else:
                    query = "estado"

            # Verificar término de búsqueda
            if not query:
                return jsonify({"error": "No se proporcionó un término de búsqueda válido"}), 400

            # Configuración de solicitud a Notion
            url = 'https://api.notion.com/v1/search'
            headers = {
                'Authorization': f'Bearer {notion_token}',
                'Notion-Version': '2022-06-28',
                'Content-Type': 'application/json'
            }
            
            # Parámetros de búsqueda
            search_params = {
                "query": query,
                "sort": {
                    "direction": "descending",
                    "timestamp": "last_edited_time"
                },
                "page_size": 10
            }
            
            # Realizar solicitud a Notion
            response = requests.post(url, headers=headers, json=search_params)
            response.raise_for_status()
            notion_response = response.json()

            # Procesar resultados
            results = notion_response.get("results", [])
            if not results:
                return jsonify({"notion": []})

            # Lista para almacenar resultados procesados
            processed_results = []
            
            for result in results:
                # Extraer información básica
                page_info = {
                    "id": result["id"],
                    "url": result.get("url", "Sin URL"),
                    "last_edited_time": result.get("last_edited_time", "Sin fecha de edición"),
                    "properties": {}
                }
                
                # Extraer propiedades relevantes
                properties = result.get("properties", {})
                
                # Inicializar valores por defecto
                nombre = "Sin Nombre"
                estado = "Sin Estado"
                
                # Buscar nombre/título
                for property_name, property_value in properties.items():
                    property_type = property_value.get("type")
                    
                    # Extraer nombre/título
                    if property_type == "title" and property_value.get("title"):
                        if property_value["title"] and len(property_value["title"]) > 0:
                            nombre = property_value["title"][0]["plain_text"]
                        page_info["properties"]["Nombre"] = nombre
                    
                    # Extraer estado
                    elif property_type == "status" and property_value.get("status"):
                        estado = property_value["status"].get("name", "Sin Estado")
                        page_info["properties"]["Estado"] = estado
                    
                    # Buscar en otros campos
                    elif property_name.lower() in ["nombre", "name", "título", "title"]:
                        if property_type == "rich_text" and property_value.get("rich_text") and len(property_value["rich_text"]) > 0:
                            nombre = property_value["rich_text"][0]["plain_text"]
                        page_info["properties"]["Nombre"] = nombre
                    
                    elif property_name.lower() in ["estado", "status"]:
                        if property_type == "select" and property_value.get("select"):
                            estado = property_value["select"].get("name", "Sin Estado")
                        page_info["properties"]["Estado"] = estado
                
                # Si no se encontró nombre en las propiedades, buscar en el título principal
                if "Nombre" not in page_info["properties"]:
                    if "title" in result and result["title"] and len(result["title"]) > 0:
                        nombre = result["title"][0]["plain_text"]
                    page_info["properties"]["Nombre"] = nombre
                
                # Si no se encontró estado, usar valor predeterminado
                if "Estado" not in page_info["properties"]:
                    page_info["properties"]["Estado"] = estado
                    
                # Formatear fecha
                if page_info["last_edited_time"] != "Sin fecha de edición":
                    try:
                        date_obj = datetime.datetime.fromisoformat(page_info["last_edited_time"].replace("Z", "+00:00"))
                        page_info["last_edited_time"] = date_obj.strftime("%d/%m/%Y %H:%M")
                    except:
                        pass
                    
                processed_results.append(page_info)
            
            # Retornar solo los resultados procesados
            return jsonify({"notion": processed_results})

        except requests.RequestException as e:
            return jsonify({"error": f"Error al realizar la solicitud a Notion: {str(e)}"}), 500
        except Exception as e:
            return jsonify({"error": f"Error inesperado: {str(e)}"}), 500

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
            print(data)
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
        
    def decode_message_body(data):
        """Decodifica el cuerpo del mensaje en base64."""
        return base64.urlsafe_b64decode(data).decode('utf-8')

    def extract_text_from_html(html_content):
        """Extrae texto del contenido HTML."""
        soup = BeautifulSoup(html_content, 'html.parser')
        return soup.get_text()
    
    @app.route('/search/clickup', methods=["GET"])
    def search_clickup():
        email = request.args.get('email')
        query = request.args.get('query')
        
        try:
            # Verificar usuario en la base de datos
            user = get_user_from_db(email, cache, mongo)
            if not user:
                return jsonify({"error": "Usuario no encontrado"}), 404

            # Verificar token de ClickUp
            clickup_integration = user.get('integrations', {}).get('ClickUp', None)
            clickup_token = clickup_integration.get('token') if clickup_integration else None
            
            if not clickup_token:
                return jsonify({"error": "Token de ClickUp no disponible"}), 400
            
            # Procesar consulta según el patrón
            original_query = query
            search_type = "general"
            
            # Identificar el tipo de búsqueda
            if "tarea" in query.lower():
                search_type = "tarea"
                query = query.lower().split("tarea", 1)[1].strip()
            elif "proyecto" in query.lower():
                search_type = "proyecto"
                query = query.lower().split("proyecto", 1)[1].strip()
            elif "estado" in query.lower():
                search_type = "estado"
                if "tarea" in query.lower():
                    query = query.lower().split("tarea", 1)[1].strip()
                elif "proyecto" in query.lower():
                    query = query.lower().split("proyecto", 1)[1].strip()
                else:
                    # Si solo pregunta por "estado", buscaremos el estado general de las tareas
                    query = ""  # Búsqueda más amplia para obtener el estado general
                    
            # Verificar término de búsqueda
            if not query and search_type == "general":
                return jsonify({"clickup": [], "message": "No se proporcionó un término de búsqueda"}), 400

            # Obtener el team_id
            team_url = "https://api.clickup.com/api/v2/team"
            headers = {'Authorization': f"Bearer {clickup_token}"}
            team_response = requests.get(team_url, headers=headers)
            
            if team_response.status_code != 200:
                return jsonify({"clickup": [], "error": "No se pudo obtener el team_id", "details": team_response.text}), team_response.status_code

            teams = team_response.json().get('teams', [])
            if not teams:
                return jsonify({"clickup": [], "error": "El usuario no pertenece a ningún equipo en ClickUp"}), 400

            team_id = teams[0].get('id')  # Tomamos el primer equipo disponible
            
            results = []
            
            # Estrategia de búsqueda basada en el tipo
            if search_type in ["general", "tarea", "estado"]:
                # Buscar tareas
                task_url = f"https://api.clickup.com/api/v2/team/{team_id}/task"
                params = {"query": query}
                
                # Si está buscando estados específicamente, podemos ampliar la búsqueda
                if search_type == "estado" and not query:
                    params = {"subtasks": True, "statuses": ["active", "closed"]}
                    
                task_response = requests.get(task_url, headers=headers, params=params)
                
                if task_response.status_code == 200:
                    tasks = task_response.json().get('tasks', [])
                    
                    for task in tasks:
                        # Formatear fecha si existe
                        due_date = "Sin fecha"
                        if task.get('due_date'):
                            try:
                                # Convertir timestamp a fecha legible
                                due_timestamp = int(task.get('due_date')) / 1000  # ClickUp usa milisegundos
                                due_date = datetime.datetime.fromtimestamp(due_timestamp).strftime("%d/%m/%Y %H:%M")
                            except:
                                due_date = task.get('due_date', 'Sin fecha')
                        
                        # Determinar si la tarea coincide con la búsqueda de estado
                        status_match = True
                        if search_type == "estado" and query:
                            status_name = task.get('status', {}).get('status', '').lower()
                            status_match = query.lower() in status_name
                        
                        if search_type != "estado" or status_match or not query:
                            task_info = {
                                'id': task.get('id'),
                                'task_name': task.get('name', 'Sin título'),
                                'status': task.get('status', {}).get('status', 'Sin estado'),
                                'priority': get_priority_name(task.get('priority')),
                                'assignees': [assignee.get('username', 'Desconocido') for assignee in task.get('assignees', [])] or ['Sin asignar'],
                                'due_date': due_date,
                                'project': task.get('project', {}).get('name', 'Sin proyecto'),
                                'list': task.get('list', {}).get('name', 'Sin lista'),
                                'url': f"https://app.clickup.com/t/{task.get('id')}"
                            }
                            results.append(task_info)
            
            if search_type in ["general", "proyecto"]:
                # Buscar espacios y carpetas (proyectos)
                spaces_url = f"https://api.clickup.com/api/v2/team/{team_id}/space"
                spaces_response = requests.get(spaces_url, headers=headers)
                
                if spaces_response.status_code == 200:
                    spaces = spaces_response.json().get('spaces', [])
                    
                    for space in spaces:
                        space_id = space.get('id')
                        
                        # Buscar carpetas en el espacio
                        folders_url = f"https://api.clickup.com/api/v2/space/{space_id}/folder"
                        folders_response = requests.get(folders_url, headers=headers)
                        
                        if folders_response.status_code == 200:
                            folders = folders_response.json().get('folders', [])
                            
                            for folder in folders:
                                folder_name = folder.get('name', '')
                                
                                # Filtrar por término de búsqueda si es búsqueda de proyecto
                                if search_type != "proyecto" or query.lower() in folder_name.lower():
                                    # Obtener listas dentro de la carpeta
                                    folder_id = folder.get('id')
                                    lists_url = f"https://api.clickup.com/api/v2/folder/{folder_id}/list"
                                    lists_response = requests.get(lists_url, headers=headers)
                                    
                                    lists = []
                                    if lists_response.status_code == 200:
                                        lists = lists_response.json().get('lists', [])
                                    
                                    project_info = {
                                        'id': folder.get('id'),
                                        'project_name': folder_name,
                                        'space': space.get('name', 'Sin espacio'),
                                        'lists': [{'name': lst.get('name'), 'id': lst.get('id')} for lst in lists],
                                        'status': folder.get('status', {}).get('status', 'Activo'),
                                        'task_count': folder.get('task_count', 0),
                                        'url': f"https://app.clickup.com/s/{space_id}/folders/{folder_id}",
                                        'type': 'project'
                                    }
                                    results.append(project_info)
            
            # Si no hay resultados
            if not results:
                return jsonify({"clickup": []})
            
            return jsonify({"clickup": results})
            
        except requests.RequestException as e:
            return jsonify({"clickup": [], "error": f"Error al realizar la solicitud a ClickUp: {str(e)}"}), 500
        except Exception as e:
            return jsonify({"clickup": [], "error": f"Error inesperado: {str(e)}"}), 500

    # Función auxiliar para convertir el valor numérico de prioridad a texto
    def get_priority_name(priority_value):
        if not priority_value:
            return "Sin prioridad"
        
        priority_map = {
            1: "Urgente",
            2: "Alta",
            3: "Normal",
            4: "Baja"
        }
        
        if isinstance(priority_value, dict) and 'priority' in priority_value:
            value = priority_value.get('priority')
            return priority_map.get(value, "Sin prioridad")
        
        return priority_map.get(priority_value, "Sin prioridad")


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
                metadata = raw_metadata.get('metadata', {})  # Extraer el diccionario correcto

                name = metadata.get('name', 'Sin nombre')
                path = metadata.get('path_display', 'Sin ruta')
                tag = metadata.get('.tag', '')  # Puede ser "file" o "folder"
                
                # 🔍 **Extraer tamaño y fecha de modificación**
                size = metadata.get('size', None)  # Tamaño del archivo
                modified = metadata.get('server_modified', None)  # Fecha de modificación

                if search_type == "folder" and tag == "folder":
                    # 📂 Si es una carpeta, listar su contenido
                    list_folder_url = "https://api.dropboxapi.com/2/files/list_folder"
                    list_folder_headers = {
                        'Authorization': f"Bearer {dropbox_token}",
                        'Content-Type': 'application/json'
                    }
                    list_folder_params = {"path": path}

                    try:
                        list_response = requests.post(list_folder_url, headers=list_folder_headers, json=list_folder_params)
                        list_response.raise_for_status()
                        folder_contents = list_response.json().get('entries', [])

                        for item in folder_contents:
                            if item['.tag'] == 'file':  # Solo archivos
                                file_link = generate_dropbox_link(dropbox_token, item['path_display'])
                                filtered_results.append({
                                    'name': item['name'],
                                    'path': item['path_display'],
                                    'type': 'file',
                                    'download_link': file_link,
                                    'size': item.get('size'),  
                                    'modified': item.get('server_modified')  
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
                            'download_link': file_link,
                            'size': size,
                            'modified': modified
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
                query = query[len("carpeta:"):]  # Solo queda el nombre de la carpeta

            folder_query = f"name = '{query}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            folder_params = {"q": folder_query, "fields": "files(id, name)"}
            folder_response = requests.get("https://www.googleapis.com/drive/v3/files", headers=headers, params=folder_params)
            folder_data = folder_response.json()
            if "files" not in folder_data or not folder_data["files"]:
                return jsonify([])  # No se encontraron carpetas

            folder_id = folder_data["files"][0]["id"]
            
            # Buscar archivos dentro de la carpeta
            files_query = f"'{folder_id}' in parents and trashed = false"
            files_params = {
                "q": files_query,
                "fields": "files(id, name, mimeType, webViewLink, size, modifiedTime, owners(displayName, emailAddress))"
            }
            files_response = requests.get("https://www.googleapis.com/drive/v3/files", headers=headers, params=files_params)
            files_data = files_response.json()

            search_results = []
            for file in files_data.get("files", []):
                search_results.append({
                    "title": file.get("name", "Desconocido"),
                    "type": file.get("mimeType", "Desconocido"),
                    "url": file.get("webViewLink", "No disponible"),
                    "size": file.get("size", "Desconocido"),
                    "modified": file.get("modifiedTime", "Desconocido"),
                    "owner": file.get("owners", [{}])[0].get("displayName", "Desconocido"),
                    "owner_email": file.get("owners", [{}])[0].get("emailAddress", "Desconocido")
                })
            
            return jsonify(search_results)
        
        except requests.RequestException as e:
            return jsonify({"error": "Error en la solicitud a Google Drive", "details": str(e)}), 500
        except Exception as e:
            return jsonify({"error": "Error inesperado", "details": str(e)}), 500
        
    return {
        "search_gmail": search_gmail,
        "search_teams": search_teams,
        "search_google_drive": search_google_drive,
        "search_notion": search_notion,
        "search_slack": search_slack,
        "search_hubspot": search_hubspot,
        "search_clickup": search_clickup,
        "search_asana": search_asana,
        "search_outlook": search_outlook,
        "search_onedrive": search_onedrive,
        "search_dropbox": search_dropbox,
    }
