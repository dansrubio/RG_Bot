import re
import html
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatType, ParseMode
from telegram.ext import CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

from config import BOT_URL, is_admin, is_staff, ADMINISTRATION_GROUP
from database.base import get_database

logger = logging.getLogger(__name__)

# --- CONFIGURACIÓN ---
MAX_LONGITUD_TEXTO = 250
MAX_PALABRAS = 20
ELEMENTOS_POR_PAGINA = 5

_REGEX_SIMBOLOS = re.compile(r'[^\w\s]', re.UNICODE)


def obtener_nombre_almacen(almacen_id) -> str:
    """Traduce el ID del almacén a su nombre legible"""
    if not almacen_id or almacen_id == 0:
        return "PC"
    aid_str = str(almacen_id)
    if aid_str == str(ADMINISTRATION_GROUP): return "PC"
    if aid_str == str(os.getenv('ALMACEN_PS4', '')): return "PS4"
    if aid_str == str(os.getenv('ALMACEN_SWITCH', '')): return "Switch"
    if aid_str == str(os.getenv('ALMACEN_CANAIMA', '')): return "Canaima"
    if aid_str == str(os.getenv('ALMACEN_AUDIOVISUALES', '')): return "Audiovisuales"
    return "PC"


def _es_busqueda_spam(texto: str) -> bool:
    return len(texto) > MAX_LONGITUD_TEXTO or len(texto.split()) > MAX_PALABRAS


def _sanitizar_palabras(texto: str) -> list[str]:
    texto_limpio = _REGEX_SIMBOLOS.sub(' ', texto)
    return [re.escape(p) for p in texto_limpio.split() if p.strip()]


def _construir_query(palabras: list[str]) -> dict:
    condiciones = [
        {"$or": [{"nombre": {"$regex": p, "$options": "i"}},
                 {"informacion_completa": {"$regex": p, "$options": "i"}}]}
        for p in palabras
    ]
    return {"$and": condiciones} if len(condiciones) > 1 else condiciones[0]


def _desescapar_para_mostrar(palabras_escapadas: list[str]) -> str:
    return ' '.join(re.sub(r'\\(.)', r'\1', p) for p in palabras_escapadas)


async def _enviar_pagina(update_or_query, context: ContextTypes.DEFAULT_TYPE, page: int, query_text: str, mostrar_id: bool):
    db = get_database()
    palabras = _sanitizar_palabras(query_text)
    
    if not palabras:
        return

    query = _construir_query(palabras)
    
    skip = page * ELEMENTOS_POR_PAGINA
    cursor = db.elementos.find(query).sort("solicitudes", -1)
    resultados = list(cursor.skip(skip).limit(ELEMENTOS_POR_PAGINA))
    
    total_count = db.elementos.count_documents(query)
    hay_mas = (page + 1) * ELEMENTOS_POR_PAGINA < total_count

    if not resultados and page == 0:
        texto = "No se encontraron elementos."
        if isinstance(update_or_query, Update):
            await update_or_query.effective_message.reply_text(texto)
        else:
            await update_or_query.edit_message_text(texto)
        return

    terminos = _desescapar_para_mostrar(palabras)
    respuesta = f"🔎 Resultados para: <b>{html.escape(terminos)}</b>\n\n"
    
    for elemento in resultados:
        nombre = elemento.get("nombre", "Sin nombre")
        almacen = obtener_nombre_almacen(elemento.get("almacen_id"))
        solicitudes = elemento.get("solicitudes", 0)
        token = elemento.get("token", "")
        enlace = f"{BOT_URL}?start={token}" if token else BOT_URL
        elemento_id = str(elemento.get("_id", ""))

        respuesta += f"• <b>[{almacen}] {html.escape(nombre)}</b>\n   📊 Solicitudes: {solicitudes}\n"
        if mostrar_id and elemento_id:
            respuesta += f"   🆔 ID: <code>{html.escape(elemento_id)}</code>\n"
        respuesta += f"   ➡️ <a href='{enlace}'>Enlace</a>\n\n"

    botones = []
    if page > 0:
        botones.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"pag:{page-1}"))
    
    botones.append(InlineKeyboardButton(f"📄 {page + 1}", callback_data="ignore"))
    
    if hay_mas:
        botones.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"pag:{page+1}"))

    keyboard = InlineKeyboardMarkup([botones])

    if isinstance(update_or_query, Update):
        await update_or_query.effective_message.reply_text(respuesta, parse_mode=ParseMode.HTML, reply_markup=keyboard, disable_web_page_preview=True)
    else:
        await update_or_query.edit_message_text(respuesta, parse_mode=ParseMode.HTML, reply_markup=keyboard, disable_web_page_preview=True)


async def _manejar_busqueda_general(update: Update, context: ContextTypes.DEFAULT_TYPE, es_admin: bool):
    message = update.effective_message
    texto = ' '.join(context.args) if context.args else (message.text or "")
    
    if _es_busqueda_spam(texto):
        if es_admin: await message.reply_text("❌ Búsqueda demasiado larga.")
        return

    context.user_data['search_query'] = texto
    context.user_data['search_admin'] = es_admin
    
    await _enviar_pagina(update, context, 0, texto, mostrar_id=es_admin)


async def callback_paginacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "ignore": return
    
    page = int(query.data.split(":")[1])
    search_query = context.user_data.get('search_query', '')
    mostrar_id = context.user_data.get('search_admin', False)
    
    await _enviar_pagina(query, context, page, search_query, mostrar_id)


async def buscar_elemento_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    await _manejar_busqueda_general(update, context, es_admin=True)


async def buscar_elemento_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != ChatType.PRIVATE or is_staff(update.effective_user.id): return
    await _manejar_busqueda_general(update, context, es_admin=False)


def register_busqueda_elemento_handler(application):
    application.add_handler(CommandHandler("buscar", buscar_elemento_command))
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND, buscar_elemento_texto), group=1)
    application.add_handler(CallbackQueryHandler(callback_paginacion, pattern="^pag:"))