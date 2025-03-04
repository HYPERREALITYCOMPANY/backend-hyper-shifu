#chat anterior landing (por si las dudas)
# @app.route("/api/chat", methods=["POST"])
#     def chat():
#         data = request.get_json()
#         user_messages = data.get("messages", [])
        
#         # Mensaje del sistema para guiar las respuestas
#         system_message = """
#         Eres Shiffu, un asistente virtual amigable y útil en su versión alfa. 
#         Ayudas a los usuarios respondiendo preguntas de manera clara y humana. 
#         Si el usuario pregunta "¿Qué es Shiffu?" o menciona "tu propósito" o algo parecido a tu funcionalidad, explica lo siguiente:
#         "Soy Shiffu, un asistente en su versión alfa. Estoy diseñado para ayudar a automatizar procesos de búsqueda y conectar aplicaciones como Gmail, Notion, Slack, Outlook y HubSpot. Mi objetivo es simplificar la gestión de tareas y facilitar la integración entre herramientas para que los usuarios puedan iniciar sesión, gestionar datos y colaborar de forma eficiente."
#         Responde saludos como "Hola" o "Saludos" con algo cálido como "¡Hola! Soy Shiffu, tu asistente virtual. ¿En qué puedo ayudarte hoy? 😊".
#         Para cualquier otra consulta, proporciona una respuesta útil y adaptada al contexto del usuario y lo más importante siempre menciona que ingresen sesion primero con Shiffu y luego con sus aplicaciones para ayudarlos de una mejor manera. Si te preguntan como iniciar sesión en shiffu menciona que arriba se encuentran dos botones y uno sirve para registrarse en Shiffu y el otro para iniciar sesión en
#         """
        
#         ia_response = "Lo siento, no entendí tu mensaje. ¿Puedes reformularlo?"

#         if user_messages:
#             try:
#                 # Llamada a OpenAI para procesar la conversación
#                 response = openai.chat.completions.create(
#                     model="gpt-3.5-turbo",  # Cambiar si tienes acceso a otro modelo
#                     messages=[
#                         {"role": "system", "content": system_message},
#                         *user_messages  # Mensajes enviados por el usuario
#                     ],
#                     max_tokens=150  # Limita el tamaño de la respuesta
#                 )
#                 # Extraemos la respuesta de OpenAI
#                 ia_response = response.choices[0].message.content.strip()
#             except Exception as e:
#                 ia_response = f"Lo siento, ocurrió un error al procesar tu mensaje: {e}"
        
#         # Retornamos la respuesta al frontend
#         return jsonify({"message": ia_response})
    