"""
Comandos de estadísticas para admins y moderadores
  /stats_db    — Info técnica del servidor MongoDB
  /stats_users — Usuarios + elementos en un solo mensaje
"""

import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config import is_admin, is_moderator
from database.base import get_database, obtener_info_servidor, obtener_estadisticas_db, verificar_conexion
from database.crud.elemento_crud import ElementoCRUD

logger = logging.getLogger(__name__)


def solo_staff(func):
    """Decorador: permite acceso solo a admins y moderadores"""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not (is_admin(user_id) or is_moderator(user_id)):
            await update.message.reply_text("⛔ No tienes permiso para usar este comando.")
            return
        return await func(update, context)
    return wrapper


def _formatear_segundos(segundos: int) -> str:
    """Convierte segundos a formato legible d/h/m/s"""
    dias,   resto  = divmod(segundos, 86400)
    horas,  resto  = divmod(resto,    3600)
    minutos, segs  = divmod(resto,    60)
    partes = []
    if dias:    partes.append(f"{dias}d")
    if horas:   partes.append(f"{horas}h")
    if minutos: partes.append(f"{minutos}m")
    partes.append(f"{segs}s")
    return " ".join(partes)


def _obtener_stats_colecciones(db) -> dict:
    """Estadísticas por colección directamente desde MongoDB"""
    colecciones = ["usuarios", "elementos", "elemento_solicitudes", "tickets"]
    resultado   = {}
    for nombre in colecciones:
        try:
            stats = db.command("collStats", nombre)
            resultado[nombre] = {
                "documentos":        db[nombre].count_documents({}),
                "tamaño_mb":         round(stats.get("size", 0) / (1024 * 1024), 3),
                "indices":           stats.get("nindexes", 0),
                "tamaño_indices_mb": round(stats.get("totalIndexSize", 0) / (1024 * 1024), 3),
            }
        except Exception:
            resultado[nombre] = {"documentos": 0, "tamaño_mb": 0, "indices": 0, "tamaño_indices_mb": 0}
    return resultado


# ── /stats_db ────────────────────────────────────────────────────────────────

@solo_staff
async def cmd_stats_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra información técnica completa del servidor MongoDB"""
    msg = await update.message.reply_text("⏳ Consultando base de datos...")

    try:
        if not verificar_conexion():
            await msg.edit_text("❌ Sin conexión a MongoDB.")
            return

        db       = get_database()
        servidor = obtener_info_servidor()
        db_stats = obtener_estadisticas_db()
        cols     = _obtener_stats_colecciones(db)

        lineas_cols = [
            f"  • <b>{nombre}</b>: {datos['documentos']:,} docs — "
            f"{datos['tamaño_mb']} MB — {datos['indices']} índices"
            for nombre, datos in cols.items()
        ]

        uptime_str = _formatear_segundos(int(servidor.get("uptime_segundos", 0)))

        texto = (
            "🗄️ <b>ESTADÍSTICAS DE BASE DE DATOS</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"

            "🔌 <b>Servidor MongoDB</b>\n"
            f"  Tipo: <code>{servidor.get('tipo', 'Desconocido')}</code>\n"
            f"  Versión: <code>{servidor.get('version', 'N/A')}</code>\n"
            f"  Uptime: <code>{uptime_str}</code>\n"
            f"  Conexiones activas: <code>{servidor.get('conexiones_actuales', 0)}</code>\n"
            f"  Conexiones disponibles: <code>{servidor.get('conexiones_disponibles', 0)}</code>\n\n"

            "📊 <b>Base de datos:</b> <code>{nombre}</code>\n"
            f"  Colecciones: <code>{db_stats.get('colecciones', 0)}</code>\n"
            f"  Documentos totales: <code>{db_stats.get('documentos', 0):,}</code>\n"
            f"  Datos: <code>{db_stats.get('tamaño_datos_mb', 0)} MB</code>\n"
            f"  Storage: <code>{db_stats.get('tamaño_storage_mb', 0)} MB</code>\n"
            f"  Índices: <code>{db_stats.get('indices', 0)}</code> "
            f"(<code>{db_stats.get('tamaño_indices_mb', 0)} MB</code>)\n\n"

            "📂 <b>Detalle por colección</b>\n"
            f"{chr(10).join(lineas_cols) or '  Sin datos'}"
        ).format(nombre=db_stats.get("nombre", "N/A"))

        await msg.edit_text(texto, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error en /stats_db: {e}")
        await msg.edit_text("❌ Error al obtener estadísticas.")


# ── /stats_users ─────────────────────────────────────────────────────────────

@solo_staff
async def cmd_stats_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra estadísticas de usuarios y elementos en un solo bloque"""
    msg = await update.message.reply_text("⏳ Recopilando estadísticas...")

    try:
        db  = get_database()
        col = db.usuarios

        # ── Sección usuarios ──────────────────────────────────────────────────
        total_usuarios   = col.count_documents({})
        con_solicitudes  = col.count_documents({"solicitudes": {"$gt": 0}})  # Usuarios que han pedido algo

        res_prom = list(col.aggregate([  # Promedio de solicitudes entre usuarios activos
            {"$match":  {"solicitudes": {"$gt": 0}}},
            {"$group":  {"_id": None, "promedio": {"$avg": "$solicitudes"}}}
        ]))
        promedio_sols = round(res_prom[0]["promedio"], 1) if res_prom else 0

        # Top 5 usuarios por solicitudes acumuladas
        top_usuarios = list(col.aggregate([
            {"$match":   {"solicitudes": {"$gt": 0}}},
            {"$sort":    {"solicitudes": -1}},
            {"$limit":   5},
            {"$project": {"_id": 1, "username": 1, "name": 1, "solicitudes": 1}}
        ]))

        lineas_top_usr = []
        for i, u in enumerate(top_usuarios, start=1):
            nombre = (
                f"@{u['username']}" if u.get("username")
                else u.get("name") or f"ID {u['_id']}"
            )
            lineas_top_usr.append(
                f"  {i}. <b>{nombre}</b> — <code>{u['solicitudes']}</code> solicitudes"
            )
        bloque_top_usr = "\n".join(lineas_top_usr) if lineas_top_usr else "  Sin datos aún"

        # ── Sección elementos ─────────────────────────────────────────────────
        stats_elem  = ElementoCRUD.obtener_estadisticas()
        total_elem  = stats_elem.get("total_elementos", 0)
        total_sols  = stats_elem.get("total_solicitudes", 0)
        prom_sols   = stats_elem.get("promedio_solicitudes", 0)
        sin_sols    = stats_elem.get("elementos_sin_solicitudes", 0)
        con_info    = stats_elem.get("elementos_con_info", 0)  # Elementos con texto indexado
        pct_sin     = round(sin_sols / total_elem * 100, 1) if total_elem > 0 else 0
        pct_info    = round(con_info / total_elem * 100, 1) if total_elem > 0 else 0

        mas_sol = stats_elem.get("elemento_mas_solicitado")
        top_elem_txt = (
            f"  🏆 <b>{mas_sol['nombre']}</b> — <code>{mas_sol['solicitudes']:,}</code> solicitudes"
            if mas_sol else "  Sin datos aún"
        )

        # ── Armar mensaje ─────────────────────────────────────────────────────
        texto = (
            "📊 <b>ESTADÍSTICAS GENERALES</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"

            "👥 <b>Usuarios</b>\n"
            f"  Registrados: <code>{total_usuarios:,}</code>\n"
            f"  Con solicitudes: <code>{con_solicitudes:,}</code>\n"
            f"  Promedio solicitudes/usuario activo: <code>{promedio_sols}</code>\n\n"

            "🏅 <b>Top 5 por solicitudes</b>\n"
            f"{bloque_top_usr}\n\n"

            "🎮 <b>Elementos</b>\n"
            f"  Total: <code>{total_elem:,}</code>  •  "
            f"Solicitudes totales: <code>{total_sols:,}</code>\n"
            f"  Promedio sols/elemento: <code>{prom_sols}</code>  •  "
            f"Sin solicitudes: <code>{sin_sols}</code> (<code>{pct_sin}%</code>)\n"
            f"  Con texto indexado: <code>{con_info}</code> (<code>{pct_info}%</code>)\n"
            f"{top_elem_txt}"
        )

        await msg.edit_text(texto, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error en /stats_users: {e}")
        await msg.edit_text("❌ Error al obtener estadísticas.")


# ── Registro ─────────────────────────────────────────────────────────────────

def register_stats_handlers(app: Application):
    app.add_handler(CommandHandler("stats_db",    cmd_stats_db))
    app.add_handler(CommandHandler("stats_users", cmd_stats_users))