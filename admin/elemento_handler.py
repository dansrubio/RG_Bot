"""
Handler para gestión de elementos con MongoDB
Sistema completo de creación, eliminación y estadísticas
"""

import logging
import re
import secrets
import string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode, ChatType
from telegram.ext import CommandHandler, ContextTypes, CallbackQueryHandler
from telegram.error import TelegramError
from html import escape

from config import is_admin, is_moderator, ADMINISTRATION_GROUP, BOT_URL, ALMACENES_MAP
from database.crud.elemento_crud import ElementoCRUD, _resolver_id
from helpers.temp_storage import guardar_temp_data, obtener_temp_data

logger = logging.getLogger(__name__)


def generar_nombre_aleatorio() -> str:
    """Genera un nombre aleatorio de 8 caracteres"""
    caracteres = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(caracteres) for _ in range(8))


def extract_message_id_from_url(url_or_number: str) -> tuple[bool, int, str]:
    """Extrae el ID de mensaje desde una URL o número directo"""
    try:
        if url_or_number.isdigit():
            valor = int(url_or_number)
            if valor <= 0:
                return False, 0, "El ID de mensaje debe ser un número positivo"
            return True, valor, ""

        telegram_patterns = [
            r't\.me/c/\d+/(\d+)',
            r'telegram\.me/c/\d+/(\d+)',
            r't\.me/[^/]+/(\d+)',
            r'/(\d+)$'
        ]

        for pattern in telegram_patterns:
            match = re.search(pattern, url_or_number)
            if match:
                valor = int(match.group(1))
                if valor <= 0:
                    return False, 0, "El ID extraído debe ser un número positivo"
                return True, valor, ""

        return False, 0, f"No se pudo extraer ID del mensaje de: {url_or_number[:50]}..."

    except ValueError:
        return False, 0, "El valor extraído no es un número válido"
    except Exception as e:
        return False, 0, f"Error procesando: {str(e)}"


def user_has_permissions(user_id: int) -> bool:
    """Verifica si el usuario tiene permisos de administrador o moderador"""
    return is_admin(user_id) or is_moderator(user_id)


def is_authorized_chat(chat) -> bool:
    """Verifica si el chat está autorizado para ejecutar comandos"""
    return (
        chat.type == ChatType.PRIVATE or
        (ADMINISTRATION_GROUP and chat.id == ADMINISTRATION_GROUP) or
        (chat.id in ALMACENES_MAP) # NUEVO SISTEMA
    )


def obtener_elemento_id(elemento_data: dict):
    """Obtiene el ID del elemento de forma segura (MongoDB usa _id)"""
    return elemento_data.get('_id') or elemento_data.get('id', 0)


def _parsear_id_del_callback(data: str, prefijo: str):
    """
    Extrae el ID del callback_data de forma robusta.
    Funciona con IDs enteros y ObjectIds heredados (hex de 24 chars).
    """
    id_str = data[len(prefijo):]
    if id_str.lstrip('-').isdigit():
        return int(id_str)
    return id_str


async def generar_nombre_desde_mensaje(context: ContextTypes.DEFAULT_TYPE, id_inicio: int, user_id: int, almacen_id: int) -> str:
    """Genera el nombre del elemento desde el primer mensaje del rango"""
    try:
        if not almacen_id:
            return generar_nombre_aleatorio()

        mensaje_temporal = None
        try:
            mensaje_temporal = await context.bot.copy_message(
                chat_id=user_id,
                from_chat_id=almacen_id, # Actualizado
                message_id=id_inicio
            )

            mensaje_copiado = await context.bot.forward_message(
                chat_id=user_id,
                from_chat_id=user_id,
                message_id=mensaje_temporal.message_id
            )

            texto_mensaje = mensaje_copiado.caption or mensaje_copiado.text

            try:
                await context.bot.delete_message(chat_id=user_id, message_id=mensaje_temporal.message_id)
                await context.bot.delete_message(chat_id=user_id, message_id=mensaje_copiado.message_id)
            except Exception:
                pass

            if texto_mensaje:
                from helpers.text_utils import limpiar_para_elemento
                nombre = limpiar_para_elemento(texto_mensaje)
                if nombre and len(nombre) > 0:
                    return nombre

        except TelegramError:
            if mensaje_temporal:
                try:
                    await context.bot.delete_message(chat_id=user_id, message_id=mensaje_temporal.message_id)
                except Exception:
                    pass

        return generar_nombre_aleatorio()

    except Exception:
        return generar_nombre_aleatorio()


async def add_element_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /add para crear nuevos elementos (soporta múltiples rangos)"""
    user    = update.effective_user
    message = update.effective_message
    chat    = update.effective_chat

    try:
        if not is_authorized_chat(chat):
            await message.reply_text(
                "❌ <b>Chat no autorizado</b>\n\n"
                "Este comando solo funciona en:\n"
                "• 💬 Chat privado conmigo\n"
                f"• 🏢 Grupos configurados",
                parse_mode=ParseMode.HTML
            )
            return

        if not user_has_permissions(user.id):
            await message.reply_text(
                "❌ <b>Sin permisos</b>\n\n"
                f"Se requiere ser administrador o moderador.\n"
                f"Tu ID: <code>{user.id}</code>",
                parse_mode=ParseMode.HTML
            )
            return

        if len(context.args) < 2:
            await message.reply_text(
                "❌ <b>Uso incorrecto</b>\n\n"
                "✅ <b>Formato:</b> <code>/add id_inicio1 id_inicio2 id_inicio3 ... id_final_ultimo</code>\n\n"
                "📌 <b>Ejemplo:</b> <code>/add 70 80 90 100</code>\n"
                "Crea 3 elementos:\n"
                "• Elemento 1: 70 a 79 (80-1)\n"
                "• Elemento 2: 80 a 89 (90-1)\n"
                "• Elemento 3: 90 a 100 (sin -1, es el último)\n\n"
                "💡 Los rangos intermedios restan -1 automáticamente\n"
                "💡 El último ID se usa tal cual como ID final",
                parse_mode=ParseMode.HTML
            )
            return

        ids_inicio = []
        for arg in context.args:
            success, msg_id, error = extract_message_id_from_url(arg)
            if not success:
                await message.reply_text(
                    f"❌ <b>Error en ID</b>\n\n"
                    f"📥 <b>Entrada:</b> <code>{escape(arg)}</code>\n"
                    f"⚠️ <b>Error:</b> {escape(error)}",
                    parse_mode=ParseMode.HTML
                )
                return

            if not isinstance(msg_id, int) or msg_id <= 0:
                await message.reply_text(
                    f"❌ <b>ID inválido:</b> <code>{escape(arg)}</code>\n"
                    f"Los IDs de mensaje deben ser números enteros positivos.",
                    parse_mode=ParseMode.HTML
                )
                return

            ids_inicio.append(msg_id)

        if len(ids_inicio) < 2:
            await message.reply_text("❌ Se requieren al menos 2 IDs para crear elementos.")
            return

        for i in range(len(ids_inicio) - 1):
            if ids_inicio[i] >= ids_inicio[i + 1]:
                await message.reply_text(
                    f"❌ <b>IDs deben estar en orden ascendente</b>\n\n"
                    f"ID {i + 1}: <code>{ids_inicio[i]}</code> debe ser menor que ID {i + 2}: <code>{ids_inicio[i + 1]}</code>",
                    parse_mode=ParseMode.HTML
                )
                return

        rangos = []
        for i in range(len(ids_inicio) - 1):
            id_inicio = ids_inicio[i]
            id_final  = ids_inicio[i + 1] - 1 if i < len(ids_inicio) - 2 else ids_inicio[i + 1]

            if id_inicio > id_final:
                await message.reply_text(f"❌ Rango inválido: {id_inicio} a {id_final}")
                return

            rango_mensajes = id_final - id_inicio + 1
            if rango_mensajes > 250:
                await message.reply_text(
                    f"❌ <b>Rango muy grande</b>\n\n"
                    f"Elemento {i + 1}: {rango_mensajes} mensajes\n"
                    f"Máximo: 250 mensajes",
                    parse_mode=ParseMode.HTML
                )
                return

            rangos.append((id_inicio, id_final, rango_mensajes))

        # NUEVO SISTEMA: Identificar almacén dinámico
        almacen_activo = chat.id if chat.id in ALMACENES_MAP else ADMINISTRATION_GROUP

        msg_procesando = await message.reply_text(
            f"⏳ <b>Procesando {len(rangos)} elementos...</b>\n\n"
            f"🔎 Generando nombres desde mensajes...",
            parse_mode=ParseMode.HTML
        )

        elementos_creados = []

        for idx, (id_inicio, id_final, rango_mensajes) in enumerate(rangos, 1):
            nombre_base = await generar_nombre_desde_mensaje(context, id_inicio, user.id, almacen_activo)

            nombre      = None
            max_intentos = 20

            for intento in range(max_intentos):
                nombre_candidato = nombre_base if intento == 0 else f"{nombre_base}_{intento}"
                if not ElementoCRUD.obtener_elemento_por_nombre(nombre_candidato):
                    nombre = nombre_candidato
                    break

            if not nombre:
                await msg_procesando.edit_text(
                    f"❌ <b>Error generando nombre único</b>\n\n"
                    f"Elemento {idx}: '<code>{escape(nombre_base)}</code>' ya existe con demasiadas variaciones.",
                    parse_mode=ParseMode.HTML
                )
                return

            # Actualizado: Pasar almacen_id
            elemento_data = ElementoCRUD.crear_elemento(
                nombre=nombre,
                id_inicio=id_inicio,
                id_final=id_final,
                creador_id=user.id,
                almacen_id=almacen_activo
            )

            if elemento_data:
                elementos_creados.append(elemento_data)
            else:
                await msg_procesando.edit_text(
                    f"❌ <b>Error creando elemento {idx}</b>\n\n"
                    f"No se pudo crear el elemento con rango {id_inicio} a {id_final}",
                    parse_mode=ParseMode.HTML
                )
                return

        MAX_ELEMENTOS_RESUMEN = 3
        elementos_a_mostrar   = elementos_creados[:MAX_ELEMENTOS_RESUMEN]
        hay_mas_elementos     = len(elementos_creados) > MAX_ELEMENTOS_RESUMEN

        texto_resumen = f"✅ <b>{len(elementos_creados)} elementos creados exitosamente</b>\n\n"

        for idx, elem in enumerate(elementos_a_mostrar, 1):
            token         = elem.get('token', '')
            token_display = f"{token[:8]}...{token[-4:]}" if len(token) >= 12 else token
            elem_id       = obtener_elemento_id(elem)
            rango         = elem['id_final'] - elem['id_inicio'] + 1

            texto_resumen += (
                f"<b>Elemento {idx}:</b>\n"
                f"🏷️ <code>{escape(elem['nombre'])}</code>\n"
                f"🆔 ID: <code>{elem_id}</code> | 📊 {rango} msgs\n"
                f"🔑 <code>{token_display}</code>\n\n"
            )

        if hay_mas_elementos:
            texto_resumen += f"<i>...y {len(elementos_creados) - MAX_ELEMENTOS_RESUMEN} más</i>\n\n"

        texto_resumen += f"👤 {escape(user.first_name)}\n"

        elementos_ids = [obtener_elemento_id(e) for e in elementos_creados]
        temp_key      = guardar_temp_data(elementos_ids)

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Publicar todos", callback_data=f"pub_all_{temp_key}")],
            [InlineKeyboardButton("📋 Ver todos",      callback_data=f"detail_all_{temp_key}")]
        ])

        await msg_procesando.edit_text(
            texto_resumen,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Error en add_element_command: {e}", exc_info=True)
        await message.reply_text(
            f"❌ <b>Error interno</b>\n\n"
            f"Contacta al administrador del bot.\n"
            f"Error: <code>{escape(str(e)[:100])}</code>",
            parse_mode=ParseMode.HTML
        )


async def delete_element_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /del para eliminar elementos — soporta IDs enteros y ObjectIds heredados"""
    user    = update.effective_user
    message = update.effective_message
    chat    = update.effective_chat

    try:
        if not is_authorized_chat(chat) or not user_has_permissions(user.id):
            await message.reply_text("❌ Sin permisos o chat no autorizado.")
            return

        if len(context.args) != 1:
            await message.reply_text(
                "❌ <b>Uso:</b> <code>/del id</code>\n"
                "📌 <b>Ejemplo:</b> <code>/del 5</code>",
                parse_mode=ParseMode.HTML
            )
            return

        elemento_id_str = context.args[0].strip()
        if not elemento_id_str:
            await message.reply_text("❌ El ID proporcionado no es válido.")
            return

        elemento_id   = _resolver_id(elemento_id_str)
        elemento_data = ElementoCRUD.obtener_elemento_por_id(elemento_id)
        if not elemento_data:
            await message.reply_text(
                f"❌ No se encontró elemento con ID <code>{escape(elemento_id_str)}</code>.",
                parse_mode=ParseMode.HTML
            )
            return

        if not is_admin(user.id) and elemento_data['creador_id'] != user.id:
            await message.reply_text("❌ Solo puedes eliminar elementos que hayas creado.")
            return

        token          = elemento_data.get('token', '')
        token_display  = f"{token[:8]}...{token[-4:]}" if len(token) >= 12 else token
        rango_mensajes = elemento_data['id_final'] - elemento_data['id_inicio'] + 1
        elem_id        = obtener_elemento_id(elemento_data)

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Confirmar", callback_data=f"del_element_confirm_{elem_id}"),
            InlineKeyboardButton("❌ Cancelar",  callback_data=f"del_element_cancel_{elem_id}")
        ]])

        await message.reply_text(
            f"⚠️ <b>¿Confirmar eliminación?</b>\n\n"
            f"🏷️ <b>Nombre:</b> <code>{escape(elemento_data['nombre'])}</code>\n"
            f"🆔 <b>ID:</b> <code>{elem_id}</code>\n"
            f"🔑 <b>Token:</b> <code>{token_display}</code>\n"
            f"📊 <b>Solicitudes:</b> <code>{elemento_data['solicitudes']}</code>\n"
            f"📊 <b>Mensajes:</b> <code>{rango_mensajes}</code>\n\n"
            f"⚠️ Esta acción no se puede deshacer.\n"
            f"🔗 El enlace dejará de funcionar permanentemente.",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Error en delete_element_command: {e}")
        await message.reply_text("❌ Error interno procesando eliminación.")


async def delete_element_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback para confirmar o cancelar eliminación — soporta IDs enteros y ObjectIds"""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    data = query.data

    try:
        if not user_has_permissions(user.id):
            await query.edit_message_text("❌ Sin permisos.")
            return

        if data.startswith("del_element_confirm_"):
            elemento_id   = _parsear_id_del_callback(data, "del_element_confirm_")
            elemento_data = ElementoCRUD.obtener_elemento_por_id(elemento_id)
            if not elemento_data:
                await query.edit_message_text("❌ Elemento no encontrado.")
                return

            if not is_admin(user.id) and elemento_data['creador_id'] != user.id:
                await query.edit_message_text("❌ Sin permisos para eliminar este elemento.")
                return

            nombre        = elemento_data['nombre']
            token         = elemento_data.get('token', '')
            token_display = f"{token[:8]}...{token[-4:]}" if len(token) >= 12 else token
            solicitudes   = elemento_data['solicitudes']

            if ElementoCRUD.eliminar_elemento(elemento_id):
                await query.edit_message_text(
                    f"✅ <b>Elemento eliminado</b>\n\n"
                    f"🏷️ Nombre: <code>{escape(nombre)}</code>\n"
                    f"🆔 ID: <code>{elemento_id}</code>\n"
                    f"🔑 Token: <code>{token_display}</code>\n"
                    f"📊 Solicitudes: <code>{solicitudes}</code>\n"
                    f"👤 Eliminado por: {escape(user.first_name)}\n\n"
                    f"🔗 El enlace ya no funciona.",
                    parse_mode=ParseMode.HTML
                )
            else:
                await query.edit_message_text("❌ Error al eliminar elemento.")

        elif data.startswith("del_element_cancel_"):
            await query.edit_message_text("❌ Eliminación cancelada.")

    except Exception as e:
        logger.error(f"Error en callback: {e}")
        await query.edit_message_text("❌ Error interno.")


async def info_elementos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /info_elementos para ver información del sistema"""
    user    = update.effective_user
    message = update.effective_message
    chat    = update.effective_chat

    try:
        if not is_authorized_chat(chat) or not user_has_permissions(user.id):
            await message.reply_text("❌ Sin permisos.")
            return

        stats         = ElementoCRUD.obtener_estadisticas()
        security_info = ElementoCRUD.obtener_info_seguridad_sistema()

        await message.reply_text(
            f"📊 <b>SISTEMA DE ELEMENTOS SEGURO</b>\n\n"
            f"📊 <b>Estadísticas:</b>\n"
            f"• Total elementos: <code>{stats['total_elementos']}</code>\n"
            f"• Total solicitudes: <code>{stats['total_solicitudes']}</code>\n"
            f"• Promedio solicitudes: <code>{stats['promedio_solicitudes']}</code>\n"
            f"• Sin solicitudes: <code>{stats['elementos_sin_solicitudes']}</code>\n\n"
            f"🔒 <b>Seguridad:</b>\n"
            f"• Longitud tokens: <code>{security_info.get('longitud_token', 32)} caracteres</code>\n"
            f"• Caracteres posibles: <code>{security_info.get('caracteres_posibles', 62)}</code>\n"
            f"• Combinaciones: <code>{security_info.get('combinaciones_totales', '1.46e+57')}</code>\n"
            f"• Tokens activos: <code>{security_info.get('tokens_activos', 0)}</code>\n"
            f"• Todos con token: <code>{security_info.get('todos_con_token', True)}</code>\n\n"
            f"ℹ️ <b>Características:</b>\n"
            f"• Tokens únicos e impredecibles\n"
            f"• Enlaces imposibles de adivinar\n"
            f"• Seguridad criptográfica\n"
            f"• Sin patrones secuenciales\n"
            f"• Nombres automáticos desde mensajes\n"
            f"• Creación múltiple de elementos\n"
            f"• Base de datos MongoDB\n\n"
            f"🎯 <b>Formato:</b> <code>{escape(BOT_URL)}?start=[TOKEN]</code>",
            parse_mode=ParseMode.HTML
        )

    except Exception as e:
        logger.error(f"Error en info_elementos_command: {e}")
        await message.reply_text("❌ Error obteniendo información.")


async def stats_elementos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /stats_elementos para ver estadísticas (solo admin)"""
    user    = update.effective_user
    message = update.effective_message

    if not is_admin(user.id):
        await message.reply_text("❌ Solo administradores pueden usar este comando.")
        return

    stats = ElementoCRUD.obtener_estadisticas()

    texto = (
        f"📚 <b>Estadísticas del sistema de elementos</b>\n\n"
        f"• Total elementos: <code>{stats['total_elementos']}</code>\n"
        f"• Total solicitudes: <code>{stats['total_solicitudes']}</code>\n"
        f"• Promedio por elemento: <code>{stats['promedio_solicitudes']}</code>\n"
        f"• Elementos sin uso: <code>{stats['elementos_sin_solicitudes']}</code>\n"
        f"• Base de datos: MongoDB\n"
    )

    elemento_top = stats.get('elemento_mas_solicitado')
    if elemento_top:
        texto += (
            f"\n🏆 Más solicitado:\n"
            f"• Nombre: <b>{escape(elemento_top['nombre'])}</b>\n"
            f"• Solicitudes: <code>{elemento_top['solicitudes']}</code>\n"
            f"• Token: <code>{elemento_top['token_display']}</code>\n"
        )

    await message.reply_text(texto, parse_mode=ParseMode.HTML)


async def mostrar_elementos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra elementos con IDs visibles solo para administradores"""
    user      = update.effective_user
    es_admin  = is_admin(user.id)
    elementos = ElementoCRUD.listar_todos_elementos()

    if not elementos:
        await update.message.reply_text("No hay elementos disponibles.")
        return

    mensajes = []
    for elemento in elementos:
        mensaje = f"Nombre: {elemento['nombre']}\n"
        if es_admin:
            mensaje += f"ID: {elemento['_id']}\n"
        mensaje += f"Solicitudes: {elemento['solicitudes']}\n"
        mensajes.append(mensaje)

    await update.message.reply_text("\n\n".join(mensajes))


def register_elemento_handlers(application):
    """Registra todos los handlers de elementos"""
    application.add_handler(CommandHandler("add",             add_element_command))
    application.add_handler(CommandHandler("del",             delete_element_command))
    application.add_handler(CommandHandler("info_elementos",  info_elementos_command))
    application.add_handler(CommandHandler("stats_elementos", stats_elementos_command))
    application.add_handler(CommandHandler("mostrar_elementos", mostrar_elementos))
    application.add_handler(CallbackQueryHandler(delete_element_callback, pattern="^del_element_(confirm|cancel)_"))