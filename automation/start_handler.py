"""
Handler para el comando /start con reenvío silencioso de archivos
Sistema con verificación de membresía al canal y bienvenida personalizada
Formato: ?start=[TOKEN] sin prefijo elemento_
Adaptado para MongoDB y Multi-Almacén
"""

import logging
import random
import asyncio
from pathlib import Path
from urllib.parse import quote
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, MessageEntity, Update
from telegram.constants import ParseMode
from telegram.ext import CommandHandler, ContextTypes
from telegram.helpers import escape_markdown
from telegram.error import TelegramError, RetryAfter

from config import BOT_URL, BOT_REGLAMENTO_URL, BOT_PRIVACIDAD_URL, ADMINISTRATION_GROUP, CANAL_ELEMENTOS, GP_ADMINS, TOPIC_LOG_SOLICITUDES, ALMACENES_MAP
from database.crud.elemento_crud import ElementoCRUD
from database.crud.usuario_crud import UsuarioCRUD
from helpers.verification_system import verificar_membresia_canales, mostrar_alerta_union_canales
from automation.verification_handler import PERMISOS_NORMAL

logger = logging.getLogger(__name__)


def _es_token_valido(token: str) -> bool:
    if not token or not isinstance(token, str):
        return False
    
    # Formato antiguo: exactamente 32 caracteres alfanuméricos
    if len(token) == 32 and token.isalnum():
        return True
    
    # Formato nuevo: secuencia_sufijo donde secuencia = 12 dígitos
    if '_' in token:
        parts = token.split('_', 1)  # Dividir en máximo 2 partes
        if len(parts) == 2:
            secuencia, sufijo = parts
            # Validar: secuencia debe ser 12 dígitos, sufijo entre 30-40 caracteres
            if len(secuencia) == 12 and secuencia.isdigit() and 30 <= len(sufijo) <= 40:
                return True
    
    return False


# NUEVA FUNCIÓN: Envía el reporte de manera silenciosa al grupo de staff
async def _notificar_solicitud_admin(context: ContextTypes.DEFAULT_TYPE, user, elemento_data, token: str):
    """Envía un log al tópico de administración cuando un elemento es solicitado"""
    try:
        if not GP_ADMINS or not TOPIC_LOG_SOLICITUDES:
            return

        # Construcción del usuario
        user_mention = f"<a href='tg://user?id={user.id}'>{html_escape(user.first_name)}</a>" if user.first_name else f"ID: <code>{user.id}</code>"
        username = f" (@{user.username})" if user.username else ""
        
        # Obtener el nombre del elemento
        nombre_elemento = elemento_data.get('nombre') or elemento_data.get('titulo') or "Elemento sin nombre"
        
        # Obtener el nombre del almacén
        almacen_id = elemento_data.get('almacen_id')
        # Intenta obtener el nombre desde la BD. Si no existe, lo busca en ALMACENES_MAP (asumiendo que es un diccionario).
        nombre_almacen = elemento_data.get('nombre_almacen')
        if not nombre_almacen:
            nombre_almacen = ALMACENES_MAP.get(almacen_id, "Almacén Principal") if isinstance(ALMACENES_MAP, dict) else str(almacen_id)

        # Texto del log simplificado
        texto_log = (
            f"👤 {user_mention}{username} / <code>{user.id}</code>\n\n"
            f"📦 <b>Elemento:</b> ({nombre_almacen}) <code>{nombre_elemento}</code>"
        )

        await context.bot.send_message(
            chat_id=GP_ADMINS,
            message_thread_id=TOPIC_LOG_SOLICITUDES,
            text=texto_log,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Error al enviar notificación de solicitud al grupo de admin: {e}")


def html_escape(text: str) -> str:
    """Escapa caracteres especiales para evitar errores en ParseMode.HTML"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def reenviar_archivos_silencioso(update: Update, context: ContextTypes.DEFAULT_TYPE, elemento_data: dict, token: str = None):
    """Reenvía archivos sin mostrar estadísticas al usuario y sugiere compartir el canal siempre"""
    try:
        user = update.effective_user
        chat = update.effective_chat

        id_inicio = elemento_data['id_inicio']
        id_final = elemento_data['id_final']

        # NUEVO SISTEMA: Obtener el almacén de origen dinámicamente
        almacen_origen = elemento_data.get('almacen_id') or ADMINISTRATION_GROUP

        if not almacen_origen:
            botones = None
            if token:
                botones = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Reintentar", url=f"{BOT_URL}?start={token}")
                ]])
            await update.effective_message.reply_text(
                "❌ Error de configuración del bot.\n"
                "Contacta al administrador.",
                reply_markup=botones
            )
            return

        archivos_enviados = 0
        errores = 0

        rango_total = id_final - id_inicio + 1
        mensaje_progreso = None

        if rango_total > 5:
            mensaje_progreso = await update.effective_message.reply_text("📤 Enviando archivos...")

        for message_id in range(id_inicio, id_final + 1):
            try:
                await context.bot.copy_message(
                    chat_id=chat.id,
                    from_chat_id=almacen_origen, # Actualizado
                    message_id=message_id
                )
                archivos_enviados += 1

            except RetryAfter as e:
                logger.warning(f"Rate limit de Telegram, esperando {e.retry_after} segundos")
                await asyncio.sleep(e.retry_after)
                try:
                    await context.bot.copy_message(
                        chat_id=chat.id,
                        from_chat_id=almacen_origen, # Actualizado
                        message_id=message_id
                    )
                    archivos_enviados += 1
                except TelegramError as retry_error:
                    errores += 1
                    logger.error(f"Error reenviando mensaje {message_id} tras recuperación: {retry_error}")

            except TelegramError as e:
                errores += 1
                error_msg = str(e).lower()

                if "message not found" in error_msg or "to copy not found" in error_msg:
                    pass  
                elif "bad request" in error_msg:
                    pass  
                else:
                    logger.error(f"Error reenviando mensaje {message_id}: {e}")

                if errores > 10:
                    logger.error(f"Demasiados errores reenviando a usuario {user.id}, deteniendo")
                    break

            await asyncio.sleep(0.05)

        if mensaje_progreso:
            try:
                await mensaje_progreso.delete()
            except:
                pass

        if archivos_enviados == 0:
            botones = None
            if token:
                botones = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Reintentar", url=f"{BOT_URL}?start={token}")
                ]])
            await update.effective_message.reply_text(
                "❌ No se pudieron enviar los archivos.\n"
                "El elemento puede tener IDs incorrectos.\n"
                "Contacta con quien te proporcionó el enlace.",
                reply_markup=botones
            )
            return
            
        share_url = "https://t.me/share/url?url=%F0%9F%91%80%20Bro%2C%20%C3%A9chale%20un%20ojo%20a%20este%20canal%20%F0%9F%91%89%20%40Refugio_Gamer%20%2F%20Es%20un%20catalogo%20para%20descargar%20GRATIS%20Juegos%20para%20PC"
        
        try:
            await update.effective_message.reply_text(
                "<b>🟡 ¿Te gusta o te resultó útil este servicio?</b>\n"
                "Compártelo con tus amigos y ayúdanos a llegar a más personas.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎯 Compartir", url=share_url)]
                ])
            )
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Error crítico reenviando archivos: {e}")
        botones = None
        if token:
            botones = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Reintentar", url=f"{BOT_URL}?start={token}")
            ]])
        await update.effective_message.reply_text(
            "❌ Error procesando los archivos.\n"
            "Contacta al administrador del bot.",
            reply_markup=botones
        )


async def mostrar_alerta_union_canales_con_reintentar(update: Update, context: ContextTypes.DEFAULT_TYPE, token: str):
    """
    Muestra mensaje pidiendo al usuario que se una a los canales faltantes
    con un botón de reintentar para verificar nuevamente
    """
    try:
        from helpers.verification_system import obtener_canales_faltantes, obtener_info_canales_verificacion
        from config import VERIFICATION_CHANNELS
        
        if not VERIFICATION_CHANNELS:
            return

        canales_faltantes = await obtener_canales_faltantes(update, context)

        if not canales_faltantes:
            return

        botones = []
        canales_procesados = []
        canales_info = await obtener_info_canales_verificacion(context)

        for info in canales_info:
            try:
                canal_id = info['id']
                nombre_canal = info['nombre']
                enlace_canal = info['username']

                if canal_id not in canales_faltantes:
                    continue

                if nombre_canal in canales_procesados:
                    continue

                canales_procesados.append(nombre_canal)

                if enlace_canal:
                    url_canal = f"https://t.me/{enlace_canal}"
                    botones.append([InlineKeyboardButton(f"🚀 {nombre_canal}", url=url_canal)])

            except Exception as e:
                logger.error(f"Error procesando canal: {e}")
                continue

        botones.append([InlineKeyboardButton("🔄 Reintentar verificación", url=f"{BOT_URL}?start={token}")])

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
            "Una vez que te hayas unido a todos, usa el botón de reintentar."
        )

        await update.effective_message.reply_text(
            mensaje_texto,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Error en mostrar_alerta_union_canales_con_reintentar: {e}", exc_info=True)
        try:
            await update.effective_message.reply_text(
                "❌ Debes unirte a nuestros canales oficiales para acceder a este contenido."
            )
        except Exception as e2:
            logger.error(f"Error en fallback de alerta: {e2}")


async def handle_start_elemento(update: Update, context: ContextTypes.DEFAULT_TYPE, token: str):
    """Procesa elementos con verificación de membresía - Adaptado para MongoDB"""
    try:
        user = update.effective_user

        if not _es_token_valido(token):
            botones = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Reintentar", url=f"{BOT_URL}?start={token}")
            ]])
            await update.effective_message.reply_text(
                "❌ Enlace inválido.\n"
                "Verifica que el enlace esté completo y correcto.",
                reply_markup=botones
            )
            return

        elemento_data = ElementoCRUD.obtener_elemento_por_token(token)

        if not elemento_data:
            botones = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Reintentar", url=f"{BOT_URL}?start={token}")
            ]])
            await update.effective_message.reply_text(
                "❌ Enlace no encontrado o expirado.\n"
                "Contacta con quien te proporcionó el enlace.",
                reply_markup=botones
            )
            return

        es_miembro = await verificar_membresia_canales(update, context)

        if not es_miembro:
            await mostrar_alerta_union_canales_con_reintentar(update, context, token)
            return

        ElementoCRUD.incrementar_solicitudes(token, user.id)

        # Disparar la notificación asíncrona hacia el grupo de staff de forma segura
        asyncio.create_task(_notificar_solicitud_admin(context, user, elemento_data, token))

        await reenviar_archivos_silencioso(update, context, elemento_data, token=token)

    except Exception as e:
        logger.error(f"Error manejando elemento {token[:8] if token else 'NONE'}...: {e}")
        botones = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Reintentar", url=f"{BOT_URL}?start={token}")
        ]])
        try:
            await update.effective_message.reply_text(
                "❌ Error procesando el elemento.\nIntenta de nuevo con el botón de abajo.",
                reply_markup=botones
            )
        except:
            pass


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler principal del comando /start con formato simplificado - Adaptado para MongoDB"""
    message = update.effective_message
    user = update.effective_user

    if not message or not user:
        return

    try:
        if not context.args or len(context.args) == 0:
            await mensaje_bienvenida_personalizada(update, context)
            return

        arg = context.args[0]

        if _es_token_valido(arg):
            await handle_start_elemento(update, context, arg)
            return

        elif arg.startswith('elemento_') and len(arg) == 41:
            token = arg[9:]
            await handle_start_elemento(update, context, token)
            return

        elif arg.startswith('elemento') and len(arg) > 8 and arg[8:].isdigit():
            elemento_id = int(arg[8:])
            elemento_data = ElementoCRUD.obtener_elemento_por_id(elemento_id)

            if elemento_data and elemento_data.get('token'):
                await handle_start_elemento(update, context, elemento_data['token'])
            else:
                botones = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔄 Reintentar", url=f"{BOT_URL}?start=elemento{elemento_id}")
                ]])
                await message.reply_text(
                    "❌ Enlace obsoleto no encontrado.\n"
                    "Solicita un enlace actualizado.",
                    reply_markup=botones
                )
            return

        elif arg.startswith('giveaway'):
            await message.reply_text("Sistema de sorteos no disponible.")
            return

        elif arg.startswith('verificar_'):
            try:
                _, group_id, user_id = arg.split('_')
                group_id = int(group_id)
                user_id = int(user_id)

                UsuarioCRUD.marcar_como_verificado(user_id, group_id)

                await context.bot.restrict_chat_member(
                    chat_id=group_id,
                    user_id=user_id,
                    permissions=PERMISOS_NORMAL
                )

                await message.reply_text(
                    "✅ ¡Verificación completada! Ya puedes participar en el grupo."
                )
            except ValueError:
                await message.reply_text(
                    "⚠️ Error procesando el enlace de verificación. Asegúrate de que sea correcto."
                )
            except Exception as e:
                logger.error(f"Error en la verificación: {e}")
                await message.reply_text(
                    "❌ Hubo un error completando la verificación. Intenta de nuevo más tarde."
                )
            return

        else:
            await message.reply_text(
                "⚠ Formato de enlace no reconocido.\n"
                "Verifica que el enlace esté completo."
            )
            return

    except Exception as e:
        logger.error(f"Error en start_command: {e}")
        await message.reply_text("❌ Error interno del bot.")


async def mensaje_bienvenida_personalizada(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envía mensaje de bienvenida + botones (sin imagen)"""
    message = update.effective_message
    user = update.effective_user

    try:
        safe_firstname = escape_markdown(user.first_name or "usuario", version=2)
        mention = f"[{safe_firstname}](tg://user?id={user.id})"

        raw_quote = (
            "🚀 Estoy aquí para ayudarte, mantener grupos y canales organizados, "
            "hacerte la vida más sencilla y, de paso, sorprenderte con "
            "notificaciones y herramientas útiles."
        )

        quote_escaped = escape_markdown(raw_quote, version=2)
        quote_block = f"> {quote_escaped}"

        comandos = escape_markdown(
            "📂 /catalogo — Ver el listado de elementos disponibles\n"
            "🏆 /top_juegos — Ver los juegos más descargados\n"
            "🎲 /juego_aleatorio — Recibir una recomendación aleatoria",
            version=2
        )

        caption = (
            f"👋 *Hola {mention}, Soy Rednite, tu bot de confianza*\\!\n"
            f"{quote_block}\n\n"
            f"*¿Qué puedo hacer por ti?*\n"
            f"{comandos}\n\n"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="🔒 Política de privacidad", url=BOT_PRIVACIDAD_URL)],
            [InlineKeyboardButton(text="📋 Reglamento", url=BOT_REGLAMENTO_URL)]
        ])

        # Se envía únicamente el texto
        await message.reply_text(
            text=caption,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Error al enviar bienvenida: {e}")
        try:
            await message.reply_text("👋 Hola — hubo un error mostrando la bienvenida.")
        except Exception:
            pass


def register_start_handler(application):
    """Registra el CommandHandler /start"""
    try:
        handler = CommandHandler("start", start_command)
        application.add_handler(handler)
    except Exception as e:
        logger.error(f"Error registrando start handler: {e}")