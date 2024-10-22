from flask import redirect, Blueprint, url_for, session, request, jsonify
import requests
from requests_oauthlib import OAuth2Session
from config import Config
from urllib.parse import urlencode
import base64 
import unicodedata
import re
import os
import quopri
from app.services.gmail import auth_gmail as service_auth_gmail
from app.services.gmail import auth_gmail_callback as service_auth_callback
from app.services.notion import notion_auth as service_auth_notion
from app.services.notion import notion_callback as service_auth_notion_callback

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
def setup_routes(app):
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
        slack = OAuth2Session(Config.SLACK_CLIENT_ID)
        authorization_url, state = slack.authorization_url('https://slack.com/oauth/authorize')
        session['oauth_state'] = state
        return redirect(authorization_url)

    @app.route('/auth/slack/callback')
    def auth_slack_callback():
        slack = OAuth2Session(Config.SLACK_CLIENT_ID, state=session['oauth_state'])
        token = slack.fetch_token('https://slack.com/api/oauth.access', 
                                  client_secret=Config.SLACK_CLIENT_SECRET, 
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



    @app.route('/search/all', methods=['GET'])
    def search_all():
        query = request.args.get('query')
        if not query:
            return jsonify({"error": "No se proporcionó una consulta de búsqueda"}), 400
        
        results = {}

        gmail_token = session.get('gmail_token')
        if gmail_token:
            headers = {'Authorization': f'Bearer {gmail_token["access_token"]}'}
            params = {'q': query}
            gmail_response = requests.get('https://www.googleapis.com/gmail/v1/users/me/messages', 
                                        headers=headers, params=params)
            if gmail_response.status_code == 200:
                results['gmail'] = gmail_response.json()
            else:
                results['gmail'] = {"error": "Error al buscar en Gmail", "details": gmail_response.json()}

        slack_token = session.get('slack_token')
        if slack_token:
            headers = {'Authorization': f'Bearer {slack_token["access_token"]}'}
            slack_response = requests.get(f'https://slack.com/api/search.messages?query={query}', 
                                        headers=headers)
            if slack_response.status_code == 200:
                results['slack'] = slack_response.json()
            else:
                results['slack'] = {"error": "Error al buscar en Slack", "details": slack_response.json()}

        return jsonify(results)

