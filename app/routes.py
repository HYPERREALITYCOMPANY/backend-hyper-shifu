from flask import redirect, Blueprint, url_for, session, request, jsonify
import requests
from requests_oauthlib import OAuth2Session
from config import Config
from urllib.parse import urlencode
import base64 
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import unicodedata
import re
import json
import os
import quopri
import openai
from app.services.gmail import auth_gmail as service_auth_gmail
from app.services.gmail import auth_gmail_callback as service_auth_callback
from app.services.notion import notion_auth as service_auth_notion
from app.services.notion import notion_callback as service_auth_notion_callback

openai.api_key=Config.CHAT_API_KEY

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
def setup_routes(app):
    stateSlack = ""
    notion_bp = Blueprint('notion', __name__)
    @app.route('/')
    def home():
        return ("Este es el backend del proyecto!!")

    @app.route('/auth/gmail')
    def auth_gmail():
        return service_auth_gmail()

    @app.route('/auth/gmail/callback')
    def auth_gmail_callback():
       return service_auth_callback()
    
    @app.route('/auth/notion')
    def auth_notion():
        return service_auth_notion()

    @app.route('/notion/callback')
    def auth_notion_callback():
        return service_auth_notion_callback()
    
    @app.route('/auth/slack')
    def auth_slack():
        scopes = ["channels:read", "chat:write", "users:read"]
        slack = OAuth2Session(Config.SLACK_CLIENT_ID, redirect_uri='https://jk6rq3rx-5000.use2.devtunnels.ms/auth/slack/callback', scope=scopes)
        authorization_url, state = slack.authorization_url('https://slack.com/oauth/v2/authorize')
        session['oauth_state'] = stateSlack   # Almacena el estado en la sesión
        print(f"Estado almacenado en la sesión: {state}")  # Debug
        return redirect(authorization_url)

    @app.route('/auth/slack/callback')
    def auth_slack_callback():
        scopes = ["channels:read", "chat:write", "users:read", "search:read"]
        slack = OAuth2Session(Config.SLACK_CLIENT_ID, state=stateSlack)
        token = slack.fetch_token('https://slack.com/api/oauth.v2.access', 
                                client_secret=Config.SLACK_CLIENT_SECRET, 
                                scope = scopes,
                                authorization_response=request.url)
        session['slack_token'] = token
        return jsonify(token)
    
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

    @app.route('/askIa', methods=['GET'])
    def ask():
        query = request.args.get('query')
        search_results = search_all()
        print(search_results.response)
        if not query:
            return jsonify({"error": "No se proporcionó una consulta de búsqueda"}), 400
        if not search_results:
            return jsonify({"error": "No se proporcionaron resultados de búsqueda"}), 400
        try:
            if isinstance(search_results.response, list) and isinstance(search_results.response[0], bytes):
                search_results_json = json.loads(search_results.response[0].decode('utf-8'))
            elif isinstance(search_results.response, str):
                search_results_json = json.loads(search_results.response)
            else:
                return jsonify({"error": "Formato de respuesta no soportado"}), 500
        except json.JSONDecodeError:
            return jsonify({"error": "La respuesta de búsqueda no es un JSON válido"}), 500

        prompt = generate_prompt(query, search_results_json)


        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Eres un asistente útil."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=4096
        )

        ia_response = response.choices[0].message['content'].strip()

        return jsonify({
            "response": ia_response
        })


    def generate_prompt(query, search_results):
        gmail_results = "\n".join([
            f"De: {email['from']}\nFecha: {email['date']}\nAsunto: {email['subject']}\nCuerpo: {email['body']}\n"
            for email in search_results.get('gmail', []) if isinstance(email, dict)
        ])

        slack_results = "\n".join([
            f"En el canal '{msg['channel']}', el usuario '{msg['user']}' dijo:\n'{msg['text']}'\nFecha: {msg['ts']}\n"
            for msg in search_results.get('slack', []) if isinstance(msg, dict)
        ])

        notion_results = "\n".join([
            f"Página ID: {page['id']}\nCreada el: {page['created_time']}\nÚltima editada: {page['last_edited_time']}\n"
            f"URL: {page['url']}\nPropiedades: {json.dumps(page['properties'], ensure_ascii=False)}\n"
            for page in search_results.get('notion', []) if isinstance(page, dict)
        ])

        prompt = f"""Resultados de búsqueda para la consulta: "{query}"

        ### Gmail:
        {gmail_results if gmail_results else "No se encontraron correos relacionados en Gmail."}

        ### Notion:
        {notion_results if notion_results else "No se encontraron correos relacionados en Notion."}

        ### Slack:
        {slack_results if slack_results else "No se encontraron correos relacionados en Slack."}

        
        Based on this information, please provide a detailed and extensive response to the query. Make sure to explain each result in depth. For example:
        - Describe the body and subject of the email, what was discussed and its relevance, as well as the name of the user who sent the email, search by keywords, including links and any file types.
        - For Slack, comment on the tone of the message and its importance.
        - For Notion, provide a summary of the key information contained in the properties.

        Also, include exact information found from emails they sent, message bodies, which channel or group they were sent in, and important dates, both explicit and when the email was created or arrived. Please do all this in markdown or in an organized way so that it is more readable, as well as values ​​that are not legible such as accents or emojis, keep in mind that dates are only year/month/day, split the answer with enters.
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
    @app.route('/search/all', methods=['GET'])
    def search_all():
        query = request.args.get('query')
        if not query:
            return jsonify({"error": "No se proporcionó una consulta de búsqueda"}), 400
        two_weeks_ago = datetime.now() - timedelta(weeks=2)
        two_weeks_ago_str = two_weeks_ago.strftime('%Y/%m/%d')
        results = {
            "gmail": [],
            "slack": [],
            "notion": []
        }

        # Búsqueda en Gmail
        gmail_token = session.get('gmail_token')
        if gmail_token:
            headers = {'Authorization': f'Bearer {gmail_token["access_token"]}'}
            params = {'q': f"{query} after:{two_weeks_ago_str}"}
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
        slack_token = session.get('slack_token')
        if slack_token:
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
        notion_token = session.get('access_token')
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
                            # Maneja el caso en que property_value no sea un diccionario
                            page_info["properties"][property_name] = str(property_value)  
                    results['notion'].append(page_info)
            else:
                results['notion'] = {"error": "Error al buscar en Notion", "details": notion_response.json()}

        else:
            results['notion'] = {"error": "Sesión no ingresada en Notion"}

        return jsonify(results)