from datetime import datetime, timedelta, time
from flask import request, jsonify
from config import Config
import json
import re
from zoneinfo import ZoneInfo
import openai
from email.mime.text import MIMEText
import base64
import requests
openai.api_key = Config.CHAT_API_KEY

class ContextHandler:
    def __init__(self, db):
        self.db = db  # Referencia a la base de datos MongoDB
        
    def get_chat_context(self, email, chat_name, query, solicitud):
        """Obtiene y procesa el contexto de un chat específico"""
        print(f"DEBUG - Parámetros recibidos:")
        print(f"Email: {email}")
        print(f"Chat name: {chat_name}")
        print(f"Query: {query}")
        print(f"Solicitud: {solicitud}")
        
        instructions_by_source = {
        "gmail": """
        INSTRUCCIONES IMPORTANTES:
        1. Analiza detalladamente el historial del chat proporcionado a continuación.
        2. PRIORIZA la extracción del CONTENIDO COMPLETO de los correos relevantes, no solo metadatos.
        3. Para cada correo relevante, extrae y organiza:
        - Remitente (De: nombre y dirección de correo)
        - Destinatario(s) (Para:)
        - Asunto completo
        - Fecha y hora exactas
        - CUERPO COMPLETO del mensaje (esto es crítico)
        - Cualquier información sobre archivos adjuntos
        - Enlaces importantes mencionados en el correo
        """,
        "outlook": """
        INSTRUCCIONES IMPORTANTES:
        1. Analiza correos electrónicos de Outlook enfocados en comunicación corporativa.
        2. Extrae información crítica como reuniones, tareas y decisiones clave.
        3. Para cada correo relevante:
        - Remitente y destinatarios
        - Fecha, hora y asunto
        - Cuerpo completo del mensaje
        - Archivos adjuntos y enlaces importantes
        """,
        "notion": """
        INSTRUCCIONES IMPORTANTES:
        1. Revisa el contenido de páginas de Notion en busca de notas, tareas o información relevante al tema.
        2. Extrae:
        - Título del bloque o página
        - Texto del contenido (completo si es posible)
        - Menciones, etiquetas y enlaces incluidos
        """,
        "hubspot": """
        INSTRUCCIONES IMPORTANTES:
        1. Analiza los registros CRM de HubSpot relacionados con la empresa, contacto o negocio buscado.
        2. Para cada coincidencia relevante:
        - Nombre del contacto o compañía
        - Actividades recientes: correos, llamadas, reuniones
        - Notas internas, tareas asignadas o etapas del negocio
        """,
        "asana": """
        INSTRUCCIONES IMPORTANTES:
        1. Revisa tareas y proyectos de Asana vinculados a la solicitud.
        2. Extrae:
        - Nombre de la tarea y su responsable
        - Fecha límite y estado de la tarea
        - Descripción completa y comentarios asociados
        """,
        "clickup": """
        INSTRUCCIONES IMPORTANTES:
        1. Analiza tareas y actualizaciones en ClickUp relacionadas con la solicitud.
        2. Extrae:
        - Nombre de la tarea, responsable y estado actual
        - Fechas claves (inicio, vencimiento)
        - Descripción detallada y comentarios o actualizaciones
        """,
        "slack": """
        INSTRUCCIONES IMPORTANTES:
        1. Revisa las conversaciones en Slack en busca de mensajes relacionados con la solicitud.
        2. Para cada mensaje o hilo relevante, organiza:
        - Autor del mensaje
        - Fecha y canal
        - Cuerpo del mensaje, menciones y enlaces relevantes
        """,
        "onedrive": """
        INSTRUCCIONES IMPORTANTES:
        1. Examina archivos y documentos de OneDrive relacionados con la solicitud.
        2. Extrae:
        - Nombre del archivo y tipo de documento
        - Resumen o contenido textual si es aplicable
        - Enlaces o rutas de acceso a los archivos
        """,
        "googledrive": """
        INSTRUCCIONES IMPORTANTES:
        1. Busca documentos y archivos en Google Drive que contengan información sobre la solicitud.
        2. Extrae:
        - Títulos de documentos
        - Resúmenes o contenido clave
        - Enlaces de acceso directo y cualquier metadato relevante
        """,
        "dropbox": """
        INSTRUCCIONES IMPORTANTES:
        1. Revisa los archivos almacenados en Dropbox relacionados con la solicitud.
        2. Para cada archivo relevante, extrae y organiza:
        - Nombre del archivo y tipo
        - Descripción o contenido extraído (si es aplicable)
        - Enlaces de acceso o información sobre compartición del archivo
        """
    }
        # Obtenemos el usuario actualizado directamente de la base de datos
        user = self.db.usuarios.find_one({"correo": email})
        if not user:
            return "No encontré a este usuario, ¿seguro que está registrado?", 404
        
        # Buscamos el chat específico
        chat = next(
            (chat for chat in user.get("chats", []) if isinstance(chat, dict) and chat.get("name") == chat_name),
            None
        )
        if not chat or not chat.get("messages"):
            return "¡Hola! 👋 No tengo historial de mensajes previos para buscar. ¿Puedes buscar el correo de nuevo? 📧✨", 200
        
        # Obtenemos el historial de mensajes
        all_messages = chat.get("messages", [])
        print(f"DEBUG - Total de mensajes encontrados para {chat_name}: {len(all_messages)}")
        
        # Separamos los mensajes por rol y tomamos los últimos 10 de cada uno
        user_messages = [msg for msg in all_messages if msg.get("role") == "user"][-15:]
        assistant_messages = [msg for msg in all_messages if msg.get("role") == "assistant"][-15:]
        
        # Combinamos y ordenamos por timestamp (si está disponible)
        combined_messages = user_messages + assistant_messages
        try:
            # Intentamos ordenar por timestamp si está disponible
            combined_messages.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        except:
            # Si hay algún error al ordenar, no hacemos nada y mantenemos el orden actual
            pass
        
        # Imprime un resumen simplificado para debugging
        print(f"DEBUG - Mensajes de usuario: {len(user_messages)}, Mensajes de asistente: {len(assistant_messages)}")
        try:
            message_summary = {
                "user_messages": [{"timestamp": m.get("timestamp", "unknown"), "content_preview": m.get("content", "")[:50] + "..."} for m in user_messages[:3]],
                "assistant_messages": [{"timestamp": m.get("timestamp", "unknown"), "content_preview": m.get("content", "")[:50] + "..."} for m in assistant_messages[:3]]
            }
            print(f"DEBUG - Resumen de mensajes: {json.dumps(message_summary, indent=2)}")
        except Exception as e:
            print(f"DEBUG - Error al imprimir resumen de mensajes: {str(e)}")
        
        # Preparamos el prompt para el análisis de contexto
        # Selecciona las instrucciones apropiadas o usa las de Gmail como default
        selected_instructions = instructions_by_source.get(chat_name.lower(), instructions_by_source["gmail"])

        context_prompt = f"""
                Eres un asistente de correo electrónico súper eficiente y amigable. Tu tono es conversacional y natural, incluyendo algunos emojis apropiados para dar calidez a tus respuestas.

                El usuario ha solicitado información sobre: "{query}" relacionada específicamente con: "{solicitud}".

                {selected_instructions}

                Aquí está el historial del chat (últimos mensajes de usuario y asistente):
                {json.dumps(combined_messages, indent=2)}

                Ahora, responde sobre "{solicitud}" con esta estructura clara:
                1. Saludo personalizado y breve
                2. Resumen conciso de hallazgos (ej: "Encontré X correos relacionados con {solicitud}")
                3. Para cada correo relevante (presentando primero el más importante):
                a) ENCABEZADO: Remitente, fecha, asunto
                b) CONTENIDO PRINCIPAL: Resumen detallado o cita textual del cuerpo del mensaje
                c) DATOS CLAVE: Destaca fechas, números, enlaces o información crítica
                4. CONCLUSIÓN: Síntesis de la información más importante
                5. Cierre amigable ofreciendo ayuda adicional para profundizar en algún aspecto

                Si encuentras información parcial o incompleta, señálalo claramente.
                Si no encuentras información sobre "{solicitud}", responde amablemente explicando que no hay datos disponibles y sugiere términos de búsqueda alternativos.

                Tu respuesta debe ser NATURAL es decir no incluyas simbolos o identificadores por cada correo, directamente debes responder la peticion del usuario tomando que es la respuesta de un chat , priorizando la información del CUERPO de los correos, pero manteniendo un tono conversacional natural con 2-3 emojis sutiles.
        """
       
        # Llamamos a la API para procesar el contexto
        try:
            context_response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": f"Eres un asistente de {chat_name} amigable."},
                    {"role": "user", "content": context_prompt}
                ],
                max_tokens=1000
            )
            
            result = context_response.choices[0].message.content.strip()
            print(f"DEBUG - Respuesta generada (primeros 100 caracteres): {result[:100]}...")
            return result, 200
            
        except Exception as e:
            print(f"ERROR al procesar contexto: {str(e)}")
            return f"¡Ups! Ocurrió un error al procesar tu solicitud. Por favor, intenta de nuevo más tarde. Error: {str(e)}", 500