"""
Handler de debug: verifica si el bot recibe comandos y otros updates en grupos.
Usa /ping para comprobar recepción y además registra todos los updates entrantes en logs.
"""
import logging
from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, filters, ContextTypes

logger = logging.getLogger(__name__)

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    message = update.effective_message

    logger.info(f"[DEBUG] /ping recibido en chat_id={chat.id} type={chat.type} user_id={user.id} username={getattr(user, 'username', None)}")
    try:
        # Intentar eliminar el comando del usuario (si hay permisos)
        await message.delete()
    except Exception as e:
        logger.debug(f"[DEBUG] No se pudo eliminar mensaje de comando /ping: {e}")

    try:
        await context.bot.send_message(
            chat_id=chat.id,
            text=f"pong — chat_id={chat.id}, tipo={chat.type}, user_id={user.id}, username={getattr(user, 'username', None)}"
        )
    except Exception as e:
        logger.error(f"[DEBUG] Error enviando respuesta /ping: {e}")

# Handler opcional que registra todos los updates (útil para ver qué actualizaciones llegan)
async def _log_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        logger.debug(f"[DEBUG-UPDATE] update_type={update.update_type} raw={update.to_dict() if hasattr(update, 'to_dict') else str(update)}")
    except Exception as e:
        logger.debug(f"[DEBUG] Error al loguear update: {e}")

def register_debug_handlers(application):
    application.add_handler(CommandHandler("ping", ping_command))
    # Añade un MessageHandler para registrar updates (no responde; solo loggea). Úsalo temporalmente.
    application.add_handler(MessageHandler(filters.ALL & (~filters.COMMAND), _log_all_messages), 0)
