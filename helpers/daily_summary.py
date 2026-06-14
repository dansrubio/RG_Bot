"""
Módulo de resumen diario de publicaciones
Envía al grupo configurado un resumen al final de cada día.
"""

import logging
from datetime import datetime, timezone, time as dtime

from telegram.constants import ParseMode
from telegram.ext import Application

from database.base import get_database

logger = logging.getLogger(__name__)

RESUMEN_GRUPO = -1001566841008  # grupo destino (-100 + ID del supergrupo)
HORA_RESUMEN  = dtime(23, 55, 0, tzinfo=timezone.utc)  # 23:55 UTC todos los días


def _formatear_peso(bytes_total: int) -> str:
    """Convierte bytes a la unidad más legible"""
    if bytes_total <= 0:
        return "0 KB"
    if bytes_total >= 1_073_741_824:
        valor = bytes_total / 1_073_741_824
        return f"{valor:.2f} GB".rstrip("0").rstrip(".")
    if bytes_total >= 1_048_576:
        valor = bytes_total / 1_048_576
        return f"{valor:.1f} MB" if valor % 1 else f"{int(valor)} MB"
    return f"{bytes_total / 1024:.0f} KB"


def _obtener_elementos_del_dia() -> list:
    """Retorna los elementos creados desde las 00:00 UTC de hoy"""
    inicio_dia = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return list(
        get_database().elementos
        .find(
            {"fecha_creacion": {"$gte": inicio_dia}},
            {"peso_bytes": 1, "num_archivos": 1}
        )
    )


async def _enviar_resumen_diario(context) -> None:
    """Job programado: consulta la BD y publica el resumen en el grupo"""
    try:
        elementos = _obtener_elementos_del_dia()

        if not elementos:
            logger.info("📅 Resumen diario: no se añadieron juegos hoy, omitiendo envío")
            return

        total_juegos   = len(elementos)
        total_bytes    = sum(e.get("peso_bytes",   0) for e in elementos)
        total_archivos = sum(e.get("num_archivos", 0) for e in elementos)
        fecha          = datetime.now(timezone.utc).strftime("%d/%m/%Y")

        mensaje = (
            f"📅 <b>Resumen del día — {fecha}</b>\n\n"
            f"🎮 <b>Juegos añadidos:</b> {total_juegos}\n"
            f"💾 <b>Peso total:</b> {_formatear_peso(total_bytes)}\n"
            f"📦 <b>Archivos totales:</b> {total_archivos}"
        )

        await context.bot.send_message(
            chat_id=RESUMEN_GRUPO,
            text=mensaje,
            parse_mode=ParseMode.HTML
        )
        logger.info(f"📅 Resumen diario enviado: {total_juegos} juegos, {_formatear_peso(total_bytes)}")

    except Exception as e:
        logger.error(f"❌ Error enviando resumen diario: {e}")


def register_daily_summary(application: Application) -> None:
    """Registra el job de resumen diario en el JobQueue del bot"""
    application.job_queue.run_daily(
        _enviar_resumen_diario,
        time=HORA_RESUMEN,
        name="resumen_diario_juegos"
    )