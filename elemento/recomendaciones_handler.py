"""
Módulo para el sistema de recomendación de elementos.
Permite a los administradores recomendar elementos y a los usuarios verlos.
"""

import logging
import math
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from html import escape

from config import is_admin, BOT_URL, ADMINISTRATION_GROUP, obtener_nombre_almacen
from database.crud.elemento_crud import ElementoCRUD

logger = logging.getLogger(__name__)

ITEMS_POR_PAGINA = 5

async def recomendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /recomendar <ID> - Activa la recomendación"""
    user = update.effective_user
    message = update.effective_message

    if not is_admin(user.id):
        await message.reply_text("❌ <b>Sin permisos:</b> Comando exclusivo para administradores.", parse_mode=ParseMode.HTML)
        return

    if len(context.args) != 1:
        await message.reply_text(
            "❌ <b>Uso incorrecto</b>\n\n"
            "✅ <b>Formato:</b> <code>/recomendar ID_elemento</code>",
            parse_mode=ParseMode.HTML
        )
        return

    elemento_id_str = context.args[0]
    
    elemento = ElementoCRUD.obtener_elemento_por_id(elemento_id_str)
    if not elemento:
        await message.reply_text(f"❌ No se encontró ningún elemento con el ID <code>{escape(elemento_id_str)}</code>.", parse_mode=ParseMode.HTML)
        return

    exito = ElementoCRUD.establecer_recomendacion(elemento_id_str, True)
    
    if exito:
        await message.reply_text(
            f"✅ <b>Añadido a recomendaciones</b>\n\n"
            f"🏷️ <b>Elemento:</b> <code>{escape(elemento['nombre'])}</code>",
            parse_mode=ParseMode.HTML
        )
    else:
        await message.reply_text("❌ Error de base de datos al actualizar la recomendación.")

async def quitar_recomendado_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /quitar_recomendado <ID> - Desactiva la recomendación"""
    user = update.effective_user
    message = update.effective_message

    if not is_admin(user.id):
        await message.reply_text("❌ <b>Sin permisos.</b>", parse_mode=ParseMode.HTML)
        return

    if len(context.args) != 1:
        await message.reply_text(
            "❌ <b>Uso incorrecto</b>\n\n"
            "✅ <b>Formato:</b> <code>/quitar_recomendado ID_elemento</code>",
            parse_mode=ParseMode.HTML
        )
        return

    elemento_id_str = context.args[0]
    
    elemento = ElementoCRUD.obtener_elemento_por_id(elemento_id_str)
    if not elemento:
        await message.reply_text(f"❌ No se encontró ningún elemento con el ID <code>{escape(elemento_id_str)}</code>.", parse_mode=ParseMode.HTML)
        return

    exito = ElementoCRUD.establecer_recomendacion(elemento_id_str, False)
    
    if exito:
        await message.reply_text(
            f"❌ <b>Eliminado de recomendaciones</b>\n\n"
            f"🏷️ <b>Elemento:</b> <code>{escape(elemento['nombre'])}</code>",
            parse_mode=ParseMode.HTML
        )
    else:
        await message.reply_text("❌ Error de base de datos al actualizar la recomendación.")

async def recomendados_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /recomendados - Muestra la lista paginada"""
    await _mostrar_pagina_recomendados(update, context, pagina=0)


async def recomendados_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los botones de paginación del menú de recomendados"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data.startswith("rec_page_"):
        pagina = int(data.split("_")[2])
        await _mostrar_pagina_recomendados(update, context, pagina=pagina, edit_message=True)


async def _mostrar_pagina_recomendados(update: Update, context: ContextTypes.DEFAULT_TYPE, pagina: int, edit_message: bool = False):
    """Lógica interna de generación de la lista y teclado inline"""
    elementos, total = ElementoCRUD.obtener_recomendados_paginados(pagina=pagina, limite=ITEMS_POR_PAGINA)

    if total == 0:
        texto = "🌟 <b>Elementos Recomendados</b>\n\nActualmente no hay elementos en la lista de recomendados."
        if edit_message:
            await update.callback_query.edit_message_text(texto, parse_mode=ParseMode.HTML)
        else:
            await update.effective_message.reply_text(texto, parse_mode=ParseMode.HTML)
        return

    total_paginas = math.ceil(total / ITEMS_POR_PAGINA)
    
    texto = f"🌟 <b>ELEMENTOS RECOMENDADOS</b> (Pág {pagina + 1}/{total_paginas})\n\n"
    
    for elem in elementos:
        nombre = escape(elem['nombre'])
        token = elem.get('token', '')
        link = f"{BOT_URL}?start={token}"
        solicitudes = elem.get('solicitudes', 0)
        almacen_id = elem.get('almacen_id')
        
        # Uso de la función centralizada
        almacen_display = obtener_nombre_almacen(almacen_id)
        
        texto += (
            f"🎮 <a href='{link}'><b>{nombre}</b></a>\n"
            f"📦 Almacén: <code>{almacen_display}</code> | 📊 Solicitudes: <code>{solicitudes}</code>\n\n"
        )

    botones = []
    if pagina > 0:
        botones.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"rec_page_{pagina - 1}"))
    if pagina < total_paginas - 1:
        botones.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"rec_page_{pagina + 1}"))

    keyboard = InlineKeyboardMarkup([botones]) if botones else None

    if edit_message:
        await update.callback_query.edit_message_text(texto, parse_mode=ParseMode.HTML, reply_markup=keyboard, disable_web_page_preview=True)
    else:
        await update.effective_message.reply_text(texto, parse_mode=ParseMode.HTML, reply_markup=keyboard, disable_web_page_preview=True)


def register_recomendaciones_handlers(application):
    """Registra todos los comandos y callbacks del sistema de recomendaciones"""
    application.add_handler(CommandHandler("recomendar", recomendar_command))
    application.add_handler(CommandHandler("quitar_recomendado", quitar_recomendado_command))
    application.add_handler(CommandHandler("recomendados", recomendados_command))
    application.add_handler(CallbackQueryHandler(recomendados_callback, pattern="^rec_page_"))