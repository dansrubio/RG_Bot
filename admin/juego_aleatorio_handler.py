"""
Handler del comando /juego_aleatorio
Muestra un juego aleatorio del sistema y elimina mensajes previos
"""

import logging
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import CommandHandler, ContextTypes
from cachetools import TTLCache

from config import BOT_URL
from database.crud.elemento_crud import ElementoCRUD

logger = logging.getLogger(__name__)

# Diccionario para almacenar el último mensaje por chat con expiración de 24 horas
_last_messages = TTLCache(maxsize=10000, ttl=86400)


async def juego_aleatorio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /juego_aleatorio - Muestra un juego aleatorio del sistema"""
    user = update.effective_user
    message = update.effective_message
    chat = update.effective_chat
    chat_id = chat.id if chat else None

    try:
        # Intentar eliminar el comando del usuario (silenciosamente)
        try:
            await message.delete()
        except Exception:
            pass

        # Eliminar mensaje anterior del bot si existe
        if chat_id in _last_messages:
            try:
                await context.bot.delete_message(
                    chat_id=chat_id,
                    message_id=_last_messages[chat_id]
                )
            except Exception:
                pass

        # Obtener todos los elementos (retorna lista desde MongoDB)
        todos_elementos = ElementoCRUD.listar_todos_elementos()

        if not todos_elementos:
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text="ℹ️ **No hay juegos disponibles**\n\n"
                     "Aún no se han agregado juegos al sistema.",
                parse_mode=ParseMode.MARKDOWN
            )
            _last_messages[chat_id] = msg.message_id
            return

        # Seleccionar elemento aleatorio
        elemento = random.choice(todos_elementos)

        # Obtener el _id real (ObjectId) del documento
        elemento_id = elemento.get("_id") if isinstance(elemento, dict) else None

        # Obtener usuarios únicos (ElementoCRUD espera el id que se usó al guardar solicitudes;
        # en la implementación actual ese id es el ObjectId almacenado en elemento_solicitudes.elemento_id)
        try:
            usuarios_unicos = ElementoCRUD.obtener_usuarios_unicos_elemento(elemento_id)
        except Exception as e:
            logger.debug(f"Error obteniendo usuarios únicos para elemento {elemento_id}: {e}")
            usuarios_unicos = 0

        # Crear enlace usando el token (si existe)
        token = elemento.get("token", "")
        enlace = f"{BOT_URL}?start={token}" if token else BOT_URL

        # Calcular mensajes en el rango con valores por defecto si faltan campos
        id_inicio = elemento.get("id_inicio", 0)
        id_final = elemento.get("id_final", 0)
        try:
            rango_mensajes = max(0, int(id_final) - int(id_inicio) + 1)
        except Exception:
            rango_mensajes = 0

        # Crear botón
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎮 Ver Juego", url=enlace)]
        ])

        # Plurales
        usuarios_texto = "usuario" if usuarios_unicos == 1 else "usuarios"

        # Mostrar el identificador como cadena (ObjectId -> str)
        elemento_id_display = str(elemento_id) if elemento_id is not None else "N/A"

        nombre = elemento.get("nombre", "Sin nombre")
        solicitudes = elemento.get("solicitudes", 0)

        texto = (
            f"🎲 **JUEGO ALEATORIO**\n\n"
            f"🎮 **{nombre}**\n\n"
            f"📊 **Estadísticas:**\n"
            f"• 👥 {usuarios_unicos} {usuarios_texto}\n"
            f"• 📝 {rango_mensajes} mensajes\n"
            f"• 🆔 ID: `{elemento_id_display}`\n\n"
            f"💡 Usa `/juego_aleatorio` para ver otro juego"
        )

        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=texto,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )

        # Guardar el mensaje actual para poder eliminarlo en la siguiente invocación
        _last_messages[chat_id] = msg.message_id

    except Exception as e:
        logger.error(f"Error en juego_aleatorio_command: {e}", exc_info=True)
        try:
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text="❌ **Error obteniendo juego aleatorio**\n\n"
                     "Intenta nuevamente.",
                parse_mode=ParseMode.MARKDOWN
            )
            _last_messages[chat_id] = msg.message_id
        except Exception:
            pass


def register_juego_aleatorio_handler(application):
    """Registra el handler del comando /juego_aleatorio"""
    application.add_handler(CommandHandler("juego_aleatorio", juego_aleatorio_command))