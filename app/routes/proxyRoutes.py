from flask import request, jsonify
import requests
from urllib.parse import urlencode
import base64 
def setup_proxy_routes(app, mongo):
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
                    "access_token": data["access_token"],# Retorna el tiempo de expiración si está disponible
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
    @app.route('/notion-proxy', methods=['POST'])
    def notion_proxy():
        try:
            data = request.json
            client_id = data.get('client_id')
            client_secret = data.get('client_secret')
            client_credentials = f"{client_id}:{client_secret}"
            encoded_credentials = base64.b64encode(client_credentials.encode()).decode()

            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {encoded_credentials}",
                "Notion-Version": "2022-06-28",
            }

            token_data = {
                "grant_type": "authorization_code",
                "code": data.get("code"),
                "redirect_uri": data.get("redirect_uri"),
            }

            response = requests.post("https://api.notion.com/v1/oauth/token", data=token_data, headers=headers)

            return jsonify(response.json()), response.status_code

        except Exception as e:
            return jsonify({"error": str(e)}), 500
        
    @app.route('/hubspot-proxy', methods=['POST'])
    def hubspot_proxy():
        try:
            data = request.json
            token_url = 'https://api.hubapi.com/oauth/v1/token'
            payload = {
                'grant_type': 'authorization_code',
                'client_id': data.get('client_id'),
                'client_secret': data.get('client_secret'),
                'redirect_uri': data.get('redirect_uri'), 
                'code': data.get('code')
            }

            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
            }
            response = requests.post(token_url, data=urlencode(payload), headers=headers)

            if response.status_code == 200:
                token_data = response.json()
                return jsonify(token_data), 200
            else:
                return jsonify({'error': 'HubSpot API error', 'details': response.json()}), response.status_code

        except Exception as e:
            return jsonify({"error": str(e)}), 500