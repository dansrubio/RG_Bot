"""
Handler para tracking automático de mensajes y gestión de usuarios
Procesa todos los mensajes para mantener actualizada la base de datos (MongoDB)
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters
from database.crud.usuario_crud import UsuarioCRUD

logger = logging.getLogger(__name__)

# IDs de cuentas especiales que no deben ser procesadas
TELEGRAM_SYSTEM_IDS = {
    777000,      # Telegram oficial
    136817688,   # @Channel_Bot
    429000,      # Telegram Support
    42777,       # Telegram Tips
    93372553,    # @BotFather
}


async def procesar_mensaje_usuario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Procesa mensajes de usuarios para mantener actualizada la base de datos (MongoDB).
    Usa UsuarioCRUD.crear_o_actualizar_usuario que interactúa con pymongo.
    """
    try:
        # Verificar que tenemos un usuario válido
        user = update.effective_user
        if not user:
            return

        # Filtrar cuentas del sistema de Telegram
        if user.id in TELEGRAM_SYSTEM_IDS:
            logger.debug(f"🤖 Ignorando cuenta del sistema: {user.id}")
            return

        # Filtrar bots (excepto si es un bot específico que queremos trackear)
        if user.is_bot:
            logger.debug(f"🤖 Ignorando bot: {user.id} (@{user.username})")
            return

        # Extraer información del usuario
        user_id = user.id
        username = user.username
        first_name = user.first_name or ""
        last_name = user.last_name or ""
        
        # Combinar nombre completo
        full_name = f"{first_name} {last_name}".strip() or None

        # Crear o actualizar usuario en base de datos (MongoDB)
        usuario_doc = UsuarioCRUD.crear_o_actualizar_usuario(
            user_id=user_id,
            username=username,
            name=full_name
        )


    except Exception as e:
        uid = update.effective_user.id if update.effective_user else "desconocido"
        logger.error(f"❌ Error procesando mensaje de usuario {uid}: {e}", exc_info=True)


def es_mensaje_valido(update: Update) -> bool:
    """
    Verifica si el mensaje debe ser procesado
    """
    # Solo procesar si hay un usuario válido
    if not update.effective_user:
        return False

    # No procesar mensajes de cuentas del sistema
    if update.effective_user.id in TELEGRAM_SYSTEM_IDS:
        return False

    # No procesar bots
    if update.effective_user.is_bot:
        return False

    # Solo procesar mensajes con contenido (message o channel_post)
    if not (update.message or update.channel_post):
        return False

    return True


async def message_tracker_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler principal para el tracking de mensajes
    """
    try:
        # Verificar si el mensaje debe ser procesado
        if not es_mensaje_valido(update):
            return

        # Procesar mensaje del usuario (función async)
        await procesar_mensaje_usuario(update, context)

    except Exception as e:
        # Error silencioso para no interferir con otros handlers, pero con log
        logger.error(f"❌ Error en message_tracker: {e}", exc_info=True)


def register_message_tracker(application):
    """
    Registra el handler de tracking de mensajes
    IMPORTANTE: Debe ser registrado al final (menor prioridad)
    """
    try:
        # Handler con prioridad muy baja (group=-1) para que se ejecute al final
        application.add_handler(
            MessageHandler(
                filters.ALL,  # Captura todos los mensajes
                message_tracker_handler
            ),
            group=-1  # Prioridad baja - se ejecuta después de otros handlers
        )

    except Exception as e:
        logger.error(f"❌ Error registrando message tracker: {e}")
        raise