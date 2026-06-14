"""
Handler de la Pokédex interactiva.
Comandos: /pokemon /pkm
          /pkm_move  — stats y descripción de un movimiento
          /pkm_item  — efecto e imagen de un ítem
          /pkm_type  — tabla de fortalezas/debilidades por tipo
          /pkm_random — Pokémon aleatorio
Soporta navegación por evoluciones con botones inline que editan el mensaje.
"""

import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode

from external_apis.pokeapi import (
    obtener_datos_completos,
    obtener_debilidades,
    obtener_encuentros,
    obtener_movimiento,
    obtener_item,
    obtener_tipo,
    obtener_pokemon_aleatorio,
)

logger = logging.getLogger(__name__)

CALLBACK_PREFIX      = "pokedex"       # prefijo para navegación por evoluciones
CALLBACK_DEBILIDADES = "pdx_weak"      # prefijo para el botón de debilidades
CALLBACK_ENCUENTROS  = "pdx_enc"       # prefijo para el botón de encuentros


# ══════════════════════════════════════════════════════════════════════════════
# CONSTRUCCIÓN DEL MENSAJE — POKÉMON
# ══════════════════════════════════════════════════════════════════════════════

def _construir_caption(datos: dict) -> str:
    """Arma el texto del mensaje con HTML: negrita, emojis y descripción en cita"""

    # ── Encabezado con badge especial si aplica ────────────────────────────
    badge = ""
    if datos["es_mitico"]:
        badge = " 🌟"
    elif datos["es_legendario"]:
        badge = " ⭐"

    lineas = [f"<b>#{datos['id']:03d} — {datos['nombre_display']}{badge}</b>"]

    if datos["genera"]:  # categoría oficial: "Pokémon Ratón"
        lineas.append(f"<i>{datos['genera']}</i>")

    lineas.append("")

    # ── Tipos ──────────────────────────────────────────────────────────────
    tipos_str = "  |  ".join(datos["tipos"])
    lineas.append(f"🏷️ <b>Tipo:</b>  {tipos_str}")

    # ── Dimensiones ────────────────────────────────────────────────────────
    lineas.append(
        f"📏 <b>Altura:</b> {datos['altura_m']} m   "
        f"⚖️ <b>Peso:</b> {datos['peso_kg']} kg"
    )

    # ── Hábitat ────────────────────────────────────────────────────────────
    if datos["habitat"]:
        lineas.append(f"🗺️ <b>Hábitat:</b> {datos['habitat']}")

    # ── Grupos huevo ───────────────────────────────────────────────────────
    if datos["grupos_huevo"]:
        grupos_str = ", ".join(datos["grupos_huevo"])
        lineas.append(f"🥚 <b>Grupo huevo:</b> {grupos_str}")

    # ── Habilidades ────────────────────────────────────────────────────────
    habs = ", ".join(datos["habilidades"]) if datos["habilidades"] else "—"
    lineas.append(f"✨ <b>Habilidades:</b> {habs}")

    if datos["habilidades_ocultas"]:
        ocultas = ", ".join(datos["habilidades_ocultas"])
        lineas.append(f"🔒 <b>H. Oculta:</b> {ocultas}")

    lineas.append("")

    # ── Estadísticas base ──────────────────────────────────────────────────
    s = datos["stats"]

    fila1 = (
        f"❤️  PS - {s.get('hp', 0)} / "
        f"⚔️  ATK - {s.get('attack', 0)} / "
        f"🛡️  DEF - {s.get('defense', 0)}"
    )
    fila2 = (
        f"💥 SP.ATK - {s.get('special-attack', 0)} / "
        f"🔰 SP.DEF - {s.get('special-defense', 0)} / "
        f"💨 SPEED - {s.get('speed', 0)}"
    )
    total = sum(s.values())

    lineas.append(f"<b>📊 POWER STATS</b>")  # título en negrita
    lineas.append(fila1)                      # valores en texto plano
    lineas.append(fila2)
    lineas.append(f"<b>🏆 TOTAL:</b> {total}")  # etiqueta bold, número plano
    lineas.append("")

    # ── Mega evoluciones ───────────────────────────────────────────────────
    if datos["mega_evoluciones"]:
        megas_display = "  |  ".join(
            _nombre_mega(m) for m in datos["mega_evoluciones"]
        )
        lineas.append(f"🔀 <b>Mega:</b> {megas_display}")
        lineas.append("")

    # ── Descripción en bloque cita ─────────────────────────────────────────
    lineas.append("📖 <b>Descripción:</b>")
    lineas.append(f"<blockquote>{datos['descripcion']}</blockquote>")

    return "\n".join(lineas)


def _nombre_mega(nombre_raw: str) -> str:
    """'charizard-mega-x' → 'Mega X',  'charizard-mega' → 'Mega' """
    partes = nombre_raw.split("-mega")           # ['charizard', '-x'] o ['charizard', '']
    sufijo = partes[1].replace("-", " ").strip() # 'x' o ''
    return f"Mega {sufijo.upper()}" if sufijo else "Mega"


def _construir_teclado(datos: dict) -> InlineKeyboardMarkup:
    """Genera botones inline: fila 1 evoluciones, fila 2 megas (si hay), fila 3 acciones"""
    fila_evo = []

    if datos["evolucion_anterior"]:
        fila_evo.append(InlineKeyboardButton(
            text=f"⬅️ {datos['evolucion_anterior'].capitalize()}",
            callback_data=f"{CALLBACK_PREFIX}:{datos['evolucion_anterior']}",
        ))

    for evo in datos["evoluciones"][:2]:
        fila_evo.append(InlineKeyboardButton(
            text=f"➡️ {evo.capitalize()}",
            callback_data=f"{CALLBACK_PREFIX}:{evo}",
        ))

    if not fila_evo:
        fila_evo.append(InlineKeyboardButton(
            text="🔁 Sin evoluciones",
            callback_data=f"{CALLBACK_PREFIX}:_noop",
        ))

    filas = [fila_evo]

    # Fila de mega evoluciones (solo si existen)
    if datos["mega_evoluciones"]:
        fila_mega = [
            InlineKeyboardButton(
                text=f"🔀 {_nombre_mega(m)}",
                callback_data=f"{CALLBACK_PREFIX}:{m}",  # navega al Pokémon mega
            )
            for m in datos["mega_evoluciones"][:3]  # máx 3 megas en fila
        ]
        filas.append(fila_mega)

    # Fila de acciones extra
    tipos_str = ",".join(datos["tipos_raw"])
    fila_acciones = [
        InlineKeyboardButton(
            text="📊 Efectividad",
            callback_data=f"{CALLBACK_DEBILIDADES}:{datos['nombre']}:{tipos_str}",
        ),
        InlineKeyboardButton(
            text="📍 Dónde encontrarlo",
            callback_data=f"{CALLBACK_ENCUENTROS}:{datos['nombre']}",
        ),
    ]
    filas.append(fila_acciones)

    return InlineKeyboardMarkup(filas)


# ══════════════════════════════════════════════════════════════════════════════
# CONSTRUCCIÓN DEL MENSAJE — MOVIMIENTOS
# ══════════════════════════════════════════════════════════════════════════════

def _construir_texto_movimiento(datos: dict) -> str:
    """Arma el mensaje de un movimiento con sus estadísticas y descripción"""
    lineas = [
        f"<b>⚡ {datos['nombre_display']}</b>",
        "",
        f"🏷️ <b>Tipo:</b>     {datos['tipo']}",
        f"🎯 <b>Clase:</b>    {datos['clase']}",
        f"💪 <b>Poder:</b>    {datos['poder']}",
        f"🎯 <b>Precisión:</b> {datos['precision']}",
        f"🔋 <b>PP:</b>       {datos['pp']}",
        "",
        "📖 <b>Descripción:</b>",
        f"<blockquote>{datos['descripcion']}</blockquote>",
    ]
    return "\n".join(lineas)


# ══════════════════════════════════════════════════════════════════════════════
# CONSTRUCCIÓN DEL MENSAJE — ÍTEMS
# ══════════════════════════════════════════════════════════════════════════════

def _construir_texto_item(datos: dict) -> str:
    """Arma el mensaje de un ítem con su efecto, categoría y costo"""
    costo_str = f"🪙 {datos['costo']:,} PD" if datos["costo"] else "No vendible"
    lineas = [
        f"<b>🎒 {datos['nombre_display']}</b>",
        "",
        f"📦 <b>Categoría:</b> {datos['categoria']}",
        f"💰 <b>Costo:</b>     {costo_str}",
        "",
        "📖 <b>Efecto:</b>",
        f"<blockquote>{datos['efecto']}</blockquote>",
    ]
    return "\n".join(lineas)


# ══════════════════════════════════════════════════════════════════════════════
# CONSTRUCCIÓN DEL MENSAJE — TIPOS
# ══════════════════════════════════════════════════════════════════════════════

def _construir_texto_tipo(datos: dict) -> str:
    """Arma la tabla completa de relaciones ofensivas y defensivas de un tipo"""

    def _lista(items: list[str]) -> str:  # formatea lista o "—" si está vacía
        return "  ".join(items) if items else "—"

    lineas = [
        f"<b>{datos['nombre_display']} — Tabla de tipo</b>",
        "",
        "⚔️ <b>ATACANDO</b>",
        f"<b>×2  ✅ Súper efectivo:</b>",
        f"     {_lista(datos['doble_daño_a'])}",
        f"<b>×½  ⬇️ Poco efectivo:</b>",
        f"     {_lista(datos['mitad_daño_a'])}",
        f"<b>×0  ❌ Sin efecto:</b>",
        f"     {_lista(datos['sin_daño_a'])}",
        "",
        "🛡️ <b>DEFENDIENDO</b>",
        f"<b>×2  ⚠️ Débil ante:</b>",
        f"     {_lista(datos['doble_daño_de'])}",
        f"<b>×½  🛡️ Resiste:</b>",
        f"     {_lista(datos['mitad_daño_de'])}",
        f"<b>×0  🔰 Inmune a:</b>",
        f"     {_lista(datos['sin_daño_de'])}",
    ]
    return "\n".join(lineas)


# ══════════════════════════════════════════════════════════════════════════════
# VISTA DE DEBILIDADES
# ══════════════════════════════════════════════════════════════════════════════

# Configuración visual de cada categoría defensiva
_CATEGORIAS = [
    (0.0,  "×0   ❌ Inmune"),
    (0.25, "×¼   🛡️ Muy resistente"),
    (0.5,  "×½   ⬇️ Resistente"),
    (2.0,  "×2   ⬆️ Débil"),
    (4.0,  "×4   💀 Muy débil"),
]

def _construir_caption_debilidades(nombre_display: str, tipos: list[str], resultado: dict) -> str:
    """
    Arma el mensaje de efectividad con:
    - Sección defensiva: qué tipos le hacen daño
    - Sección ofensiva:  a qué tipos les hace daño
    Labels en negrita, listas de tipos en texto plano.
    """
    tipos_display = "  |  ".join(tipos)
    lineas = [
        f"<b>⚔️ Efectividad — {nombre_display}</b>",
        f"<i>{tipos_display}</i>",
        "",
        "🛡️ <b>DEFENSIVA</b>",
    ]

    defensiva = resultado.get("defensiva", {})
    hubo = False
    for mult, etiqueta in _CATEGORIAS:
        lista = defensiva.get(mult, [])
        if not lista:
            continue
        hubo = True
        lineas.append(f"<b>{etiqueta}</b>")                    # label en negrita
        lineas.append(f"     {'  '.join(lista)}")              # tipos en plano
        lineas.append("")

    if not hubo:
        lineas.append("✅ Sin debilidades ni resistencias especiales")
        lineas.append("")

    # ── Sección ofensiva ───────────────────────────────────────────────────
    ofensiva = resultado.get("ofensiva", [])
    lineas.append("⚔️ <b>OFENSIVA</b>")
    if ofensiva:
        lineas.append("<b>×2  ✅ Súper efectivo contra:</b>")
        lineas.append(f"     {'  '.join(ofensiva)}")
    else:
        lineas.append("Sin ventaja ofensiva especial")

    return "\n".join(lineas)


def _construir_teclado_debilidades(nombre: str) -> InlineKeyboardMarkup:
    """Teclado para la vista de debilidades — solo botón de regreso a la ficha"""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            text="🔙 Volver a la ficha",
            callback_data=f"{CALLBACK_PREFIX}:{nombre}",  # reutiliza el callback de evoluciones
        )
    ]])


# ══════════════════════════════════════════════════════════════════════════════
# VISTA DE ENCUENTROS
# ══════════════════════════════════════════════════════════════════════════════

def _construir_caption_encuentros(nombre_display: str, encuentros: list[dict]) -> str:
    """Arma el mensaje de zonas: título, un salto, zona en bold, método y versiones planos"""
    lineas = [f"<b>📍 Dónde encontrar a {nombre_display}</b>", ""]  # 1 espacio tras el título

    if not encuentros:
        lineas.append("🚫 Este Pokémon no aparece en la naturaleza.")
        lineas.append("<i>Solo se puede obtener por evento, regalo o evolución.</i>")
        return "\n".join(lineas)

    for enc in encuentros:
        metodos_str   = "  ".join(enc["metodos"]) if enc["metodos"] else "—"
        versiones_str = ", ".join(enc["versiones"][:4])
        if len(enc["versiones"]) > 4:
            versiones_str += "…"

        lineas.append(f"📌 <b>{enc['zona']}</b>")  # zona en negrita
        lineas.append(f"   {metodos_str}")           # método plano
        lineas.append(f"   🎮 {versiones_str}")      # versiones plano
        lineas.append("")                            # separador entre zonas

    return "\n".join(lineas)


def _construir_teclado_encuentros(nombre: str) -> InlineKeyboardMarkup:
    """Teclado para la vista de encuentros — solo botón de regreso"""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            text="🔙 Volver a la ficha",
            callback_data=f"{CALLBACK_PREFIX}:{nombre}",
        )
    ]])


# ══════════════════════════════════════════════════════════════════════════════
# LÓGICA PRINCIPAL DE ENVÍO / EDICIÓN
# ══════════════════════════════════════════════════════════════════════════════

async def _mostrar_pokemon(
    nombre: str,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    editar: bool = False,
) -> None:
    """
    Busca los datos del Pokémon y:
    - editar=False → envía un mensaje nuevo con foto
    - editar=True  → edita el mensaje existente (usado desde callback)
    """
    chat_id = update.effective_chat.id

    # Indicador de carga solo cuando es un comando nuevo (no edición)
    if not editar:
        mensaje_espera = await context.bot.send_message(
            chat_id=chat_id,
            text="🔍 Buscando en la Pokédex...",
        )

    datos = await obtener_datos_completos(nombre)

    if datos is None:
        if editar:
            await update.callback_query.answer(
                "❌ No encontré ese Pokémon. Puede ser un nombre inválido.",
                show_alert=True,
            )
        else:
            await mensaje_espera.edit_text(
                f"❌ No encontré a <b>{nombre.capitalize()}</b> en la Pokédex.\n"
                "Verifica el nombre e intenta de nuevo.",
                parse_mode=ParseMode.HTML,
            )
        return

    caption = _construir_caption(datos)
    teclado = _construir_teclado(datos)

    if editar:
        # Edita la foto y el caption del mensaje existente
        await update.callback_query.edit_message_media(
            media=InputMediaPhoto(
                media=datos["imagen"],
                caption=caption,
                parse_mode=ParseMode.HTML,
            ),
            reply_markup=teclado,
        )
    else:
        # Elimina el mensaje "Buscando..." y envía la foto
        await mensaje_espera.delete()
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=datos["imagen"],
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=teclado,
        )


# ══════════════════════════════════════════════════════════════════════════════
# HANDLERS — POKÉMON BASE
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_pokemon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/pokemon <nombre> — busca y muestra un Pokémon en la Pokédex"""
    if not context.args:
        await update.message.reply_text(
            "❓ Debes indicar un Pokémon.\n"
            "Ejemplo: <code>/pokemon pikachu</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    nombre = context.args[0].lower().strip()  # normalizar entrada del usuario
    await _mostrar_pokemon(nombre, update, context, editar=False)


async def callback_pokedex(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja los botones inline de evolución — edita el mensaje en lugar de crear uno nuevo"""
    query = update.callback_query
    await query.answer()  # quitar el spinner del botón inmediatamente

    _, nombre = query.data.split(":", 1)  # extraer nombre del callback_data

    if nombre == "_noop":  # botón decorativo sin acción
        return

    await _mostrar_pokemon(nombre, update, context, editar=True)


async def callback_debilidades(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja el botón ⚔️ Debilidades — edita solo el caption con la tabla de efectividad"""
    query = update.callback_query
    await query.answer()

    # callback_data formato: "pdx_weak:{nombre}:{tipo1,tipo2}"
    partes = query.data.split(":")
    nombre     = partes[1]
    tipos_raw  = partes[2].split(",")  # lista de tipos en inglés

    # Deducir display del nombre y tipos para el caption (sin nueva petición)
    nombre_display = " ".join(p.capitalize() for p in nombre.replace("-", " ").split())

    resultado = await obtener_debilidades(tipos_raw)

    if resultado is None:
        await query.answer("❌ Error al cargar la tabla de efectividad.", show_alert=True)
        return

    from external_apis.pokeapi import TIPOS_ES  # importación local para evitar ciclo
    tipos_display = [TIPOS_ES.get(t, t.capitalize()) for t in tipos_raw]

    caption  = _construir_caption_debilidades(nombre_display, tipos_display, resultado)
    teclado  = _construir_teclado_debilidades(nombre)

    # Edita solo el caption — la imagen se mantiene intacta
    await query.edit_message_caption(
        caption=caption,
        parse_mode=ParseMode.HTML,
        reply_markup=teclado,
    )


async def callback_encuentros(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja el botón 📍 Dónde encontrarlo — edita el caption con las zonas"""
    query = update.callback_query
    await query.answer()

    _, nombre = query.data.split(":", 1)  # formato: "pdx_enc:{nombre}"
    nombre_display = " ".join(p.capitalize() for p in nombre.replace("-", " ").split())

    encuentros = await obtener_encuentros(nombre)

    if encuentros is None:  # solo falla si hay error de red
        await query.answer("❌ Error al consultar las zonas de encuentro.", show_alert=True)
        return

    caption = _construir_caption_encuentros(nombre_display, encuentros)
    teclado = _construir_teclado_encuentros(nombre)

    await query.edit_message_caption(
        caption=caption,
        parse_mode=ParseMode.HTML,
        reply_markup=teclado,
    )


# ══════════════════════════════════════════════════════════════════════════════
# HANDLERS — NUEVOS COMANDOS
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_pkm_move(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/pkm_move <movimiento> — muestra stats y descripción de un movimiento"""
    if not context.args:
        await update.message.reply_text(
            "❓ Debes indicar un movimiento.\n"
            "Ejemplo: <code>/pkm_move thunderbolt</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    nombre = "-".join(context.args).lower().strip()  # "thunder bolt" → "thunder-bolt"
    espera = await update.message.reply_text("🔍 Buscando movimiento...")

    datos = await obtener_movimiento(nombre)
    await espera.delete()

    if datos is None:
        await update.message.reply_text(
            f"❌ No encontré el movimiento <b>{nombre}</b>.\n"
            "Usa el nombre en inglés, ej: <code>flamethrower</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    await update.message.reply_text(
        _construir_texto_movimiento(datos),
        parse_mode=ParseMode.HTML,
    )


async def cmd_pkm_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/pkm_item <ítem> — muestra efecto e imagen de un ítem"""
    if not context.args:
        await update.message.reply_text(
            "❓ Debes indicar un ítem.\n"
            "Ejemplo: <code>/pkm_item master-ball</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    nombre = "-".join(context.args).lower().strip()  # "master ball" → "master-ball"
    espera = await update.message.reply_text("🔍 Buscando ítem...")

    datos = await obtener_item(nombre)
    await espera.delete()

    if datos is None:
        await update.message.reply_text(
            f"❌ No encontré el ítem <b>{nombre}</b>.\n"
            "Usa el nombre en inglés, ej: <code>potion</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    texto = _construir_texto_item(datos)

    if datos["imagen"]:  # enviar con sprite si está disponible
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=datos["imagen"],
            caption=texto,
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(texto, parse_mode=ParseMode.HTML)


async def cmd_pkm_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/pkm_type <tipo> — muestra tabla completa de fortalezas y debilidades"""
    if not context.args:
        await update.message.reply_text(
            "❓ Debes indicar un tipo.\n"
            "Ejemplo: <code>/pkm_type fire</code> o <code>/pkm_type fuego</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    nombre = context.args[0].lower().strip()
    espera = await update.message.reply_text("🔍 Cargando tabla de tipo...")

    datos = await obtener_tipo(nombre)
    await espera.delete()

    if datos is None:
        await update.message.reply_text(
            f"❌ No encontré el tipo <b>{nombre}</b>.\n"
            "Tipos válidos: fire, water, grass, electric, ice, fighting, "
            "poison, ground, flying, psychic, bug, rock, ghost, dragon, "
            "dark, steel, fairy, normal.",
            parse_mode=ParseMode.HTML,
        )
        return

    await update.message.reply_text(
        _construir_texto_tipo(datos),
        parse_mode=ParseMode.HTML,
    )


async def cmd_pkm_random(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/pkm_random — obtiene un Pokémon al azar (Gen 1–9)"""
    datos = await obtener_pokemon_aleatorio()

    if datos is None:  # fallo de red poco probable pero posible
        await update.message.reply_text("❌ Error al obtener el Pokémon aleatorio. Intenta de nuevo.")
        return

    # Reutiliza _mostrar_pokemon pasando el nombre del Pokémon obtenido
    await _mostrar_pokemon(datos["nombre"], update, context, editar=False)


# ══════════════════════════════════════════════════════════════════════════════
# REGISTRO
# ══════════════════════════════════════════════════════════════════════════════

def register_pokedex_handler(app: Application) -> None:
    """Registra todos los handlers del módulo Pokédex en la aplicación"""
    # Comandos base
    app.add_handler(CommandHandler(["pokemon", "pkm"],    cmd_pokemon))

    # Nuevos comandos
    app.add_handler(CommandHandler("pkm_move",   cmd_pkm_move))
    app.add_handler(CommandHandler("pkm_item",   cmd_pkm_item))
    app.add_handler(CommandHandler("pkm_type",   cmd_pkm_type))
    app.add_handler(CommandHandler("pkm_random", cmd_pkm_random))

    # Callbacks inline
    app.add_handler(CallbackQueryHandler(callback_pokedex,    pattern=rf"^{CALLBACK_PREFIX}:"))
    app.add_handler(CallbackQueryHandler(callback_debilidades, pattern=rf"^{CALLBACK_DEBILIDADES}:"))
    app.add_handler(CallbackQueryHandler(callback_encuentros,  pattern=rf"^{CALLBACK_ENCUENTROS}:"))
    