"""
Sistema de limpieza de mensajes de servicio de Telegram
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

# Filtro robusto para detectar todos los mensajes de servicio relevantes
SERVICE_FILTER = (
    filters.StatusUpdate.NEW_CHAT_MEMBERS |
    filters.StatusUpdate.LEFT_CHAT_MEMBER |
    filters.StatusUpdate.NEW_CHAT_TITLE |
    filters.StatusUpdate.NEW_CHAT_PHOTO |
    filters.StatusUpdate.DELETE_CHAT_PHOTO |
    filters.StatusUpdate.PINNED_MESSAGE |
    filters.StatusUpdate.FORUM_TOPIC_CREATED |
    filters.StatusUpdate.FORUM_TOPIC_EDITED |
    filters.StatusUpdate.FORUM_TOPIC_CLOSED |
    filters.StatusUpdate.FORUM_TOPIC_REOPENED |
    filters.StatusUpdate.MESSAGE_AUTO_DELETE_TIMER_CHANGED
)

async def cleaner_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para limpiar mensajes de servicio"""
    msg = update.effective_message
    if msg:
        try:
            await msg.delete()
        except Exception:
            pass

def register_cleaner(application):
    """Registra el cleaner con filtro robusto para mensajes de servicio"""
    try:
        application.add_handler(
            MessageHandler(SERVICE_FILTER, cleaner_handler),
            group=1  # Grupo de prioridad baja
        )
    except Exception as e:
        logging.error(f"❌ Error registrando cleaner: {e}")