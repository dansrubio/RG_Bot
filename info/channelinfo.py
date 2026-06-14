"""
Sistema para detectar comandos en canales y enviar información a admins
"""
import logging
import html
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters


async def channel_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja mensajes en canales y detecta el comando /channel"""
    if not update.channel_post:  # Solo procesar si es un post de canal
        return

    message = update.channel_post

    if not message.text or not message.text.strip().startswith(
            '/channel'):  # Verificar si el mensaje es exactamente "/channel"
        return

    # Eliminar el mensaje del comando
    try:
        await context.bot.delete_message(
            chat_id=message.chat.id,
            message_id=message.message_id
        )
    except Exception:
        pass  # Si no se puede eliminar, continuar

    # Obtener información del canal
    chat = message.chat

    # Información básica del canal
    text = (
        f"📝 <b>Comando /channel detectado</b>\n\n"
        f"📢 <b>Información del canal:</b>\n"
        f"• Título: {html.escape(chat.title) if chat.title else 'Sin título'}\n"
        f"• ID: <code>{chat.id}</code>\n"
        f"• Username: @{chat.username if chat.username else 'Sin username público'}\n"
        f"• Tipo: Canal"
    )

    # Intentar obtener número de suscriptores
    try:
        member_count = await context.bot.get_chat_member_count(chat.id)
        text += f"\n• Suscriptores: {member_count:,}"
    except Exception:
        text += f"\n• Suscriptores: No disponible"

    # Intentar obtener descripción del canal
    try:
        full_chat = await context.bot.get_chat(chat.id)
        if hasattr(full_chat, 'description') and full_chat.description:
            description = full_chat.description[:100] + "..." if len(
                full_chat.description) > 100 else full_chat.description
            text += f"\n• Descripción: {html.escape(description)}"
    except Exception:
        pass

    # Enviar información a cada admin
    from config import ADMIN_IDS  # Importación local

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=text,
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"Error enviando info de canal a admin {admin_id}: {e}")


def register_channel_handlers(application):
    """Registra el handler para detectar mensajes en canales"""
    try:
        application.add_handler(
            MessageHandler(
                filters.UpdateType.CHANNEL_POST & filters.TEXT,  # Solo posts de texto en canales
                channel_message_handler
            )
        )
    except Exception as e:
        logging.error(f"❌ Error registrando handler de canales: {e}")