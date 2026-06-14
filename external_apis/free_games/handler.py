"""
Handler de juegos gratis.
- Job cada N horas que notifica juegos nuevos en los grupos configurados.
- Comando /juegosgratis para verificacion manual.
- Deduplicacion con MongoDB (colección sent_games).
"""

import logging

from telegram import Bot, Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode

from .sources import obtener_juegos_gratis
from .sent_games_manager import SentGamesManager
from config import FREE_GAMES_GRUPOS, FREE_GAMES_CANALES, FREE_GAMES_INTERVALO_HORAS

logger = logging.getLogger(__name__)

EMOJIS = {
    "Epic Games": "🎁",
    "GOG":        "🔮",
    "Steam":      "🎮",
}


# ── Persistencia ──────────────────────────────────────────────────────────────
def cargar_enviados() -> set[str]:
    """Carga los IDs de juegos ya enviados desde MongoDB"""
    try:
        return set(SentGamesManager.get_all_sent_games())
    except Exception as e:
        logger.warning(f"[Enviados] Error cargando: {e}")
        return set()


def guardar_enviados(ids: set[str]):
    """Guarda los IDs de juegos enviados en MongoDB"""
    try:
        nuevos = list(ids)
        if nuevos:
            SentGamesManager.add_games_bulk(nuevos)
    except Exception as e:
        logger.error(f"[Enviados] Error guardando: {e}")


def filtrar_nuevos(juegos: list[dict], enviados: set[str]) -> list[dict]:
    return [j for j in juegos if j["id"] and j["id"] not in enviados]


# ── Formato ───────────────────────────────────────────────────────────────────
def _truncar(texto: str, limite: int = 250) -> str:
    texto = texto.strip()
    return texto if len(texto) <= limite else texto[:limite].rstrip() + "..."


def _linea_opcional(icono: str, etiqueta: str, valor: str) -> str:
    """Retorna la linea formateada solo si el valor no esta vacio"""
    return f"{icono} <b>{etiqueta}:</b> {valor}\n" if valor else ""


def construir_mensaje(juego: dict) -> tuple[str, InlineKeyboardMarkup]:
    """Retorna (texto HTML, teclado con boton de enlace)"""
    emoji       = EMOJIS.get(juego["fuente"], "🎯")
    titulo      = juego["titulo"]
    fuente      = juego["fuente"]
    descripcion = _truncar(juego.get("descripcion", ""))
    valor       = juego.get("valor", "")
    f_lanz      = juego.get("fecha_lanzamiento", "")
    f_fin       = juego.get("fecha_fin_promo", "")

    bloque_info = (
        _linea_opcional("💰", "Valor original", valor)
        + _linea_opcional("📅", "Lanzamiento", f_lanz)
        + _linea_opcional("⏰", "Finaliza", f_fin)
    )

    bloque_desc = (
        f"\n<blockquote>{descripcion}</blockquote>\n"
        if descripcion else ""
    )

    texto = (
        f"{emoji} <b>{titulo}</b> — {fuente}\n\n"
        f"{bloque_info}"
        f"{bloque_desc}\n"
        f"🆓 <i>Disponible gratis por tiempo limitado</i>"
    )

    teclado = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"🎮 Reclamar en {fuente}", url=juego["url"])
    ]])

    return texto, teclado


# ── Envio ─────────────────────────────────────────────────────────────────────
async def _enviar_a_destino(bot: Bot, chat_id: int, juego: dict, texto: str, teclado: InlineKeyboardMarkup, imagen: str):
    """Envía un juego a un destino (grupo o canal)"""
    try:
        if imagen:
            await bot.send_photo(
                chat_id=chat_id,
                photo=imagen,
                caption=texto,
                parse_mode=ParseMode.HTML,
                reply_markup=teclado,
            )
        else:
            await bot.send_message(
                chat_id=chat_id,
                text=texto,
                parse_mode=ParseMode.HTML,
                reply_markup=teclado,
            )
        logger.info(f"[Notificado] '{juego['titulo']}' ({juego['fuente']}) -> {chat_id}")
    except Exception as e:
        logger.error(f"[Notificado] Error en destino {chat_id}: {e}")


async def notificar_juego(bot: Bot, juego: dict):
    texto, teclado = construir_mensaje(juego)
    imagen = juego.get("imagen", "")
    destinos = FREE_GAMES_GRUPOS + FREE_GAMES_CANALES  # Combina grupos y canales

    for chat_id in destinos:
        await _enviar_a_destino(bot, chat_id, juego, texto, teclado, imagen)


async def notificar_todos(bot: Bot, juegos: list[dict]):
    if not juegos:
        return

    enviados = cargar_enviados()
    nuevos   = filtrar_nuevos(juegos, enviados)

    if not nuevos:
        return

    logger.info(f"[FreeGames] Notificando {len(nuevos)} juego(s) nuevo(s)")
    for juego in nuevos:
        await notificar_juego(bot, juego)
        enviados.add(juego["id"])

    guardar_enviados(enviados)


# ── Jobs y comandos ───────────────────────────────────────────────────────────
async def job_revisar_juegos(context: ContextTypes.DEFAULT_TYPE):
    try:
        juegos = await obtener_juegos_gratis()
        await notificar_todos(context.bot, juegos)
    except Exception as e:
        logger.error(f"[Job] Error inesperado: {e}")


async def cmd_juegos_gratis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /juegosgratis — fuerza revision inmediata"""
    await update.message.reply_text("🔍 Buscando juegos gratis...")
    try:
        juegos = await obtener_juegos_gratis()
        if not juegos:
            await update.message.reply_text("😕 No se encontraron juegos gratis en este momento.")
            return
        await update.message.reply_text(f"✅ {len(juegos)} juego(s) encontrado(s). Notificando grupos...")
        await notificar_todos(context.bot, juegos)
    except Exception as e:
        logger.error(f"[cmd] Error: {e}")
        await update.message.reply_text("❌ Error al buscar juegos gratis.")


async def cmd_reset_enviados(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /resetjuegos — borra historial de enviados en MongoDB (para pruebas)"""
    try:
        deleted = SentGamesManager.clear_all()
        await update.message.reply_text(f"🗑️ Historial de {deleted} juegos enviados borrado.")
    except Exception as e:
        logger.error(f"[cmd_reset] Error: {e}")
        await update.message.reply_text("❌ Error al borrar historial.")


def register_free_games_handler(app: Application):
    app.job_queue.run_repeating(
        callback=job_revisar_juegos,
        interval=FREE_GAMES_INTERVALO_HORAS * 3600,  # Intervalo cargado desde .env
        first=10,
        name="free_games_job",
    )
    app.add_handler(CommandHandler("juegosgratis", cmd_juegos_gratis))
    app.add_handler(CommandHandler("resetjuegos", cmd_reset_enviados))