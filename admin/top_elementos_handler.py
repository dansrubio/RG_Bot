"""
Handler del comando /top_all y específicos por almacén
TOP 100 elementos por usuarios únicos. Muestra 20 por página.
"""
import logging
import html
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from cachetools import TTLCache

from config import BOT_URL, ADMINISTRATION_GROUP
from database.base import get_database

logger = logging.getLogger(__name__)

# Constantes de paginación
TOTAL_JUEGOS = 100
POR_PAGINA = 20
TOTAL_PAGINAS = TOTAL_JUEGOS // POR_PAGINA

_cache_top: TTLCache = TTLCache(maxsize=1000, ttl=7200)
_DIGIT_EMOJI = ["0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]


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


def _numero_emoji(n: int) -> str:
    tens, units = divmod(n, 10)
    if tens <= 9 and units <= 9:
        return f"{_DIGIT_EMOJI[tens]}{_DIGIT_EMOJI[units]}"
    return f"{n}."


def _construir_texto(elementos: list, pagina: int, nombre_almacen: str) -> str:
    inicio = pagina * POR_PAGINA
    fin = inicio + POR_PAGINA
    segmento = elementos[inicio:fin]
    rango_inicio = inicio + 1
    rango_fin = min(fin, len(elementos))

    lineas = [
        f"🏆 <b>TOP {TOTAL_JUEGOS} MÁS DESCARGADOS [{nombre_almacen}]</b>",
        f"📄 Mostrando del <b>#{rango_inicio}</b> al <b>#{rango_fin}</b> • Página {pagina + 1}/{TOTAL_PAGINAS}",
        ""
    ]

    total_segmento = len(segmento)
    for i, elemento in enumerate(segmento):
        idx_global = inicio + i + 1
        nombre = elemento.get('nombre', 'Sin nombre')
        solicitudes = elemento.get('usuarios_unicos', 0)
        token = elemento.get('token', '')
        enlace = f"{BOT_URL}?start={token}" if token else BOT_URL

        nombre_esc = html.escape(str(nombre))
        enlace_esc = html.escape(str(enlace), quote=True)
        numero = _numero_emoji(idx_global)

        # Si es el top global, añadimos la etiqueta visual del almacén
        tag_almacen = f"<b>[{obtener_nombre_almacen(elemento.get('almacen_id'))}]</b> " if nombre_almacen == "GLOBAL" else ""

        lineas.append(f"{numero} - {tag_almacen}<a href=\"{enlace_esc}\"><b>{nombre_esc}</b></a>")
        lineas.append(f"   📊 <b>Solicitudes:</b> {solicitudes}")
        if i != total_segmento - 1:
            lineas.append("")

    return "\n".join(lineas)


def _construir_teclado(pagina: int, chat_id: int, msg_id: int) -> InlineKeyboardMarkup:
    ref = f"{chat_id}:{msg_id}"
    botones = []
    if pagina > 0:
        botones.append(InlineKeyboardButton("◀️ Anterior", callback_data=f"top_pag:{ref}:{pagina - 1}"))
    botones.append(InlineKeyboardButton(f"· {pagina + 1}/{TOTAL_PAGINAS} ·", callback_data="top_noop"))
    if pagina < TOTAL_PAGINAS - 1:
        botones.append(InlineKeyboardButton("Siguiente ▶️", callback_data=f"top_pag:{ref}:{pagina + 1}"))

    fila_paginas = [
        InlineKeyboardButton(
            "🔘" if p == pagina else str(p + 1),
            callback_data="top_noop" if p == pagina else f"top_pag:{ref}:{p}"
        )
        for p in range(TOTAL_PAGINAS)
    ]
    return InlineKeyboardMarkup([botones, fila_paginas])


async def _obtener_top_db(almacen_id: int) -> list | None:
    """Obtiene el top de un almacén en específico"""
    try:
        db = get_database()
        pipeline = [
            {"$match": {"almacen_id": almacen_id}},
            {"$lookup": {"from": "elemento_solicitudes", "localField": "_id", "foreignField": "elemento_id", "as": "solicitudes_info"}},
            {"$addFields": {"usuarios_unicos": {"$size": {"$setUnion": ["$solicitudes_info.user_id", []]}}}},
            {"$match": {"usuarios_unicos": {"$gt": 0}}},
            {"$sort": {"usuarios_unicos": -1}},
            {"$limit": TOTAL_JUEGOS},
            {"$project": {"nombre": 1, "token": 1, "usuarios_unicos": 1, "almacen_id": 1}}
        ]
        return list(db.elementos.aggregate(pipeline))
    except Exception as e:
        logger.error(f"Error en pipeline MongoDB: {e}", exc_info=True)
        return None


async def _obtener_top_global_db() -> list | None:
    """Obtiene el top mezclando todos los almacenes"""
    try:
        db = get_database()
        pipeline = [
            {"$lookup": {"from": "elemento_solicitudes", "localField": "_id", "foreignField": "elemento_id", "as": "solicitudes_info"}},
            {"$addFields": {"usuarios_unicos": {"$size": {"$setUnion": ["$solicitudes_info.user_id", []]}}}},
            {"$match": {"usuarios_unicos": {"$gt": 0}}},
            {"$sort": {"usuarios_unicos": -1}},
            {"$limit": TOTAL_JUEGOS},
            {"$project": {"nombre": 1, "token": 1, "usuarios_unicos": 1, "almacen_id": 1}}
        ]
        return list(db.elementos.aggregate(pipeline))
    except Exception as e:
        logger.error(f"Error en pipeline MongoDB: {e}", exc_info=True)
        return None


async def _procesar_top(update: Update, context: ContextTypes.DEFAULT_TYPE, almacen_id: int, nombre_almacen: str):
    message = update.effective_message
    chat = update.effective_chat
    chat_id = chat.id if chat else None

    if not almacen_id or almacen_id == 0:
        await message.reply_text(f"❌ El almacén {nombre_almacen} no está configurado en el sistema.")
        return

    try:
        msg_cargando = await context.bot.send_message(chat_id=chat_id, text=f"⏳ Generando TOP 100 de {nombre_almacen}...")
        try:
            await message.delete()
        except Exception:
            pass

        elementos = await _obtener_top_db(almacen_id)

        if elementos is None:
            await msg_cargando.edit_text("❌ Error consultando la base de datos. Intenta más tarde.")
            return

        if not elementos:
            await msg_cargando.edit_text(f"ℹ️ Aún no hay solicitudes registradas para el almacén de {nombre_almacen}.")
            return

        msg_id = msg_cargando.message_id
        _cache_top[(chat_id, msg_id)] = {"elementos": elementos, "nombre_almacen": nombre_almacen}

        texto = _construir_texto(elementos, 0, nombre_almacen)
        teclado = _construir_teclado(0, chat_id, msg_id)

        await msg_cargando.edit_text(texto, parse_mode=ParseMode.HTML, reply_markup=teclado, disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Error procesando top: {e}", exc_info=True)


async def top_all_global(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat
    chat_id = chat.id if chat else None

    try:
        msg_cargando = await context.bot.send_message(chat_id=chat_id, text="⏳ Generando TOP 100 Global...")
        try:
            await message.delete()
        except Exception:
            pass

        elementos = await _obtener_top_global_db()

        if elementos is None:
            await msg_cargando.edit_text("❌ Error consultando la base de datos. Intenta más tarde.")
            return

        if not elementos:
            await msg_cargando.edit_text("ℹ️ Aún no hay solicitudes registradas en ningún almacén.")
            return

        msg_id = msg_cargando.message_id
        _cache_top[(chat_id, msg_id)] = {"elementos": elementos, "nombre_almacen": "GLOBAL"}

        texto = _construir_texto(elementos, 0, "GLOBAL")
        teclado = _construir_teclado(0, chat_id, msg_id)

        await msg_cargando.edit_text(texto, parse_mode=ParseMode.HTML, reply_markup=teclado, disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Error procesando top global: {e}", exc_info=True)


async def top_juegos_pc(update, context): await _procesar_top(update, context, ADMINISTRATION_GROUP, "PC")
async def top_ps4(update, context): await _procesar_top(update, context, int(os.getenv('ALMACEN_PS4', '0')), "PS4")
async def top_switch(update, context): await _procesar_top(update, context, int(os.getenv('ALMACEN_SWITCH', '0')), "Switch")
async def top_canaima(update, context): await _procesar_top(update, context, int(os.getenv('ALMACEN_CANAIMA', '0')), "Canaima")
async def top_audiovisuales(update, context): await _procesar_top(update, context, int(os.getenv('ALMACEN_AUDIOVISUALES', '0')), "Audiovisuales")


async def top_juegos_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "top_noop":
        return

    try:
        _, chat_id_str, msg_id_str, pagina_str = query.data.split(":")
        chat_id, msg_id, pagina = int(chat_id_str), int(msg_id_str), int(pagina_str)
    except ValueError:
        logger.warning(f"Callback con formato inesperado: {query.data}")
        return

    clave = (chat_id, msg_id)
    if clave not in _cache_top:
        await query.edit_message_text("⚠️ El ranking expiró. Usa el comando nuevamente para regenerarlo.")
        return

    if not (0 <= pagina < TOTAL_PAGINAS):
        return

    data = _cache_top[clave]
    elementos = data["elementos"]
    nombre_almacen = data["nombre_almacen"]

    texto = _construir_texto(elementos, pagina, nombre_almacen)
    teclado = _construir_teclado(pagina, chat_id, msg_id)

    try:
        await query.edit_message_text(texto, parse_mode=ParseMode.HTML, reply_markup=teclado, disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Error editando mensaje en callback: {e}", exc_info=True)


def register_top_elementos_handler(application):
    application.add_handler(CommandHandler("top_all", top_all_global))
    application.add_handler(CommandHandler("top_pc", top_juegos_pc))
    application.add_handler(CommandHandler("top_ps4", top_ps4))
    application.add_handler(CommandHandler("top_switch", top_switch))
    application.add_handler(CommandHandler("top_canaima", top_canaima))
    application.add_handler(CommandHandler("top_audiovisuales", top_audiovisuales))
    application.add_handler(CallbackQueryHandler(top_juegos_callback, pattern=r"^top_(pag|noop)"))