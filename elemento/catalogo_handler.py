"""
Comando /catalogo — Accesible para todos los usuarios
Sistema de navegación por letra inicial (A-Z) con paginación en MongoDB.
"""

import logging
import os
from math import ceil
from time import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from database.crud.elemento_crud import ElementoCRUD
from database.base import MOTOR_AVAILABLE
# SE AGREGÓ: obtener_nombre_almacen
from config import ADMINISTRATION_GROUP, obtener_nombre_almacen

logger = logging.getLogger(__name__)

ELEMENTOS_POR_PAGINA = 25
LETRAS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + ["#"]
CACHE_LETRAS_TTL = 600

MODO_ASYNC = MOTOR_AVAILABLE
if MODO_ASYNC:
    logger.info("✅ Motor disponible - Usando paginación async")
else:
    logger.info("⚠️ Motor no disponible - Usando fallback sincrónico")

# SE ELIMINÓ: La función duplicada obtener_nombre_almacen() que estaba aquí.

async def _obtener_letras_disponibles(context: ContextTypes.DEFAULT_TYPE) -> dict:
    cache_key = "catalogo_letras_cache"
    ahora = time()
    
    if cache_key in context.bot_data:
        cache = context.bot_data[cache_key]
        si_es_valido = (ahora - cache.get("timestamp", 0)) < CACHE_LETRAS_TTL
        if si_es_valido:
            return cache["letras"]
    
    logger.debug("🔄 Refrescando letras disponibles...")
    if MODO_ASYNC:
        letras = await ElementoCRUD.obtener_todas_las_letras_disponibles_async()
    else:
        letras = ElementoCRUD.obtener_todas_las_letras_disponibles_sync()
    
    context.bot_data[cache_key] = {"letras": letras, "timestamp": ahora}
    return letras


async def _contar_por_letra(letra: str) -> int:
    if MODO_ASYNC:
        return await ElementoCRUD.contar_por_letra_async(letra)
    else:
        return ElementoCRUD.contar_por_letra_sync(letra)


async def _obtener_elementos_pagina(letra: str, pagina: int) -> list:
    if MODO_ASYNC:
        return await ElementoCRUD.listar_por_letra_paginado_async(letra, pagina, ELEMENTOS_POR_PAGINA)
    else:
        return ElementoCRUD.listar_por_letra_pagina_sync(letra, pagina, ELEMENTOS_POR_PAGINA)


async def _teclado_completo(letras_disponibles: dict, letra_activa: str, pagina: int, total_paginas: int) -> InlineKeyboardMarkup:
    filas = []
    fila_actual = []
    
    for l in LETRAS:
        if l not in letras_disponibles:
            continue
        
        label = f"● {l}" if l == letra_activa else l
        fila_actual.append(InlineKeyboardButton(label, callback_data=f"cat:{l}:0"))
        
        if len(fila_actual) == 7:
            filas.append(fila_actual)
            fila_actual = []
    
    if fila_actual:
        filas.append(fila_actual)
    
    if total_paginas > 1:
        nav = []
        if pagina > 0:
            nav.append(InlineKeyboardButton("◀️ Anterior", callback_data=f"cat:{letra_activa}:{pagina - 1}"))
        nav.append(InlineKeyboardButton(f"📄 {pagina + 1} / {total_paginas}", callback_data="cat:noop:0"))
        if pagina < total_paginas - 1:
            nav.append(InlineKeyboardButton("Siguiente ▶️", callback_data=f"cat:{letra_activa}:{pagina + 1}"))
        filas.append(nav)
    
    return InlineKeyboardMarkup(filas)


async def _construir_texto(elementos: list, letra: str, pagina: int, total_elementos_letra: int, total_paginas: int, bot_username: str) -> str:
    inicio = pagina * ELEMENTOS_POR_PAGINA
    ancho_num = len(str(total_elementos_letra))
    num_desde = inicio + 1
    num_hasta = min(inicio + ELEMENTOS_POR_PAGINA, total_elementos_letra)
    
    titulo = "Sección <b>#</b>" if letra == "#" else f"Sección <b>{letra}</b>"
    
    encabezado = (
        f"🎮 <b>CATÁLOGO DE ELEMENTOS</b>\n"
        f"┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        f"  {titulo}  •  <b>{total_elementos_letra}</b> elemento{'s' if total_elementos_letra != 1 else ''}\n"
        f"  📄 Página <b>{pagina + 1}</b> de <b>{total_paginas}</b>  •  mostrando <b>{num_desde}–{num_hasta}</b>\n"
        f"┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n\n"
    )
    
    lineas = []
    for i, elem in enumerate(elementos, start=inicio + 1):
        nombre = elem.get("nombre", "Sin nombre")
        almacen = obtener_nombre_almacen(elem.get("almacen_id"))
        token = elem.get("token", "")
        url = f"https://t.me/{bot_username}?start={token}"
        num = str(i).zfill(ancho_num)
        lineas.append(f"<b>{num}</b> - <b>[{almacen}]</b> <a href=\"{url}\">{nombre}</a>")
    
    cuerpo = "\n".join(lineas)
    pie = (
        f"\n\n┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄\n"
        f"💡 <i>Toca un elemento para solicitarlo al bot</i>"
    )
    
    return encabezado + cuerpo + pie


async def _obtener_bot_username(context) -> str:
    if "bot_username" not in context.bot_data:
        bot = await context.bot.get_me()
        context.bot_data["bot_username"] = bot.username
    return context.bot_data["bot_username"]


async def cmd_catalogo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    letras_disponibles = await _obtener_letras_disponibles(context)
    
    if not letras_disponibles:
        await update.message.reply_text("📭 El catálogo está vacío por el momento.")
        return
    
    primera_letra = next((l for l in LETRAS if l in letras_disponibles), None)
    if not primera_letra:
        await update.message.reply_text("📭 El catálogo está vacío por el momento.")
        return
    
    context.user_data["catalogo"] = {"letra": primera_letra, "pagina": 0}
    
    total_elementos = await _contar_por_letra(primera_letra)
    total_paginas = ceil(total_elementos / ELEMENTOS_POR_PAGINA)
    
    elementos_pagina = await _obtener_elementos_pagina(primera_letra, 0)
    bot_username = await _obtener_bot_username(context)
    
    texto = await _construir_texto(elementos_pagina, primera_letra, 0, total_elementos, total_paginas, bot_username)
    teclado = await _teclado_completo(letras_disponibles, primera_letra, 0, total_paginas)
    
    await update.message.reply_text(texto, parse_mode="HTML", reply_markup=teclado, disable_web_page_preview=True)


async def callback_catalogo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    _, letra, pagina_str = query.data.split(":")
    pagina = int(pagina_str)
    
    if letra == "noop":
        return
    
    letras_disponibles = await _obtener_letras_disponibles(context)
    
    if letra not in letras_disponibles:
        await query.answer("Sin elementos para esta letra.", show_alert=True)
        return
    
    total_elementos = await _contar_por_letra(letra)
    total_paginas = ceil(total_elementos / ELEMENTOS_POR_PAGINA)
    pagina = max(0, min(pagina, total_paginas - 1)) if total_paginas > 0 else 0
    
    elementos_pagina = await _obtener_elementos_pagina(letra, pagina)
    context.user_data["catalogo"] = {"letra": letra, "pagina": pagina}
    
    bot_username = await _obtener_bot_username(context)
    nuevo_texto = await _construir_texto(elementos_pagina, letra, pagina, total_elementos, total_paginas, bot_username)
    nuevo_teclado = await _teclado_completo(letras_disponibles, letra, pagina, total_paginas)
    
    try:
        await query.edit_message_text(nuevo_texto, parse_mode="HTML", reply_markup=nuevo_teclado, disable_web_page_preview=True)
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error editando mensaje: {e}")
            raise


def register_catalogo_handler(app: Application):
    app.add_handler(CommandHandler("catalogo", cmd_catalogo))
    app.add_handler(CallbackQueryHandler(callback_catalogo, pattern=r"^cat:"))