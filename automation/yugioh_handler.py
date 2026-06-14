"""
Handler para el módulo Yu-Gi-Oh!

Comandos:
  /carta | /yugioh | /card | /ygo [nombre]  — busca cartas por nombre
  /carta_aleatoria | /ygo_random            — carta completamente aleatoria
  /arquetipo | /archetype [nombre]          — cartas de un arquetipo
  /sets | /expansion [nombre_set]           — cartas de una expansión
  /precio | /price [nombre]                 — precios de mercado de una carta

Flujo de búsqueda:
  1 resultado  → muestra la carta directamente con imagen.
  2+ resultados → panel de selección con lista numerada + botones + paginación.
  Selección    → muestra la carta elegida con imagen.
"""

import logging
import math

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from external_apis.yugioh import (
    buscar_carta_exacta,
    buscar_carta_por_id,
    buscar_cartas,
    buscar_por_arquetipo,
    buscar_por_set,
    formatear_carta,
    formatear_precios,
    obtener_carta_aleatoria,
    obtener_imagen_url,
)

logger = logging.getLogger(__name__)

# ── Paginación ────────────────────────────────────────────────────────────────
CARTAS_POR_PAGINA = 9

# ── Prefijos de callback_data ─────────────────────────────────────────────────
_CB_SELECCIONAR = "ygo_sel"   # ygo_sel:{card_id}
_CB_PAGINA      = "ygo_pag"   # ygo_pag:{pagina}
_CB_NOOP        = "ygo_noop"  # indicador de página (sin acción)

# ── Clave en user_data para los resultados de la búsqueda activa ──────────────
_KEY_RESULTADOS = "ygo_resultados"

# ── Mensajes ──────────────────────────────────────────────────────────────────
_MSG_SIN_NOMBRE    = "⚠️ Debes indicar el nombre de la carta.\n<b>Ejemplo:</b> <code>/carta Dark Magician</code>"
_MSG_SIN_ARQUETIPO = "⚠️ Debes indicar el nombre del arquetipo.\n<b>Ejemplo:</b> <code>/arquetipo Blue-Eyes</code>"
_MSG_SIN_SET       = "⚠️ Debes indicar el nombre de la expansión.\n<b>Ejemplo:</b> <code>/sets Legend of Blue Eyes White Dragon</code>"
_MSG_SIN_PRECIO    = "⚠️ Debes indicar el nombre exacto de la carta.\n<b>Ejemplo:</b> <code>/precio Dark Magician</code>"
_MSG_NO_ENCONTRADA = "❌ No encontré ninguna carta con ese nombre. Intenta con otro término."
_MSG_NO_ARQUETIPO  = "❌ No encontré cartas para ese arquetipo. Verifica el nombre exacto."
_MSG_NO_SET        = "❌ No encontré cartas para esa expansión. Verifica el nombre exacto."
_MSG_ERROR_API     = "⚠️ No se pudo conectar con la base de datos de cartas. Intenta más tarde."


# ── Utilidades ────────────────────────────────────────────────────────────────

async def _eliminar_mensaje(update: Update) -> None:
    """Borra el mensaje del comando. Falla silenciosamente si no hay permisos."""
    try:
        await update.message.delete()
    except Exception:
        pass


async def _enviar_con_imagen(context, chat_id: int, imagen_url: str, texto: str) -> None:
    """Envía foto + caption. Si supera 1024 chars manda el texto en mensaje aparte."""
    if len(texto) <= 1024:
        await context.bot.send_photo(chat_id, photo=imagen_url, caption=texto, parse_mode="HTML")
    else:
        await context.bot.send_photo(chat_id, photo=imagen_url)
        await context.bot.send_message(chat_id, texto, parse_mode="HTML")


# ── Panel de selección con paginación ─────────────────────────────────────────

async def _enviar_panel_seleccion(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    pagina: int,
    editar: bool,  # True = edita mensaje existente, False = mensaje nuevo
) -> None:
    """Construye y envía (o edita) el panel de selección numerado con paginación."""
    resultados: list[dict] = context.user_data.get(_KEY_RESULTADOS, [])
    total         = len(resultados)
    total_paginas = math.ceil(total / CARTAS_POR_PAGINA)

    inicio        = pagina * CARTAS_POR_PAGINA
    pagina_cartas = resultados[inicio: inicio + CARTAS_POR_PAGINA]

    # Lista numerada en el cuerpo del mensaje
    lista = "\n".join(
        f"<b>{i + 1}.</b> {carta['name']}"
        for i, carta in enumerate(pagina_cartas)
    )
    texto = f"🔍 Se encontraron <b>{total}</b> cartas. Elige una:\n\n{lista}"

    # Botones numéricos agrupados en filas de 3 → máximo 3 filas para 9 cartas
    nums    = [
        InlineKeyboardButton(str(i + 1), callback_data=f"{_CB_SELECCIONAR}:{carta['id']}")
        for i, carta in enumerate(pagina_cartas)
    ]
    botones = [nums[i: i + 3] for i in range(0, len(nums), 3)]

    # Fila de navegación debajo (solo si hay más de una página)
    if total_paginas > 1:
        nav = []
        if pagina > 0:
            nav.append(InlineKeyboardButton("◀️ Anterior", callback_data=f"{_CB_PAGINA}:{pagina - 1}"))
        nav.append(InlineKeyboardButton(f"{pagina + 1} / {total_paginas}", callback_data=_CB_NOOP))
        if pagina < total_paginas - 1:
            nav.append(InlineKeyboardButton("Siguiente ▶️", callback_data=f"{_CB_PAGINA}:{pagina + 1}"))
        botones.append(nav)

    teclado = InlineKeyboardMarkup(botones)

    if editar:
        await update.callback_query.edit_message_text(texto, parse_mode="HTML", reply_markup=teclado)
    else:
        await update.effective_chat.send_message(texto, parse_mode="HTML", reply_markup=teclado)


# ── Mostrar carta completa ────────────────────────────────────────────────────

async def _mostrar_carta_por_id(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    card_id: int,
    desde_callback: bool = False,
) -> None:
    """Consulta la carta por id y la envía con imagen y datos formateados."""
    try:
        carta = await buscar_carta_por_id(card_id)
    except Exception as e:
        logger.error(f"Error al obtener carta id={card_id}: {e}")
        if desde_callback:
            await update.callback_query.edit_message_text(_MSG_ERROR_API)
        else:
            await update.effective_chat.send_message(_MSG_ERROR_API)
        return

    if not carta:
        if desde_callback:
            await update.callback_query.edit_message_text(_MSG_NO_ENCONTRADA)
        else:
            await update.effective_chat.send_message(_MSG_NO_ENCONTRADA)
        return

    texto      = formatear_carta(carta)
    imagen_url = obtener_imagen_url(carta)
    chat_id    = update.effective_chat.id

    if desde_callback:
        await update.callback_query.delete_message()  # borra el panel antes de mostrar la carta

    if imagen_url:
        await _enviar_con_imagen(context, chat_id, imagen_url, texto)
    else:
        await context.bot.send_message(chat_id, texto, parse_mode="HTML")


# ── Lógica compartida: buscar → panel o carta directa ────────────────────────

async def _flujo_busqueda(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    resultados: list[dict],
    msg_no_encontrado: str,
) -> None:
    """
    Recibe una lista de resultados ya obtenida y decide si mostrar
    la carta directo (1 resultado) o el panel de selección (2+).
    """
    if not resultados:
        await update.effective_chat.send_message(msg_no_encontrado)
        return

    if len(resultados) == 1:
        await _mostrar_carta_por_id(update, context, resultados[0]["id"])
        return

    context.user_data[_KEY_RESULTADOS] = resultados
    await _enviar_panel_seleccion(update, context, pagina=0, editar=False)


# ── Comando /carta ─────────────────────────────────────────────────────────────

async def carta_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Busca cartas por nombre — /carta | /yugioh | /card | /ygo [nombre]"""
    await _eliminar_mensaje(update)
    nombre = " ".join(context.args).strip() if context.args else ""

    if not nombre:
        await update.effective_chat.send_message(_MSG_SIN_NOMBRE, parse_mode="HTML")
        return

    await context.bot.send_chat_action(update.effective_chat.id, action="typing")

    try:
        resultados = await buscar_cartas(nombre)
    except Exception as e:
        logger.error(f"Error al consultar YGOPRODeck: {e}")
        await update.effective_chat.send_message(_MSG_ERROR_API)
        return

    await _flujo_busqueda(update, context, resultados, _MSG_NO_ENCONTRADA)


# ── Comando /carta_aleatoria ───────────────────────────────────────────────────

async def carta_aleatoria_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envía una carta completamente aleatoria — /carta_aleatoria | /ygo_random"""
    await _eliminar_mensaje(update)
    await context.bot.send_chat_action(update.effective_chat.id, action="typing")

    try:
        carta = await obtener_carta_aleatoria()
    except Exception as e:
        logger.error(f"Error al obtener carta aleatoria: {e}")
        await update.effective_chat.send_message(_MSG_ERROR_API)
        return

    if not carta:
        await update.effective_chat.send_message(_MSG_ERROR_API)
        return

    texto      = formatear_carta(carta)
    imagen_url = obtener_imagen_url(carta)
    chat_id    = update.effective_chat.id

    if imagen_url:
        await _enviar_con_imagen(context, chat_id, imagen_url, texto)
    else:
        await context.bot.send_message(chat_id, texto, parse_mode="HTML")


# ── Comando /arquetipo ─────────────────────────────────────────────────────────

async def arquetipo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lista cartas de un arquetipo — /arquetipo | /archetype [nombre]"""
    await _eliminar_mensaje(update)
    nombre = " ".join(context.args).strip() if context.args else ""

    if not nombre:
        await update.effective_chat.send_message(_MSG_SIN_ARQUETIPO, parse_mode="HTML")
        return

    await context.bot.send_chat_action(update.effective_chat.id, action="typing")

    try:
        resultados = await buscar_por_arquetipo(nombre)
    except Exception as e:
        logger.error(f"Error buscando arquetipo '{nombre}': {e}")
        await update.effective_chat.send_message(_MSG_ERROR_API)
        return

    await _flujo_busqueda(update, context, resultados, _MSG_NO_ARQUETIPO)


# ── Comando /sets ──────────────────────────────────────────────────────────────

async def sets_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lista cartas de una expansión — /sets | /expansion [nombre_set]"""
    await _eliminar_mensaje(update)
    nombre = " ".join(context.args).strip() if context.args else ""

    if not nombre:
        await update.effective_chat.send_message(_MSG_SIN_SET, parse_mode="HTML")
        return

    await context.bot.send_chat_action(update.effective_chat.id, action="typing")

    try:
        resultados = await buscar_por_set(nombre)
    except Exception as e:
        logger.error(f"Error buscando set '{nombre}': {e}")
        await update.effective_chat.send_message(_MSG_ERROR_API)
        return

    await _flujo_busqueda(update, context, resultados, _MSG_NO_SET)


# ── Comando /precio ────────────────────────────────────────────────────────────

async def precio_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra precios de mercado de una carta — /precio | /price [nombre exacto]"""
    await _eliminar_mensaje(update)
    nombre = " ".join(context.args).strip() if context.args else ""

    if not nombre:
        await update.effective_chat.send_message(_MSG_SIN_PRECIO, parse_mode="HTML")
        return

    await context.bot.send_chat_action(update.effective_chat.id, action="typing")

    try:
        carta = await buscar_carta_exacta(nombre)
    except Exception as e:
        logger.error(f"Error buscando precio de '{nombre}': {e}")
        await update.effective_chat.send_message(_MSG_ERROR_API)
        return

    if not carta:
        await update.effective_chat.send_message(_MSG_NO_ENCONTRADA)
        return

    texto      = formatear_precios(carta)
    imagen_url = obtener_imagen_url(carta)
    chat_id    = update.effective_chat.id

    if imagen_url:
        await context.bot.send_photo(chat_id, photo=imagen_url, caption=texto, parse_mode="HTML")
    else:
        await context.bot.send_message(chat_id, texto, parse_mode="HTML")


# ── Callbacks de los botones ──────────────────────────────────────────────────

async def _callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja los presses de botones del panel de selección."""
    query = update.callback_query
    await query.answer()  # quitar el "reloj de carga" del botón

    datos = query.data

    if datos == _CB_NOOP:  # botón indicador de página → sin acción
        return

    if datos.startswith(f"{_CB_PAGINA}:"):  # cambio de página
        pagina = int(datos.split(":")[1])
        await _enviar_panel_seleccion(update, context, pagina=pagina, editar=True)
        return

    if datos.startswith(f"{_CB_SELECCIONAR}:"):  # selección de carta
        card_id = int(datos.split(":")[1])
        await query.edit_message_text("⏳ Cargando carta…")
        await _mostrar_carta_por_id(update, context, card_id, desde_callback=True)


# ── Registro de handlers ──────────────────────────────────────────────────────

def register_yugioh_handler(app: Application) -> None:
    """Registra todos los comandos y callbacks del módulo Yu-Gi-Oh!."""
    app.add_handler(CommandHandler(["carta", "yugioh", "card", "ygo"],      carta_command))
    app.add_handler(CommandHandler(["carta_aleatoria", "ygo_random"],        carta_aleatoria_command))
    app.add_handler(CommandHandler(["arquetipo", "archetype"],               arquetipo_command))
    app.add_handler(CommandHandler(["sets", "expansion"],                    sets_command))
    app.add_handler(CommandHandler(["precio", "price"],                      precio_command))
    app.add_handler(CallbackQueryHandler(_callback_handler, pattern=r"^ygo_"))
