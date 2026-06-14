"""
Sistema centralizado de verificación de membresía en canales
Gestiona la verificación de usuarios en múltiples canales configurados
Requiere que el usuario sea miembro de TODOS los canales configurados
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.error import TelegramError

from config import VERIFICATION_CHANNELS, BOT_URL

logger = logging.getLogger(__name__)


async def verificar_membresia_canales(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Verifica si el usuario es miembro de TODOS los canales de verificación

    Args:
        update: Update de Telegram
        context: Contexto de la aplicación

    Returns:
        bool: True si es miembro de TODOS los canales, False si le falta alguno
    """
    if not VERIFICATION_CHANNELS:
        return True

    user = update.effective_user
    canales_unicos = list(set(VERIFICATION_CHANNELS))

    if len(canales_unicos) == 0:
        return True

    verificacion_resultados = {}

    for canal_id in canales_unicos:
        try:
            member = await context.bot.get_chat_member(chat_id=canal_id, user_id=user.id)
            verificacion_resultados[canal_id] = member.status in ['member', 'administrator', 'creator']

        except TelegramError:
            verificacion_resultados[canal_id] = False
        except Exception as e:
            logger.error(f"Error verificando canal {canal_id}: {e}")
            verificacion_resultados[canal_id] = False

    return all(verificacion_resultados.values())


async def obtener_canales_faltantes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> list:
    """
    Obtiene los canales que el usuario NO ha verificado aún

    Args:
        update: Update de Telegram
        context: Contexto de la aplicación

    Returns:
        list: Lista de IDs de canales que el usuario no ha verificado
    """
    user = update.effective_user
    canales_unicos = list(set(VERIFICATION_CHANNELS))
    canales_faltantes = []

    for canal_id in canales_unicos:
        try:
            member = await context.bot.get_chat_member(chat_id=canal_id, user_id=user.id)

            if member.status not in ['member', 'administrator', 'creator']:
                canales_faltantes.append(canal_id)

        except TelegramError:
            canales_faltantes.append(canal_id)
        except Exception as e:
            logger.error(f"Error verificando canal {canal_id}: {e}")
            canales_faltantes.append(canal_id)

    return canales_faltantes


async def obtener_info_canales_verificacion(context: ContextTypes.DEFAULT_TYPE) -> list:
    """
    Obtiene información de todos los canales de verificación

    Args:
        context: Contexto de la aplicación

    Returns:
        list: Lista de dicts con información de canales
    """
    canales_unicos = list(set(VERIFICATION_CHANNELS))
    canales_info = []

    for canal_id in canales_unicos:
        try:
            chat = await context.bot.get_chat(canal_id)
            nombre_canal = chat.title or f"Canal {canal_id}"
            enlace_canal = chat.username

            canales_info.append({
                'id': canal_id,
                'nombre': nombre_canal,
                'username': enlace_canal
            })

        except Exception as e:
            logger.error(f"Error obteniendo info del canal {canal_id}: {e}")
            canales_info.append({
                'id': canal_id,
                'nombre': f"Canal {canal_id}",
                'username': None
            })

    return canales_info


async def mostrar_alerta_union_canales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Muestra mensaje pidiendo al usuario que se una a los canales faltantes

    Args:
        update: Update de Telegram
        context: Contexto de la aplicación
    """
    try:
        if not VERIFICATION_CHANNELS:
            return

        # Obtener canales faltantes
        canales_faltantes = await obtener_canales_faltantes(update, context)

        if not canales_faltantes:
            return

        botones = []
        canales_procesados = []
        canales_info = await obtener_info_canales_verificacion(context)

        # Construir lista de botones solo con canales faltantes
        for info in canales_info:
            try:
                canal_id = info['id']
                nombre_canal = info['nombre']
                enlace_canal = info['username']

                # Solo mostrar botón si el usuario NO está en este canal
                if canal_id not in canales_faltantes:
                    continue

                # Evitar duplicados
                if nombre_canal in canales_procesados:
                    continue

                canales_procesados.append(nombre_canal)

                if enlace_canal:
                    url_canal = f"https://t.me/{enlace_canal}"
                    botones.append([InlineKeyboardButton(f"🚀 {nombre_canal}", url=url_canal)])

            except Exception as e:
                logger.error(f"Error procesando canal: {e}")
                continue

        if not botones:
            await update.effective_message.reply_text(
                "❌ No se pudieron cargar los canales de verificación.\n"
                "Contacta al administrador."
            )
            return

        keyboard = InlineKeyboardMarkup(botones)

        mensaje_canales = "\n".join([f"• {nombre}" for nombre in canales_procesados])

        canales_faltantes_count = len(canales_faltantes)
        canales_totales = len(list(set(VERIFICATION_CHANNELS)))

        mensaje_texto = (
            "🔒 **Debes unirte a nuestros canales oficiales para usar el bot**\n\n"
            f"**Canales que te faltan ({canales_faltantes_count}/{canales_totales}):**\n{mensaje_canales}\n\n"
            "Una vez que te hayas unido a todos, intenta de nuevo."
        )

        await update.effective_message.reply_text(
            mensaje_texto,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Error en mostrar_alerta_union_canales: {e}", exc_info=True)
        try:
            await update.effective_message.reply_text(
                "❌ Debes unirte a nuestros canales oficiales para acceder a este contenido."
            )
        except Exception as e2:
            logger.error(f"Error en fallback de alerta: {e2}")


def obtener_canales_verificacion_info() -> dict:
    """
    Obtiene información sobre los canales de verificación configurados

    Returns:
        dict: Información de configuración de verificación
    """
    canales_unicos = list(set(VERIFICATION_CHANNELS))

    return {
        'canales_totales': len(canales_unicos),
        'canales_ids': canales_unicos,
        'verificacion_activa': bool(canales_unicos)
    }