import re
import logging
from telethon import events
from config import is_admin  #[cite: 1]

logger = logging.getLogger(__name__)

def register_info_handler(client):
    @client.on(events.NewMessage(pattern=re.compile(r"^/info", re.IGNORECASE)))
    async def handler_info(event):
        try:
            # Filtrar estrictamente: Solo administradores[cite: 1]
            if not is_admin(event.sender_id):
                return
                
            # 1. Información del Chat/Grupo actual
            chat = await event.get_chat()
            chat_id = event.chat_id
            chat_title = getattr(chat, 'title', 'Chat Privado / Desconocido')
            
            texto_respuesta = (
                f"ℹ️ **Información del Chat Actual:**\n"
                f"• **Nombre:** {chat_title}\n"
                f"• **ID del Chat:** `{chat_id}`\n"
            )
            
            # Verificar si el grupo tiene hilos/topics activos
            if event.reply_to_msg_id and getattr(event.message, 'reply_to', None):
                reply_info = event.message.reply_to
                if getattr(reply_info, 'forum_topic', False):
                    texto_respuesta += f"• **ID del Topic/Hilo:** `{reply_info.reply_to_top_id}`\n"
    
            texto_respuesta += "\n"
    
            # 2. Información si estás respondiendo a un mensaje
            if event.is_reply:
                reply_msg = await event.get_reply_message()
                sender = await reply_msg.get_sender()
                
                sender_id = sender.id if sender else "Desconocido"
                username = f"@{sender.username}" if getattr(sender, 'username', None) else "No tiene"
                nombre_usuario = getattr(sender, 'first_name', 'Canal/Bot / Sistema')
                
                texto_respuesta += (
                    f"💬 **Información del Mensaje Respondido:**\n"
                    f"• **ID del Mensaje:** `{reply_msg.id}`\n"
                    f"• **ID del Usuario:** `{sender_id}`\n"
                    f"• **Nombre:** {nombre_usuario}\n"
                    f"• **Username:** {username}\n"
                )
                
                if reply_msg.media:
                    texto_respuesta += f"• **Tipo de Media:** `{type(reply_msg.media).__name__}`\n"
            else:
                texto_respuesta += "💡 Tip: Responde a un mensaje con /info para obtener los IDs del mensaje y del usuario."
    
            # Responder directamente en el chat
            await event.reply(texto_respuesta)
            
        except Exception as e:
            logger.error(f"Error en handler_info: {e}")
            await event.reply(f"❌ Error al obtener información: {str(e)[:100]}")