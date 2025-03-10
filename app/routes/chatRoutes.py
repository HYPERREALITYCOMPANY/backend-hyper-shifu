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

openai.api_key=Config.CHAT_API_KEY
def setup_routes_chats(app, mongo):
    functions = setup_routes_searchs(app, mongo)
    functionsPost = setup_post_routes(app, mongo)
    functions2 = setup_rules_routes(app, mongo)
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

    # CHAT GET Y POSTS
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

        # ClickUp Results (Filtrar por tarea específica)
        clickup_results = "\n".join([
            f"Tarea: {task.get('task_name', 'Sin nombre')} | "
            f"Estado: {task.get('status', 'Sin estado')} | "
            f"Prioridad: {task.get('priority', 'Sin prioridad')} | "
            f"Asignado a: {', '.join(task.get('assignees', ['Sin asignar']))} | "
            f"Fecha de vencimiento: {task.get('due_date') if task.get('due_date') else 'Sin fecha'} | "
            f"Lista: {task.get('list', 'Sin lista')} | "
            f"URL: {task.get('url', 'Sin URL')}"
            for task in search_results.get('clickup', []) if isinstance(task, dict)
        ]) or "No se encontraron tareas relacionadas con 'Shiffu' en ClickUp."

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

        google_drive_results = "\n".join([
            f"Archivo: {file.get('title', 'Sin nombre')} | "
            f"Tamaño: {format_size(file.get('size'))} | "
            f"Modificado: {file.get('modified', 'Sin fecha')} | "
            f"Propietario: {file.get('owner', 'Desconocido')} ({file.get('owner_email', 'Sin correo')}) | "
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
                    f"""En ClickUp, la consulta debe ajustarse específicamente si el usuario menciona tareas, proyectos, estados o fechas.
                    Si menciona 'tarea de <nombre>' o 'estado de la tarea <nombre>', responde: 'tarea <nombre>'.
                    Si menciona 'proyecto <nombre>' o 'estado del proyecto <nombre>', responde: 'proyecto <nombre>'.
                    Si solo menciona 'estado' sin contexto adicional, devuelve 'estado de tareas' para obtener una visión general.
                    Si el usuario menciona fechas, ajusta la búsqueda para encontrar tareas dentro de ese rango.\n"""
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
                    f"ESPECIFICAMENTE SI Y SOLO SI LA SOLICITUD ES TIPO POST SIMPLE:\n"
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
                    f"   - Si el usuario menciona solo un nombre de usuario sin dominio (por ejemplo, 'gallodelacruz'), asume que es un correo de Gmail y completa con '@gmail.com'.\n"
                    f"   - Si el usuario proporciona un correo con dominio (por ejemplo, 'gallodelacruz@outlook.com'), respétalo tal como está.\n"
                    f"   - Genera la query en este formato: 'enviar correo a [destinatario] con asunto: [asunto] y cuerpo: [cuerpo]'.\n"
                    f"   - Ejemplo 1: 'envia un correo a gallodelacruz con asunto: Prueba API y cuerpo: Hola, este es un mensaje de prueba enviado desde mi API.'\n"
                    f"     🔹 Esto debe interpretarse como 'gallodelacruz@gmail.com'.\n"
                    f"   - Ejemplo 2: 'enviar correo a gallodelacruz@outlook.com con asunto: Trabajo y cuerpo: Aquí está la info'.\n"
                    f"     🔹 Aquí se respeta el dominio 'outlook.com'.\n"
                    f"6. **Agendar o Programar** (acciones como 'agendar', 'programar'):\n"
                    f"   - Ejemplo: Agendar cita en Gmail \n"
                    f"7. **Crear un borrador** (acciones como 'crear borrador', 'guardar borrador'):\n"
                    f"   - Ejemplo: Crear un borrador en Gmail con asunto: Prueba borrador cuerpo: Hola que tal te adjunto tal y tal (Esto se envía a Gmail, Outlook, Teams, Slack\n"
                    f"8. **Compartir archivos o carpetas** (acciones como 'compartir archivo', 'compartir carpeta', 'enviar archivo'):\n"
                    f"   - Ejemplo: Compartir archivo 'documento.pdf' con correo 'ejemplo@gmail.com' (Esto se puede hacer en Google Drive, Dropbox, OneDrive)\n"
                    f"   - Ejemplo: Compartir carpeta 'Proyectos' con los correos 'ejemplo1@gmail.com, ejemplo2@gmail.com' (Esto se puede hacer en Google Drive, Dropbox, OneDrive)\n"
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
                    f"ESPECIFICAMENTE SI Y SOLO SI LA SOLICITUD ES TIPO POST AUTOMATIZADA (QUEMADA):\n"
                    f"OBLIGATORIO: Responde con 'es una solicitud post automatizada' seguido del JSON de abajo\n"
                    f"Detecta los patrones de automatización solicitados por el usuario. Estos se identifican con frases como:\n"
                    f"- 'Cada vez que...'\n"
                    f"- 'Siempre que...'\n"
                    f"- 'Mueve siempre...'\n"
                    f"- 'Borra automáticamente...'\n"
                    f"- 'Cuando reciba correos de...'\n"
                    f"- 'Si un proyecto cambia a...'\n"
                    f"- 'Contesta automáticamente a...'\n"
                    f"- Cualquier indicación de acción repetitiva o condicional\n\n"
                    
                    f"Para estos casos, construye un JSON con:\n"
                    f"1. 'condition': La condición que activa la automatización\n"
                    f"2. 'action': La acción a realizar\n"
                    f"3. Para cada servicio relevante\n\n"
                    
                    f"**Estructura del JSON para la respuesta (con automatizaciones):**\n"
                    f"{{\n"
                    f"    \"gmail\": {{\n"
                    f"        \"condition\": \"<condición que activa la acción, ej: 'Cuando llegue correo de Dominos Pizza'>\",\n"
                    f"        \"action\": \"<acción a realizar, ej: 'borrar'>\"\n"
                    f"    }},\n"
                    f"    \"notion\": {{\n"
                    f"        \"condition\": \"<condición, ej: 'Cuando un proyecto cambie a En Curso'>\",\n"
                    f"        \"action\": \"<acción, ej: 'cambiar a prioridad crítica'>\"\n"
                    f"    }},\n"
                    f"    \"slack\": {{\n"
                    f"        \"condition\": \"<condición>\",\n"
                    f"        \"action\": \"<acción>\"\n"
                    f"    }},\n"
                    f"    \"hubspot\": {{\n"
                    f"        \"condition\": \"<condición>\",\n"
                    f"        \"action\": \"<acción>\"\n"
                    f"    }},\n"
                    f"    \"outlook\": {{\n"
                    f"        \"condition\": \"<condición>\",\n"
                    f"        \"action\": \"<acción>\"\n"
                    f"    }},\n"
                    f"    \"clickup\": {{\n"
                    f"        \"condition\": \"<condición>\",\n"
                    f"        \"action\": \"<acción>\"\n"
                    f"    }},\n"
                    f"    \"dropbox\": {{\n"
                    f"        \"condition\": \"<condición>\",\n"
                    f"        \"action\": \"<acción>\"\n"
                    f"    }},\n"
                    f"    \"asana\": {{\n"
                    f"        \"condition\": \"<condición>\",\n"
                    f"        \"action\": \"<acción>\"\n"
                    f"    }},\n"
                    f"    \"googledrive\": {{\n"
                    f"        \"condition\": \"<condición>\",\n"
                    f"        \"action\": \"<acción>\"\n"
                    f"    }},\n"
                    f"    \"onedrive\": {{\n"
                    f"        \"condition\": \"<condición>\",\n"
                    f"        \"action\": \"<acción>\"\n"
                    f"    }},\n"
                    f"    \"teams\": {{\n"
                    f"        \"condition\": \"<condición>\",\n"
                    f"        \"action\": \"<acción>\"\n"
                    f"    }}\n"
                    f"}}\n"
                    f"Usa 'N/A' si una API no aplica a la solicitud de automatización.\n"
                    f"Asegúrate de que las condiciones sean claras y específicas, y que las acciones sean ejecutables por el sistema.\n"
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
                    queries = json.loads(json_block)

                    print(queries)
                    if queries:
                        try:
                            for api, data in queries.items():
                                condition = data.get('condition', '')
                                action = data.get('action', '')    
                                if condition and action and condition.lower() != "n/a" and action.lower() != "n/a":
                                    function_name = f"post_auto_{api}"
                                    if function_name in functionsAuto:
                                        function = functionsAuto[function_name]
                                        response = function(condition, action)
                                        if response:
                                            print(response)
                                        else:
                                            print(f"No se pudo ejecutar la acción para {api}.")
                                    else:
                                        print(f"La función para {api} no está definida en functionsPost.")                     
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
