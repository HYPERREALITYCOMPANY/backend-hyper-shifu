import requests
import json
from datetime import datetime
import openai
from config import Config
openai.api_key = Config.CHAT_API_KEY

def analyze_notion_request(solicitud):
    """Analiza la solicitud con IA para extraer datos de creación en Notion."""
    prompt = f"""
    Eres un asistente inteligente que analiza solicitudes para crear contenido en Notion. Dada la solicitud: "{solicitud}", identifica:
    - Acción (ej. "crear página", "crear base de datos")
    - Destino (nombre de la base de datos o "nueva" si es una base de datos nueva)
    - Título (nombre de la página o base de datos)
    - Contenido (texto o propiedades adicionales, si se mencionan)
    
    Devuelve un JSON con "accion", "destino", "titulo", "contenido". Usa null si algo no está claro o falta.
    Ejemplos:
    - "Crear página en Proyectos con título Reunión" → {{"accion": "crear página", "destino": "Proyectos", "titulo": "Reunión", "contenido": null}}
    - "Crear base de datos nueva llamada Tareas" → {{"accion": "crear base de datos", "destino": "nueva", "titulo": "Tareas", "contenido": null}}
    - "Crear página" → {{"accion": "crear página", "destino": null, "titulo": null, "contenido": null}}
    """
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150
        )
        return json.loads(response.choices[0].message.content.strip())
    except Exception as e:
        return {"accion": None, "destino": None, "titulo": None, "contenido": None, "error": str(e)}

def get_task_id_notion(name, token, database_id="YOUR_DATABASE_ID"):
    """Obtiene el ID de una tarea en Notion por su nombre."""
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    data = {
        "filter": {
            "property": "Name",
            "rich_text": {
                "equals": name
            }
        }
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        results = response.json().get('results', [])
        if results:
            return results[0]["id"]
    return None

def handle_post_request(accion, solicitud, email, user):
    if not user:
        return {"solicitud": "POST", "result": {"error": "No te encontré en la base de datos, ¿estás seguro de que estás registrado?"}}, 404

    notion_integration = user.get('integrations', {}).get('Notion', None)
    if not notion_integration or not notion_integration.get('token'):
        return {"solicitud": "POST", "result": {"error": "No tengo tu token de Notion, ¿puedes darme permisos nuevamente?"}}, 400
    notion_token = notion_integration.get('token')

    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }

    if not accion:
        return {"solicitud": "POST", "result": {"error": "No me indicaste qué hacer, ¿en qué puedo ayudarte con Notion?"}}, 400
    if not solicitud:
        return {"solicitud": "POST", "result": {"error": "Necesito más detalles para proceder, ¿qué te gustaría hacer en Notion?"}}, 400

    solicitud = solicitud.lower()
    try:
        if accion == "crear":
            analysis = analyze_notion_request(solicitud)
            action_type = analysis.get("accion")
            destino = analysis.get("destino")
            titulo = analysis.get("titulo")
            contenido = analysis.get("contenido")

            if not action_type:
                return {"solicitud": "POST", "result": {"message": "📘 ¡Falta algo! Dime qué crear (ej. página o base de datos) 🚀"}}, 200

            # Crear página en una base de datos existente
            if "página" in action_type or "pagina" in action_type:
                if not destino:
                    return {"solicitud": "POST", "result": {"message": "📘 ¡Falta algo! Dime en qué base de datos crear la página 🚀"}}, 200
                if not titulo:
                    return {"solicitud": "POST", "result": {"message": "📘 ¡Falta algo! Dime el título de la página 🚀"}}, 200

                # Buscar la base de datos
                url = "https://api.notion.com/v1/databases"
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                databases = response.json().get("results", [])
                db_id = None
                for db in databases:
                    if destino.lower() in db["title"][0]["text"]["content"].lower():
                        db_id = db["id"]
                        break
                if not db_id:
                    return {"solicitud": "POST", "result": {"message": f"📘 No encontré una base de datos llamada '{destino}'."}}, 200

                # Crear la página
                url = "https://api.notion.com/v1/pages"
                payload = {
                    "parent": {"database_id": db_id},
                    "properties": {
                        "Name": {
                            "title": [{"text": {"content": titulo}}]
                        }
                    }
                }
                if contenido:
                    payload["children"] = [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": contenido}}]}}]

                response = requests.post(url, headers=headers, json=payload)
                response.raise_for_status()
                page = response.json()
                return {"solicitud": "POST", "result": {"message": f"📘 ¡Página '{titulo}' creada en la base de datos '{destino}'! 🚀\nEnlace: {page['url']}"}}, 200

            # Crear una nueva base de datos
            elif "base de datos" in action_type:
                if not titulo:
                    return {"solicitud": "POST", "result": {"message": "📘 ¡Falta algo! Dime el nombre de la base de datos 🚀"}}, 200

                url = "https://api.notion.com/v1/databases"
                payload = {
                    "parent": {"type": "page_id", "page_id": notion_integration.get("parent_page_id", "your-root-page-id")},
                    "title": [{"type": "text", "text": {"content": titulo}}],
                    "properties": {
                        "Name": {"title": {}},
                        "Description": {"rich_text": {}}
                    }
                }
                response = requests.post(url, headers=headers, json=payload)
                response.raise_for_status()
                db = response.json()
                return {"solicitud": "POST", "result": {"message": f"📘 ¡Base de datos '{titulo}' creada! 🚀\nEnlace: {db['url']}"}}, 200

            # Marcar tarea como completada
            elif "marca como completada" in solicitud or "completar tarea" in solicitud:
                task_name = None
                if "tarea" in solicitud:
                    task_name = solicitud.split("tarea")[-1].strip()
                else:
                    task_name = solicitud.split("completada")[-1].strip()

                if not task_name:
                    return {"solicitud": "POST", "result": {"message": "📘 ¡Falta algo! Dime el nombre de la tarea que quieres completar 🚀"}}, 200

                # Buscar la base de datos de tareas (se asume que el usuario tiene una predeterminada o se pasa como destino)
                db_id = None
                if destino and destino != "nueva":
                    url = "https://api.notion.com/v1/databases"
                    response = requests.get(url, headers=headers)
                    response.raise_for_status()
                    databases = response.json().get("results", [])
                    for db in databases:
                        if destino.lower() in db["title"][0]["text"]["content"].lower():
                            db_id = db["id"]
                            break
                    if not db_id:
                        return {"solicitud": "POST", "result": {"message": f"📘 No encontré una base de datos llamada '{destino}'."}}, 200
                else:
                    db_id = "YOUR_DATABASE_ID"  # ID predeterminado si no se especifica destino

                task_id = get_task_id_notion(task_name, notion_token, db_id)
                if not task_id:
                    return {"solicitud": "POST", "result": {"message": f"📘 No encontré la tarea '{task_name}' en Notion."}}, 200

                url = f"https://api.notion.com/v1/pages/{task_id}"
                payload = {
                    "properties": {
                        "Status": {
                            "select": {
                                "name": "Completed"
                            }
                        }
                    }
                }
                response = requests.patch(url, headers=headers, json=payload)
                response.raise_for_status()
                return {"solicitud": "POST", "result": {"message": f"📘 ¡Tarea '{task_name}' marcada como completada! 🚀"}}, 200

            else:
                return {"solicitud": "POST", "result": {"message": "📘 ¡Falta algo! Dime si quieres crear una página, base de datos o completar una tarea 🚀"}}, 200

        else:
            return {"solicitud": "POST", "result": {"error": f"No entendí '{accion}', ¿puedes usar 'crear' para hacer algo en Notion?"}}, 400

    except requests.RequestException as e:
        return {"solicitud": "POST", "result": {"error": f"Lo siento, hubo un problema al conectar con Notion: {str(e)}"}}, 500
    except Exception as e:
        return {"solicitud": "POST", "result": {"error": f"Ups, algo salió mal inesperadamente: {str(e)}"}}, 500