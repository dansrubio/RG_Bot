import logging
import time
import os
import sys
import psutil
import platform
import subprocess
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from config import ADMIN_IDS

# Guardamos el tiempo en que se inició el bot
BOT_START_TIME = time.time()
COOLDOWN_ACTUALIZAR = 5  # Segundos de delay para el botón actualizar


def _formatear_uptime(dt_inicio: datetime) -> str:
    """Calcula el tiempo transcurrido desde dt_inicio (UTC) como string legible"""
    delta = datetime.now(timezone.utc) - dt_inicio
    return str(delta).split(".")[0]


def _obtener_version_git() -> str:
    """Obtiene el último commit o descripción del repositorio Git"""
    try:
        return subprocess.check_output(["git", "describe", "--always"]).strip().decode()
    except Exception:
        return "Desconocida (No Git)"


def _obtener_estado_mongodb() -> str:
    """
    Verifica el estado de MongoDB utilizando las funciones nativas de database.base
    """
    try:
        from database.base import verificar_conexion, obtener_estadisticas_db
        if verificar_conexion():
            stats = obtener_estadisticas_db()
            if "error" not in stats:
                return f"✅ Online ({stats['documentos']} docs, {stats['tamaño_datos_mb']} MB)"
            return "✅ Online"
        return "❌ Offline"
    except Exception:
        return "❌ Error de conexión"


def _obtener_estado_userbot() -> dict | None:
    """Importa y retorna el estado del userbot de forma segura desde el indexador modular"""
    try:
        # Importamos apuntando correctamente a la subcarpeta userbot
        from userbot.manager import get_estado_userbot
        return get_estado_userbot()
    except Exception as e:
        import logging
        logging.error(f"Error obteniendo estado del userbot en status.py: {e}")
        return None


def _generar_barra_progreso(porcentaje: float) -> str:
    """Genera una barra de progreso visual de 10 bloques para el consumo"""
    bloques_llenos = int(round(porcentaje / 10))
    bloques_vacios = 10 - bloques_llenos
    return f"[{'■' * bloques_llenos}{'□' * bloques_vacios}] {porcentaje:.1f}%"


def _obtener_datos_sistema(latency_ms: int, bot_uptime: str) -> str:
    """Reúne todas las métricas de hardware, software, DB y Userbot"""
    # CPU
    cpu_usage = psutil.cpu_percent(interval=None)
    cpu_count = psutil.cpu_count(logical=True)
    cpu_model = platform.processor() or "Procesador Genérico"
    barra_cpu = _generar_barra_progreso(cpu_usage)

    # RAM
    memory = psutil.virtual_memory()
    ram_usada = memory.used / (1024 ** 3)
    ram_total = memory.total / (1024 ** 3)
    barra_ram = _generar_barra_progreso(memory.percent)

    # Disco
    disk = psutil.disk_usage("/")
    disco_usado = disk.used / (1024 ** 3)
    disco_total = disk.total / (1024 ** 3)
    barra_disco = _generar_barra_progreso(disk.percent)

    # Variables de entorno y software
    boot_time = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
    uptime_sistema = datetime.now(timezone.utc) - boot_time
    python_version = sys.version.split()[0]
    git_version = _obtener_version_git()
    mongo_status = _obtener_estado_mongodb()

    # Info de red y temperatura
    net_io = psutil.net_io_counters()
    network_info = f"↑ {net_io.bytes_sent / (1024 ** 2):.2f} MB | ↓ {net_io.bytes_recv / (1024 ** 2):.2f} MB"

    cpu_temp = "No disponible"
    try:
        if hasattr(psutil, "sensors_temperatures"):
            temps = psutil.sensors_temperatures()
            if temps:
                if "coretemp" in temps:
                    cpu_temp = f"{temps['coretemp'][0].current}°C"
                elif "cpu-thermal" in temps:
                    cpu_temp = f"{temps['cpu-thermal'][0].current}°C"
        if cpu_temp == "No disponible" and os.path.exists("/sys/class/thermal/thermal_zone0/temp"):
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                cpu_temp = f"{int(f.read().strip()) / 1000:.1f}°C"
    except Exception:
        cpu_temp = "No soportado"

    # Estado del Userbot
    estado_ub = _obtener_estado_userbot()
    if estado_ub is None:
        userbot_seccion = (
            "**🤖 USERBOT:**\n"
            "└ No disponible (módulo no cargado o apagado)\n"
        )
    else:
        ub_icono  = "✅" if estado_ub.get("conectado") else "❌"
        ub_estado = "Conectado" if estado_ub.get("conectado") else "Desconectado"

        ub_desde = "—"
        if estado_ub.get("conectado_desde"):
            ub_desde = _formatear_uptime(estado_ub["conectado_desde"])

        ub_ultimo_index = "—"
        if estado_ub.get("ultimo_index"):
            delta_index     = datetime.now(timezone.utc) - estado_ub["ultimo_index"]
            mins            = int(delta_index.total_seconds() // 60)
            ub_ultimo_index = f"hace {mins} min" if mins < 60 else estado_ub["ultimo_index"].strftime("%d/%m %H:%M UTC")

        ub_indexados = estado_ub.get("elementos_indexados_total", 0)
        ub_error     = estado_ub.get("ultimo_error") or "Ninguno"

        userbot_seccion = (
            "**🤖 USERBOT:**\n"
            f"├ Estado: {ub_icono} {ub_estado}\n"
            f"├ Activo desde: {ub_desde}\n"
            f"├ Último /index: {ub_ultimo_index}\n"
            f"├ Elementos indexados: {ub_indexados}\n"
            f"└ Último error: {ub_error[:80]}\n"
        )

    # Construcción final del texto usando Markdown estándar con títulos en negrita (incluyendo emojis)
    return (
        "**📊 ESTADO DEL SISTEMA**\n\n"
        "**🖥️ HARDWARE & CONSUMO:**\n"
        f"├ *CPU:* {cpu_model} ({cpu_count} hilos)\n"
        f"│   └ {barra_cpu}\n"
        f"├ *RAM:* {ram_usada:.2f} GB / {ram_total:.2f} GB\n"
        f"│   └ {barra_ram}\n"
        f"└ *Disco:* {disco_usado:.2f} GB / {disco_total:.2f} GB\n"
        f"    └ {barra_disco}\n\n"
        "**⚙️ ENTORNO & VERSIONES:**\n"
        f"├ *SO:* {platform.system()} {platform.release()}\n"
        f"├ *Python:* v{python_version}\n"
        f"├ *Git Versión:* {git_version}\n"
        f"├ *Uptime Sistema:* {str(uptime_sistema).split('.')[0]}\n"
        f"└ *Uptime Bot:* {bot_uptime}\n\n"
        "**⚡️ MÉTRICAS & RED:**\n"
        f"├ *Latencia:* {latency_ms} ms\n"
        f"├ *Tráfico:* {network_info}\n"
        f"└ *Temperatura CPU:* {cpu_temp}\n\n"
        "**🗄️ SERVICIOS:**\n"
        f"├ *MongoDB:* {mongo_status}\n\n"
        f"{userbot_seccion}"
    )


def _obtener_teclado_status() -> InlineKeyboardMarkup:
    """Genera la botonera con el enlace a GitHub y la acción de refrescar"""
    botones = [
        [
            InlineKeyboardButton("📦 GitHub Repo", url="https://github.com/dansrubio/RG_Bot"),
            InlineKeyboardButton("🔄 Actualizar", callback_data="refresh_status")
        ]
    ]
    return InlineKeyboardMarkup(botones)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /status - Muestra información avanzada del sistema y bot"""
    try:
        user_id = update.effective_user.id if update.effective_user else None
        is_admin = user_id in ADMIN_IDS

        # Medición inicial de latencia básica
        start = time.time()
        sent_message = await update.message.reply_text("⏳ Midiendo latencia...")
        end = time.time()
        latency_ms = int((end - start) * 1000)
        try:
            await sent_message.delete()
        except Exception:
            pass

        bot_uptime = str(datetime.now(timezone.utc) - datetime.fromtimestamp(BOT_START_TIME, tz=timezone.utc)).split(".")[0]

        if not is_admin:
            simple_message = (
                "✅ ¡El bot se encuentra activo!\n"
                f"Latencia: {latency_ms} ms\n"
                f"Uptime bot: {bot_uptime}"
            )
            await update.message.reply_text(simple_message)
            return

        status_message = _obtener_datos_sistema(latency_ms, bot_uptime)
        teclado = _obtener_teclado_status()

        await update.message.reply_text(status_message, parse_mode="Markdown", reply_markup=teclado)

    except Exception as e:
        logging.error(f"Error en /status: {e}")
        try:
            await update.message.reply_text("❌ Error obteniendo estado del sistema.")
        except Exception:
            pass


async def status_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja las pulsaciones del botón '🔄 Actualizar' con control de cooldown"""
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in ADMIN_IDS:
        await query.answer("❌ No tienes permisos para usar este botón.", show_alert=True)
        return

    ahora = time.time()
    ultimo_click = context.user_data.get("ultimo_click_status", 0)
    tiempo_transcurrido = ahora - ultimo_click

    if tiempo_transcurrido < COOLDOWN_ACTUALIZAR:
        tiempo_restante = int(COOLDOWN_ACTUALIZAR - tiempo_transcurrido)
        await query.answer(f"⏳ Por favor, espera {tiempo_restante}s antes de actualizar de nuevo.", show_alert=True)
        return

    context.user_data["ultimo_click_status"] = ahora

    try:
        await query.answer("🔄 Actualizando métricas...")

        start_time = time.time()
        bot_uptime = str(datetime.now(timezone.utc) - datetime.fromtimestamp(BOT_START_TIME, tz=timezone.utc)).split(".")[0]
        
        latency_ms = int((time.time() - start_time) * 1000)
        if latency_ms <= 0:
            latency_ms = 5
            
        nuevo_texto = _obtener_datos_sistema(latency_ms, bot_uptime)
        teclado = _obtener_teclado_status()

        await query.edit_message_text(text=nuevo_texto, parse_mode="Markdown", reply_markup=teclado)

    except Exception as e:
        logging.error(f"Error actualizando el estado: {e}")
        await query.answer("❌ Error al intentar refrescar los datos.")


def register_status_handler(application) -> None:
    """Registra los handlers necesarios para el comando /status y su botón de refresco"""
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CallbackQueryHandler(status_refresh_callback, pattern="^refresh_status$"))