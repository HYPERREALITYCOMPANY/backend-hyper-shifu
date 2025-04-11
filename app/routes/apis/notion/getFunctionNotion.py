from datetime import datetime
import requests
import json

def handle_get_request(accion, solicitud, email, user):
    if not user:
        return {"solicitud": "GET", "result": {"error": "No te encontré en la base de datos, ¿estás seguro de que estás registrado?"}}, 404

    notion_integration = user.get('integrations', {}).get('Notion', None)
    if not notion_integration or not notion_integration.get('token'):
        return {"solicitud": "GET", "result": {"error": "No tengo tu token de Notion, ¿puedes darme permisos nuevamente?"}}, 400
    notion_token = notion_integration.get('token')

    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": "2022-06-28",  # Versión estable de la API de Notion
        "Content-Type": "application/json"
    }

    if not accion:
        return {"solicitud": "GET", "result": {"error": "No me indicaste qué hacer, ¿qué te gustaría buscar en Notion?"}}, 400
    if not solicitud:
        return {"solicitud": "GET", "result": {"error": "Necesito más detalles para buscar, ¿qué quieres encontrar en Notion?"}}, 400

    solicitud = solicitud.lower()

    try:
        if accion == "buscar":
            # Buscar páginas en una base de datos
            if "páginas" in solicitud or "paginas" in solicitud:
                if "de" in solicitud or "en" in solicitud:
                    db_name = solicitud.split("de")[-1].strip() if "de" in solicitud else solicitud.split("en")[-1].strip()
                    if not db_name:
                        return {"solicitud": "GET", "result": {"message": "📘 ¡Falta algo! Dime de qué base de datos buscar las páginas 🚀"}}, 200
                    
                    # Buscar bases de datos del usuario
                    url = "https://api.notion.com/v1/databases"
                    response = requests.get(url, headers=headers)
                    response.raise_for_status()
                    databases = response.json().get("results", [])
                    db_id = None
                    for db in databases:
                        if db_name.lower() in db["title"][0]["text"]["content"].lower():
                            db_id = db["id"]
                            break
                    if not db_id:
                        return {"solicitud": "GET", "result": {"message": f"📘 No encontré una base de datos llamada '{db_name}'."}}, 200

                    # Consultar páginas en la base de datos
                    url = f"https://api.notion.com/v1/databases/{db_id}/query"
                    response = requests.post(url, headers=headers, json={})
                    response.raise_for_status()
                    pages = response.json().get("results", [])
                    if not pages:
                        return {"solicitud": "GET", "result": {"message": f"📘 No hay páginas en la base de datos '{db_name}'."}}, 200

                    results = [
                        {
                            "title": page["properties"].get("Name", {}).get("title", [{}])[0].get("text", {}).get("content", "Sin título"),
                            "id": page["id"],
                            "url": page["url"]
                        } for page in pages[:5]  # Limitamos a 5 resultados
                    ]
                    return {"solicitud": "GET", "result": {"message": f"📘 ¡Encontré {len(results)} páginas en la base de datos '{db_name}'! 🚀", "data": results}}, 200

            # Buscar todas las bases de datos
            elif "bases de datos" in solicitud or "databases" in solicitud:
                url = "https://api.notion.com/v1/databases"
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                databases = response.json().get("results", [])
                if not databases:
                    return {"solicitud": "GET", "result": {"message": "📘 No encontré bases de datos en tu Notion."}}, 200

                results = [
                    {
                        "title": db["title"][0]["text"]["content"],
                        "id": db["id"],
                        "url": db["url"]
                    } for db in databases[:5]  # Limitamos a 5 resultados
                ]
                return {"solicitud": "GET", "result": {"message": f"📘 ¡Aquí tienes {len(results)} bases de datos de tu Notion! 🚀", "data": results}}, 200

            else:
                return {"solicitud": "GET", "result": {"message": "📘 ¡Falta algo! Dime qué buscar, como 'páginas de X' o 'bases de datos' 🚀"}}, 200

        else:
            return {"solicitud": "GET", "result": {"error": f"No entendí '{accion}', ¿puedes usar 'buscar' para buscar algo en Notion?"}}, 400

    except requests.RequestException as e:
        return {"solicitud": "GET", "result": {"error": f"Lo siento, hubo un problema al conectar con Notion: {str(e)}"}}, 500
    except Exception as e:
        return {"solicitud": "GET", "result": {"error": f"Ups, algo salió mal inesperadamente: {str(e)}"}}, 500