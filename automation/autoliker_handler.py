"""
Sistema AutoLiker - Bot principal (python-telegram-bot)
Reacciona automáticamente a:
  1. Publicaciones nuevas en el canal configurado (CANAL_ELEMENTOS)
  2. Mensajes con hashtags de solicitud en los grupos de GROUP_ADMIN_ID

Las reacciones se eligen al azar de REACCIONES_POOL.
"""

import logging
import random

from telegram import Update, ReactionTypeEmoji
from telegram.ext import Application, MessageHandler, ContextTypes, filters

from config import CANAL_ELEMENTOS, GROUP_ADMIN_ID

logger = logging.getLogger(__name__)

REACCIONES_POOL = ["❤", "👍", "🔥", "🥰", "🤩", "😍", "💯", "⚡"]  # Pool de reacciones disponibles

HASHTAGS_SOLICITUD = {  # Hashtags que activan el like en solicitudes
    "#game", "#games", "#juego", "#juegos",
    "#solicitud", "#pedido", "#sos", "#ayuda",
    "#help", "#bug", "#report", "#error",
}


def _reaccion_aleatoria() -> str:
    """Retorna una reacción aleatoria del pool"""
    return random.choice(REACCIONES_POOL)


def _tiene_hashtag_solicitud(texto: str) -> bool:
    """Verifica si el texto contiene al menos un hashtag del sistema de solicitudes"""
    if not texto:
        return False
    palabras = {p.lower() for p in texto.split()}
    return bool(palabras & HASHTAGS_SOLICITUD)


async def _enviar_reaccion(context, chat_id: int, message_id: int) -> None:
    """Envía una reacción aleatoria a un mensaje específico"""
    emoji = _reaccion_aleatoria()
    try:
        await context.bot.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=[ReactionTypeEmoji(emoji=emoji)],
        )
        logger.debug(f"Reacción '{emoji}' enviada al msg {message_id} en chat {chat_id}")
    except Exception as e:
        logger.warning(f"No se pudo reaccionar al msg {message_id} en {chat_id}: {e}")


async def _handler_canal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reacciona a cualquier publicación nueva en el canal configurado"""
    msg = update.channel_post or update.message
    if not msg:
        return
    await _enviar_reaccion(context, msg.chat_id, msg.message_id)


async def _handler_solicitud_grupo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reacciona a mensajes con hashtags de solicitud en los grupos configurados"""
    msg = update.message
    if not msg:
        return

    texto = msg.text or msg.caption or ""
    if not _tiene_hashtag_solicitud(texto):
        return

    await _enviar_reaccion(context, msg.chat_id, msg.message_id)


def register_autoliker_handler(app: Application) -> None:
    """Registra los handlers del autoliker en la aplicación"""
    try:
        if CANAL_ELEMENTOS:  # Solo registrar si el canal está configurado
            app.add_handler(MessageHandler(
                filters.Chat(CANAL_ELEMENTOS) & (filters.ALL),
                _handler_canal,
            ))

        if GROUP_ADMIN_ID:  # Solo registrar si hay grupos configurados
            app.add_handler(MessageHandler(
                filters.Chat(GROUP_ADMIN_ID) & (filters.TEXT | filters.CAPTION),
                _handler_solicitud_grupo,
            ))

    except Exception as e:
        logger.error(f"Error registrando autoliker_handler: {e}")
