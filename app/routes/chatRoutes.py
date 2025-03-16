from flask import request, jsonify
from datetime import datetime
from config import Config
from datetime import datetime
import re
import json
import openai
from app.routes.searchRoutes import setup_routes_searchs
from app.routes.postRoutes import setup_post_routes
from app.routes.rulesRoutes import setup_rules_routes
from flask_caching import Cache
from app.utils.utils import get_user_from_db
openai.api_key=Config.CHAT_API_KEY
def setup_routes_chats(app, mongo, cache):
    cache = Cache(app)
    functions = setup_routes_searchs(app, mongo, cache)
    functionsPost = setup_post_routes(app, mongo, cache)
    functions2 = setup_rules_routes(app, mongo, cache)
    search_gmail = functions["search_gmail"]
    search_outlook = functions["search_outlook"]
    search_notion = functions["search_notion"]
    search_clickup = functions["search_clickup"]
    search_hubspot = functions["search_hubspot"]
    search_teams = functions["search_teams"]
    search_slack = functions["search_slack"]
    search_dropbox = functions["search_dropbox"]
    search_asana = functions["search_asana"]
    search_onedrive = functions["search_onedrive"]
    search_google_drive = functions["search_google_drive"]
    post_to_gmail = functionsPost["post_to_gmail"]
    post_to_notion = functionsPost["post_to_notion"]
    post_to_outlook = functionsPost["post_to_outlook"]
    post_to_clickup = functionsPost["post_to_clickup"]
    post_to_asana = functionsPost["post_to_asana"]
    post_to_dropbox = functionsPost["post_to_dropbox"]
    post_to_googledrive = functionsPost["post_to_googledrive"]
    post_to_onedrive = functionsPost["post_to_onedrive"]

    functionsAuto = {
        "post_auto_gmail": functions2["post_auto_gmail"],
        "post_auto_notion": functions2["post_auto_notion"],
        "post_auto_clickup": functions2["post_auto_clickup"],
        "post_auto_asana": functions2["post_auto_asana"],
        "post_auto_dropbox": functions2["post_auto_dropbox"],
        "post_auto_googledrive": functions2["post_auto_googledrive"],
        "post_auto_outlook": functions2["post_auto_outlook"],
        "post_auto_hubspot": functions2["post_auto_hubspot"],
        "post_auto_teams": functions2["post_auto_teams"],
        "post_auto_slack": functions2["post_auto_slack"],
        "post_auto_onedrive": functions2["post_auto_onedrive"]
    }
    post_to_onedrive = functionsPost["post_to_onedrive"]
    global last_searchs

    def generate_prompt(query, search_results):
        # Extraer solo la información relevante de cada fuente
        results = {}
        def format_size(size_in_bytes):
            if size_in_bytes is None:
                return "Desconocido"
            size_in_bytes = int(size_in_bytes)
            if size_in_bytes < 1024:
                return f"{size_in_bytes} B"
            elif size_in_bytes < 1024**2:
                return f"{size_in_bytes / 1024:.2f} KB"
            elif size_in_bytes < 1024**3:
                return f"{size_in_bytes / (1024**2):.2f} MB"
            else:
                return f"{size_in_bytes / (1024**3):.2f} GB"

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

        # ClickUp Results (extraer información relevante)
        clickup_results = "\n".join([
            f"Tarea: {task.get('task_name', 'Sin nombre')} | "
            f"Estado: {task.get('status', 'Sin estado')} | "
            f"Prioridad: {task.get('priority', 'Sin prioridad')} | "
            f"Asignado a: {', '.join(task.get('assignees', ['Sin asignar']))} | "
            f"Fecha de vencimiento: {task.get('due_date', 'Sin fecha')} | "
            f"Lista: {task.get('list', 'Sin lista')} | "
            f"URL: {task.get('url', 'Sin URL')}"
            for task in search_results.get('clickup', []) if isinstance(task, dict)
        ]) or "No se encontraron tareas relacionadas en ClickUp."

        # Dropbox Results
        dropbox_results = "\n".join([
            f"Archivo: {file.get('name', 'Sin nombre')} | Tamaño: {format_size(file.get('size'))} | Fecha de modificación: {file.get('modified', 'Sin fecha')}"
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

        # Google Drive Results
        google_drive_results = "\n".join([
            f"Archivo: {file.get('title', 'Sin nombre')} | "
            f"Tamaño: {format_size(file.get('size'))} | "
            f"Modificado: {file.get('modified', 'Sin fecha')} | "
            f"Propietario: {file.get('owner', 'Desconocido')} ({file.get('owner_email', 'Sin correo')})"
            for file in search_results.get('googledrive', []) if isinstance(file, dict)
        ]) or "No se encontraron archivos relacionados en Google Drive."

        # Crear el prompt final con instrucciones adicionales para filtrar la información específica
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

    Responde de forma humana, concisa y en párrafo:
    Quiero que respondas a la query enviada por el usuario utilizando únicamente la información específica que se encuentra en cada API, descartando datos generales o irrelevantes. Es decir, si la query solicita detalles puntuales (por ejemplo, el estado de un proyecto con un nombre determinado, o información de un correo específico en Gmail), debes extraer y usar únicamente los registros que correspondan a esa solicitud y omitir el resto.
    - Si no existe información en ninguna API, contesta de manera amable sugiriendo mejorar el prompt o especificar mejor lo que se desea encontrar.
    - Si existe información en algunas APIs y en otras no, responde únicamente con los datos disponibles.
    - En el caso de HubSpot, cuando se soliciten contactos de una compañía y el campo 'compañía' esté vacío, valida que el nombre de la empresa pueda obtenerse del dominio del correo electrónico (todo lo que sigue después de '@'). Por ejemplo, si el dominio es 'empresa.com', considera que la empresa es 'empresa'. No incluyas registros irrelevantes; muestra solo los contactos relacionados con el dominio o con el nombre de la compañía.
    - Recuerda utilizar la información de los bodys de correos, fechas y remitentes (De:) para filtrar y responder de manera precisa.

    Necesito que tu respuesta sea concisa, siguiendo el estilo de "Suggested Answers" de Guru, e incluye emojis para hacer la interacción más amigable. No incluyas la palabra 'Respuesta:'; contesta de forma natural y sin enlaces.
    Analiza cuidadosamente la información proporcionada; si consideras que la query no puede responderse de manera amena o precisa, sugiere amablemente que el usuario mejore su prompt o especifique lo que desea encontrar.
    """
        print(prompt)
        return prompt


    @app.route("/api/chatAi", methods=["POST"])
    def apiChat():
        print("Hola")
        data = request.get_json()
        user_messages = data.get("messages", [])
        last_ai_response = ""
        hoy = datetime.today().strftime('%Y-%m-%d')
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
                f"   - Si es una solicitud POST simple (acción única), responde con 'Es una solicitud POST'.\n"
                f"   - Si es una solicitud POST automatizada o quemada (para ejecutar siempre cuando ocurra algo), responde con 'Es una solicitud automatizada'.\n"
                f"   - Si es una solicitud que menciona algo sobre una conversación o respuesta anterior (ejemplo: 'de lo que hablamos antes', 'en la conversación anterior', 'acerca del mensaje previo', 'respuesta anterior', 'de que trataba', etc), responde con 'Se refiere a la respuesta anterior'.\n\n"
                
                f"REGLAS CRÍTICAS PARA CLASIFICACIÓN DE SOLICITUDES:\n"
                f"- SOLICITUDES GET: Cuando el usuario usa verbos como 'Mándame', 'Pásame', 'Envíame', 'Muéstrame', 'Busca', 'Encuentra', 'Dame', 'Dime', 'Quiero ver' dirigidos a SÍ MISMO.\n"
                f"- SOLICITUDES POST SIMPLE: Verbos de acción hacia sistemas o terceros: 'Crear', 'Enviar (a otra persona)', 'Eliminar', 'Mover', 'Actualizar', 'Editar', 'Agregar'.\n"
                f"- SOLICITUDES POST AUTOMATIZADAS: Frases que indican automatización: 'Cada vez que', 'Siempre que', 'Cuando ocurra', 'Automáticamente', contienen una condición Y una acción.\n\n"
                
                f"ESPECIFICAMENTE SI Y SOLO SI LA SOLICITUD ES TIPO GET:\n"
                f"En caso de ser una solicitud GET, desglosa las partes relevantes para cada API (Gmail, Notion, Slack, HubSpot, Outlook, ClickUp, Dropbox, Asana, Google Drive, OneDrive, Teams).\n"
                f"Asegúrate de lo siguiente:\n"
                f"- No coloques fechas en ninguna query, ni after ni before'.\n"
                f"- Si se menciona un nombre propio (detectado si hay una combinación de nombre y apellido), responde 'from: <nombre completo>'.\n"
                f"- Si se menciona un correo electrónico, responde 'from: <correo mencionado>'.\n"
                f"- Usa la misma query de Gmail también para Outlook.\n"
                f"- Usa la misma query de Notion en Asana y Clickup.\n"
                f"- En HubSpot, identifica qué tipo de objeto busca el usuario (por ejemplo: contacto, compañía, negocio, empresa, tarea, etc.) y ajusta la query de forma precisa. "
                f"El valor debe seguir esta estructura: \"<tipo de objeto> <query>\", como por ejemplo \"contacto osuna\" o \"compañía osuna\".\n"
                f"- Para Slack, adapta la query de Gmail pero hazla más informal y directa para contextos de mensajería.\n"
                f"- En ClickUp, la consulta debe ajustarse específicamente si el usuario menciona tareas, proyectos, estados o fechas.\n"
                f"  Si menciona 'tarea de <nombre>' o 'estado de la tarea <nombre>', responde: 'tarea <nombre>'.\n"
                f"  Si menciona 'proyecto <nombre>' o 'estado del proyecto <nombre>', responde: 'proyecto <nombre>'.\n"
                f"  Si solo menciona 'estado' sin contexto adicional, devuelve 'estado de tareas' para obtener una visión general.\n"
                f"- Genera una consulta para Dropbox, OneDrive y Google Drive basada en el mensaje del usuario.\n"
                f"  Si menciona un archivo: \"archivo:<nombre>\"\n"
                f"  Si menciona una carpeta: \"carpeta:<nombre>\"\n"
                f"  Si menciona un archivo dentro de una carpeta: \"archivo:<nombre> en carpeta:<ubicación>\"\n"
                f"- En Asana, si menciona un proyecto o tarea, ajusta la consulta a ese nombre específico.\n"
                f"- En Teams, ajusta la consulta según lo que menciona el usuario:\n"
                f"  Si menciona un canal: usa \"channel:<nombre del canal>\".\n"
                f"  Si el usuario menciona que está 'hablando con' alguien: usa \"conversation with:<nombre> <palabras clave>\".\n"
                f"  Si menciona un tema específico sin un contacto: usa \"message:<palabras clave>\".\n"
                f"  SI EL USUARIO MENCIONA EXPLICITAMENTE 'TEAMS' O 'MICROSOFT TEAMS' HAZ LA QUERY.\n\n"
                
                f"Estructura del JSON para GET:\n"
                f"{{\n"
                f"    \"gmail\": \"<query para Gmail> Se conciso y evita palabras de solicitud y solo pon la query y evita los is:unread\",\n"
                f"    \"notion\": \"<query para Notion o 'N/A' si no aplica>\",\n"
                f"    \"slack\": \"<query para Slack o 'N/A' si no aplica>\",\n"
                f"    \"hubspot\": \"<query para HubSpot o 'N/A' si no aplica>\",\n"
                f"    \"outlook\": \"<query para Outlook, misma que Gmail>\",\n"
                f"    \"clickup\": \"<query para ClickUp, o 'N/A' si no aplica>\",\n"
                f"    \"dropbox\": \"<query para Dropbox o 'N/A' si no aplica>\",\n"
                f"    \"asana\": \"<query para Asana o 'N/A' si no aplica>\",\n"
                f"    \"googledrive\": \"<query para Google Drive o 'N/A' si no aplica>\",\n"
                f"    \"onedrive\": \"<query para OneDrive o 'N/A' si no aplica>\",\n"
                f"    \"teams\": \"<query para Teams o 'N/A' si no aplica>\"\n"
                f"}}\n\n"
                
                f"ESPECIFICAMENTE SI Y SOLO SI LA SOLICITUD ES TIPO POST SIMPLE:\n"
                f"OBLIGATORIO: Responde con 'Es una solicitud POST' seguido del JSON de abajo\n"
                f"Detecta las acciones solicitadas por el usuario y genera la consulta para la API correspondiente:\n"
                f"1. **Crear o Agregar elementos** (acciones como 'crear', 'agregar', 'añadir', 'subir', 'agendar').\n"
                f"2. **Modificar o Editar elementos** (acciones como 'editar', 'modificar', 'actualizar', 'mover').\n"
                f"3. **Eliminar elementos** (acciones como 'eliminar', 'borrar', 'suprimir').\n"
                f"   - Si se menciona 'eliminar correos', debe enviarse a Gmail y Outlook.\n"
                f"   - Si se menciona 'elimina la cita' o 'elimina la reunion' debe enviarse a Gmail.\n"
                f"4. **Mover elementos** (acciones como 'mover', 'trasladar', 'archivar', 'poner en spam').\n"
                f"5. **Enviar o compartir** (acciones como 'enviar', 'compartir', 'enviar por correo').\n"
                f"   - Para correos, genera la query en formato: 'enviar correo a [destinatario] con asunto: [asunto] y cuerpo: [cuerpo]'.\n"
                f"6. **Agendar o Programar** (acciones como 'agendar', 'programar').\n"
                f"7. **Crear un borrador** (acciones como 'crear borrador', 'guardar borrador').\n"
                f"8. **Compartir archivos o carpetas** (acciones como 'compartir archivo', 'compartir carpeta').\n\n"
                f"""- Si la solicitud implica crear un evento en Google Calendar (por ejemplo, con palabras como 'haz una reunión', 'agenda', 'agendar', 'programar' y menciona 'Google Calendar' o 'calendario'), genera una query para la clave "gmail" en el formato: "create_event|summary:<asunto>|start:<fecha_inicio>|end:<fecha_fin>", donde:
                    - <asunto> es el título del evento extraído de la consulta (con la primera letra en mayúscula).
                    - <fecha_inicio> y <fecha_fin> están en formato ISO (ej., "2023-10-18T14:00:00"), calculadas a partir de la fecha y hora proporcionadas por el usuario y la fecha actual ({hoy}). Si no se especifica duración, asume 1 hora por defecto.
                    - Usa la fecha actual ({hoy}) para inferir el mes y año si el usuario solo menciona el día (ej., "el 18" → "2023-10-18" si hoy es octubre de 2023). """
                
                f"Estructura del JSON para POST simple:\n"
                f"{{\n"
                f"    \"gmail\": \"<query para Gmail o 'N/A' si no aplica>\",\n"
                f"    \"notion\": \"<query para Notion o 'N/A' si no aplica>\",\n"
                f"    \"slack\": \"<query para Slack o 'N/A' si no aplica>\",\n"
                f"    \"hubspot\": \"<query para HubSpot o 'N/A' si no aplica>\",\n"
                f"    \"outlook\": \"<query para Outlook o 'N/A' si no aplica>\",\n"
                f"    \"clickup\": \"<query para ClickUp o 'N/A' si no aplica>\",\n"
                f"    \"dropbox\": \"<query para Dropbox o 'N/A' si no aplica>\",\n"
                f"    \"asana\": \"<query para Asana o 'N/A' si no aplica>\",\n"
                f"    \"googledrive\": \"<query para Google Drive o 'N/A' si no aplica>\",\n"
                f"    \"onedrive\": \"<query para OneDrive o 'N/A' si no aplica>\",\n"
                f"    \"teams\": \"<query para Teams o 'N/A' si no aplica>\"\n"
                f"}}\n\n"
                
                f"ESPECIFICAMENTE SI Y SOLO SI LA SOLICITUD ES TIPO POST AUTOMATIZADA (QUEMADA):\n"
                f"OBLIGATORIO: Responde con 'Es una solicitud automatizada' seguido del JSON de abajo\n"
                f"Detecta los patrones de automatización solicitados por el usuario. Estos se identifican con frases como:\n"
                f"- 'Cada vez que...'\n"
                f"- 'Siempre que...'\n"
                f"- 'Mueve siempre...'\n"
                f"- 'Borra automáticamente...'\n"
                f"- 'Cuando reciba correos de...'\n"
                f"- 'Si un proyecto cambia a...'\n"
                f"- 'Contesta automáticamente a...'\n"
                f"- Cualquier indicación de acción repetitiva o condicional\n\n"
                
                f"⚠ **VALIDACIÓN ESTRICTA:** ⚠\n"
                f"Incluye **únicamente** los servicios que sean lógicamente aplicables a la acción descrita:\n"
                f"- **Si la automatización menciona correos**, **SOLO** incluir 'gmail' y/o 'outlook'.\n"
                f"- **Si la automatización menciona proyectos o tareas**, **SOLO** incluir 'notion', 'asana' y/o 'clickup'.\n"
                f"- **Si la automatización menciona archivos**, **SOLO** incluir 'googledrive', 'dropbox' y/o 'onedrive'.\n"
                f"- **Si la automatización menciona mensajería/chat**, **SOLO** incluir 'slack' y/o 'teams'.\n"
                f"- **Si la automatización menciona contactos, CRM o ventas**, **SOLO** incluir 'hubspot'.\n"
                f"🚫 **NO agregues un servicio si no está relacionado con la acción descrita.**\n"
                f"🚫 **No pongas claves con 'N/A', simplemente excluye el servicio si no aplica.**\n\n"
                
                f"Estructura del JSON para POST automatizada:\n"
                f"{{\n"
                f"    \"gmail\": {{\n"
                f"        \"condition\": \"<condición que activa la acción>\",\n"
                f"        \"action\": \"<acción a realizar>\"\n"
                f"    }},\n"
                f"    \"notion\": {{\n"
                f"        \"condition\": \"<condición>\",\n"
                f"        \"action\": \"<acción>\"\n"
                f"    }},\n"
                f"    // ... (y así para todos los servicios aplicables)\n"
                f"}}\n\n"
                
                f"CAPACIDADES ESPECÍFICAS POR API:\n"
                f"- GMAIL: Buscar correos por asunto/remitente, eliminar correos, mover a spam, enviar correo, crear borrador.\n"
                f"- NOTION: Status de tareas, información de bloques de página.\n"
                f"- CLICKUP: Status de tareas, marcar tareas como completadas.\n"
                f"- OUTLOOK: Obtener correos, mover a spam, eliminar correos.\n"
                f"- HUBSPOT: Mostrar información de contactos y negocios.\n"
                f"- ASANA: Mostrar tareas con los status.\n"
                f"- ONEDRIVE/GOOGLE DRIVE/DROPBOX: Mostrar archivos en carpetas, mover/eliminar archivos, crear carpetas.\n"
                f"- SLACK: Buscar mensajes en canales.\n"
                f"- TEAMS: Búsqueda de mensajes y conversaciones.\n\n"
                
                f"El JSON debe incluir solo información relevante extraída del mensaje del usuario y ser fácilmente interpretable por sistemas automatizados."
                f"Si el mensaje del usuario no puede ser interpretado para una de las aplicaciones, responde 'N/A'."
                )   
                if last_ai_response:
                    prompt += f"\nLa última respuesta de la IA fue: '{last_ai_response}'.\n"

                response = openai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": """Eres un asistente especializado en interpretar solicitudes del usuario para diferentes APIs (Gmail, Notion, Slack, HubSpot, Outlook, ClickUp, Dropbox, Asana, Google Drive, OneDrive, Teams). Tu objetivo principal es clasificar correctamente el tipo de solicitud y extraer información relevante en formato JSON para cada servicio aplicable.
                        #### REGLAS PARA CLASIFICACIÓN DE SOLICITUDES:
                        1. SOLICITUDES GET (CONSULTA/BÚSQUEDA DE INFORMACIÓN):
                        - Cuando el usuario usa verbos como "Mándame", "Pásame", "Envíame", "Muéstrame", "Busca", "Encuentra", "Dame", "Dime", "Quiero ver" dirigidos a SÍ MISMO.
                        - Cuando pregunta sobre información existente: "¿Cuáles son...?", "¿Dónde están...?", "¿Qué tareas...?"
                        - Ejemplos claros:
                            * "Mándame los correos de marketing" = GET (buscar correos)
                            * "Busca documentos sobre presupuesto" = GET (buscar archivos)
                            * "Quiero ver mis tareas pendientes" = GET (buscar tareas)
                        - RESPUESTA: "Es una solicitud GET" + JSON con queries específicas para cada API

                        2. SOLICITUDES POST SIMPLE (ACCIÓN ÚNICA):
                        - Verbos de acción hacia sistemas o terceros: "Crear", "Enviar (a otra persona)", "Eliminar", "Mover", "Actualizar", "Editar", "Agregar"
                        - Ejemplos claros:
                            * "Crea una tarea para el proyecto X" = POST (crear tarea)
                            * "Envía un correo a Juan con asunto..." = POST (enviar correo)
                            * "Elimina los documentos duplicados" = POST (eliminar archivos)
                        - RESPUESTA: "Es una solicitud POST" + JSON con acciones para cada API aplicable

                        3. SOLICITUDES POST AUTOMATIZADAS (CONDICIONALES/REPETITIVAS):
                        - Frases que indican automatización: "Cada vez que", "Siempre que", "Cuando ocurra", "Automáticamente"
                        - Contienen una condición Y una acción
                        - Ejemplos claros:
                            * "Cuando reciba correos de marketing, muévelos a la carpeta promociones" = AUTOMATIZADA
                            * "Si una tarea cambia a completada, notifica al equipo en Slack" = AUTOMATIZADA
                        - RESPUESTA: "Es una solicitud automatizada" + JSON con condition/action para cada API aplicable

                        4. SALUDOS:
                        - Expresiones como: "Hola", "Buenos días", "Qué tal", etc. sin solicitud adicional
                        - RESPUESTA: "Es un saludo"

                        5. REFERENCIAS A CONVERSACIONES PREVIAS:
                        - Cuando menciona "como hablamos antes", "de lo que mencionaste", "respuesta anterior"
                        - RESPUESTA: "Se refiere a la respuesta anterior"

                        #### GUÍA DETALLADA PARA INTERPRETACIÓN:

                        - VERBOS DIRIGIDOS AL USUARIO vs ACCIONES HACIA SISTEMAS:
                        * "Mándame/Pásame/Muéstrame X" = GET (el usuario quiere VER/RECIBIR información)
                        * "Manda/Pasa/Crea/Elimina X (en un sistema)" = POST (el usuario quiere EJECUTAR una acción)

                        - ESPECÍFICOS PARA EMAIL (GMAIL/OUTLOOK):
                        * GET: "Mándame correos de Juan" → query=from:juan
                        * POST: "Envía un correo a juan@example.com" → acción=enviar, destinatario=juan@example.com
                        * AUTOMATIZADA: "Cuando reciba correos de spam, elimínalos" → condition=recepción de spam, action=eliminar

                        - ESPECÍFICOS PARA SLACK:
                        * GET: "Muéstrame mensajes del canal marketing" → query=in:marketing
                        * GET: "Busca mensajes donde se mencionó el proyecto Alpha" → query=proyecto Alpha
                        * POST: "Envía un mensaje al canal general" → acción=enviar mensaje, canal=general
                        * POST: "Notifica a @dev-team sobre la actualización" → acción=enviar mensaje, destinatario=@dev-team
                        * AUTOMATIZADA: "Cuando alguien mencione 'urgente' en Slack, notifícame" → condition=mención de 'urgente', action=notificar
                        * AUTOMATIZADA: "Si hay mensajes sin responder después de 2 horas, envía un recordatorio" → condition=mensajes sin respuesta, action=enviar recordatorio

                        - ESPECÍFICOS PARA HUBSPOT:
                        * GET: "Muéstrame contactos de la empresa XYZ" → query=contacto XYZ
                        * GET: "Encuentra empresas del sector tecnológico" → query=empresa tecnológico
                        * GET: "Busca negocios con valor mayor a 10k" → query=negocio >10k
                        * GET: "Dame información sobre el contacto Pedro García" → query=contacto Pedro García
                        * POST: "Crea un contacto para María López con email maria@ejemplo.com" → acción=crear contacto
                        * POST: "Actualiza el teléfono de Juan Pérez a 555-123-4567" → acción=actualizar contacto
                        * POST: "Registra una nueva empresa llamada ABC Corp" → acción=crear empresa
                        * AUTOMATIZADA: "Cuando un lead pase a calificado, asígnalo a ventas" → condition=cambio estado lead, action=asignar
                        * AUTOMATIZADA: "Si un contacto no responde en 7 días, envía email de seguimiento" → condition=sin respuesta, action=enviar seguimiento

                        - ESPECÍFICOS PARA TAREAS (NOTION/CLICKUP/ASANA):
                        * GET: "Muéstrame tareas pendientes" → query=tareas pendientes
                        * POST: "Marca como completada la tarea X" → acción=actualizar estado
                        * AUTOMATIZADA: "Cuando una tarea pase a En Progreso, notifica al equipo" → condition=cambio de estado, action=notificar

                        - ESPECÍFICOS PARA ARCHIVOS (GOOGLE DRIVE/DROPBOX/ONEDRIVE):
                        * GET: "Encuentra documentos de presupuesto" → query=presupuesto
                        * POST: "Comparte la carpeta Proyectos con maria@example.com" → acción=compartir
                        * AUTOMATIZADA: "Cuando se suban archivos PDF, notifícame" → condition=subida de PDF, action=notificar

                        - ESPECÍFICOS PARA TEAMS:
                        * GET: "Encuentra conversaciones con Juan sobre el proyecto" → query=conversation with:Juan proyecto
                        * GET: "Busca mensajes donde se mencionó la reunión semanal" → query=message:reunión semanal
                        * POST: "Envía un mensaje a María en Teams" → acción=enviar mensaje, destinatario=María
                        * AUTOMATIZADA: "Cuando alguien comparta un archivo en el canal Proyectos, notifícame" → condition=archivo compartido, action=notificar

                        Si encuentras ambigüedad, analiza el contexto completo y la intención principal del usuario. Prioriza la interpretación como GET cuando el usuario busca información para sí mismo, y como POST cuando claramente solicita ejecutar acciones en plataformas.

                        Genera respuestas estructuradas y precisas en el formato JSON solicitado, excluyendo servicios no aplicables (usa "N/A"). Asegúrate de capturar todos los detalles relevantes de la solicitud del usuario.

                        RECUERDA:
                        - Para HubSpot, identifica claramente el tipo de objeto (contacto, empresa, negocio) en las consultas GET
                        - Para Slack, adapta la consulta de Gmail pero hazla más informal y directa para contextos de mensajería
                        - En todos los casos, solo incluye en el JSON los servicios que son relevantes para la solicitud específica """},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=3500
                )
                ia_interpretation = response.choices[0].message.content.strip().lower()
                print(ia_interpretation)

                if 'saludo' in ia_interpretation:
                    prompt_greeting = f"Usuario: {last_message}\nResponde de manera cálida y amigable, como si fuera una conversación normal. Y pon emojis"

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
                                user = get_user_from_db(email, cache, mongo)
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
                                googledrive = search_google_drive(googledrive_query)
                                search_results_data['googledrive'] = googledrive.get_json() if hasattr(googledrive, 'get_json') else googledrive
                            except Exception:
                                search_results_data['googledrive'] = ["No se encontró ningún valor en Google Drive"]


                            try:
                                onedrive_results = search_onedrive(onedrive_query)
                                search_results_data['onedrive'] = onedrive_results.get_json() if hasattr(onedrive_results, 'get_json') else onedrive_results
                            except Exception:
                                search_results_data['onedrive'] = ["No se encontró ningún valor en OneDrive"]

                            try:
                                teams_results = search_teams(teams_query)
                                search_results_data['teams'] = teams_results.get_json() if hasattr(teams_results, 'get_json') else teams_results
                            except Exception:
                                search_results_data['teams'] = ["No se encontró ningún valor en Teams"]
                            print("DATA", search_results_data)
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
                                user = get_user_from_db(email, cache, mongo)
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
                                    'dropbox': post_to_dropbox,
                                    'asana': post_to_asana,
                                    'googledrive': post_to_googledrive,
                                    'onedrive': post_to_onedrive,
                                    # 'teams': post_to_teams,
                                }
                                
                                # Ejecutar las funciones de las APIs correspondientes
                                for service, query in queries.items():
                                    if query.lower() != 'n/a' and service in apis:
                                        try:
                                            response = apis[service](query)
                                            print("RESPONSES", response)
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
                elif 'automatizada' in ia_interpretation:
                    start = ia_interpretation.find('{')
                    end = ia_interpretation.rfind('}') + 1
                    json_block = ia_interpretation[start:end]

                    try:
                        queries = json.loads(json_block)
                        print(queries)

                        post_results_data = {}

                        for api, data in queries.items():
                            condition = data.get('condition', '').lower()
                            action = data.get('action', '').lower()
                            
                            if condition != "n/a" and action != "n/a" and api:
                                try:
                                    function = functionsAuto[f"post_auto_{api}"]
                                    response = function(condition, action)
                                    
                                    if response:
                                        response_json = response.get_json()
                                        message = response_json.get('message', None)
                                        print(response_json)
                                        
                                        if message and message != "Sin mensaje":
                                            if api not in post_results_data:
                                                post_results_data[api] = []
                                            post_results_data[api].append(message)
                                            
                                except Exception as e:
                                    pass  # Manejo de errores opcional

                        if post_results_data:
                            return jsonify({
                                "message": "✅ ¡Tus reglas de automatización han sido creadas con éxito! 🎉 Ahora tus acciones se realizaran según las reglas establecidas. 📩✨"
                            }), 200
                        else:
                            return jsonify({
                                "message": "⚠️ No se pudieron crear tus reglas de automatización. ¿Podrías reformularlas? 🤔"
                            }), 400

                    except json.JSONDecodeError:
                        return jsonify({"error": "Formato JSON inválido"}), 400
                elif 'anterior' in ia_interpretation:
                    reference_prompt = f"El usuario dijo: '{last_message}'\n"
                    reference_prompt += f"La última respuesta de la IA fue: '{last_response}'.\n"
                    reference_prompt += "Responde al usuario considerando la respuesta anterior."

                    response_reference = openai.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "system", "content":  """Eres un asistente que identifica saludos o solicitudes (get, post simples y post automatizados (quemados)). 
                    - Si el usuario saluda, responde de forma cálida y amigable, como si fuera una conversación fluida.
                    - Si el usuario comparte cómo se siente o menciona una situación personal, responde con empatía y comprensión.
                    - Si el usuario solicita automatizaciones o reglas persistentes (quemadas), identifícalas correctamente.
                    - Siempre mantén una respuesta natural y cercana, evitando un tono robótico.
                    """},
                                {"role": "user", "content": reference_prompt}],
                        max_tokens=150
                    )
                    ia_response = response_reference.choices[0].message.content.strip()
                else:
                    ia_response = "Lo siento, no entendí el mensaje. ¿Puedes especificar más sobre lo que necesitas?"

            except Exception as e:
                ia_response = f"Lo siento, ocurrió un error al procesar tu mensaje: {e}"

        return jsonify({"message": ia_response})
    

    def extract_links_from_datas(datas):
        """Extrae los enlaces y los nombres (asunto/página/mensaje/nombre de archivo) de cada API según la estructura de datos recibida."""
        results = {
            'gmail': [], 'slack': [], 'notion': [], 'outlook': [], 'clickup': [], 'hubspot': [], 
            'dropbox': [], 'asana': [], 'onedrive': [], 'teams': [], 'googledrive': []
        }

        # Gmail
        if isinstance(datas.get('gmail'), list):
            results['gmail'] = [
                {'link': item['link'], 'subject': item.get('subject', 'No subject')} 
                for item in datas['gmail'] if 'link' in item
            ]
        
        # Slack
        if isinstance(datas.get('slack'), list):
            results['slack'] = [
                {'link': item['link'], 'message': item.get('message', 'No message')} 
                for item in datas['slack'] if 'link' in item
            ]
        
        # Notion
        if isinstance(datas.get('notion'), list):
            results['notion'] = [
                {'url': item['url'], 'page_name': item.get('properties', {}).get('Nombre', 'Sin Nombre')} 
                for item in datas['notion'] if 'url' in item
            ]
        
        # Outlook
        if isinstance(datas.get('outlook'), list):
            results['outlook'] = [
                {'webLink': item['webLink'], 'subject': item.get('subject', 'No subject')} 
                for item in datas['outlook'] if 'webLink' in item
            ]
        
        # ClickUp
        if isinstance(datas.get("clickup"), list):
            results['clickup'] = [
                {'url': item['url'], 'task_name': item.get('task_name', 'Sin Nombre')} 
                for item in datas["clickup"] if 'url' in item
            ]
        
        # Dropbox
        if isinstance(datas.get("dropbox"), list):
            results['dropbox'] = [
                {'url': item['download_link'], 'name': item.get('name', 'Sin Nombre')} 
                for item in datas["dropbox"] if 'download_link' in item
            ]
        
        # OneDrive
        if isinstance(datas.get("onedrive"), list):
            results['onedrive'] = [
                {'url': item['url'], 'name': item.get('name', 'Sin Nombre')} 
                for item in datas["onedrive"] if 'url' in item
            ]
        
        # Asana
        if isinstance(datas.get("asana"), list):
            results['asana'] = [
                {'url': item['url'], 'task_name': item.get('name', 'Sin Nombre')} 
                for item in datas["asana"] if 'url' in item
            ]
        
        # Google Drive
        if isinstance(datas.get("googledrive"), list):
            results['googledrive'] = [
                {'url': item['url'], 'name': item.get('name', 'Sin Nombre')} 
                for item in datas["googledrive"] if 'url' in item
            ]
        
        return results
