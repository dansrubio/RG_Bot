import logging
import time
import os
import sys
import psutil
import platform
from datetime import datetime, timezone
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from config import ADMIN_IDS

# Guardamos el tiempo en que se inició el bot
BOT_START_TIME = time.time()


def _formatear_uptime(dt_inicio: datetime) -> str:
    """Calcula el tiempo transcurrido desde dt_inicio (UTC) como string legible"""
    delta = datetime.now(timezone.utc) - dt_inicio
    return str(delta).split(".")[0]


def _obtener_estado_userbot() -> dict | None:
    """
    Importa y retorna el estado del userbot de forma segura.
    Retorna None si el módulo no está disponible.
    """
    try:
        from userbot_indexer import get_estado_userbot
        return get_estado_userbot()
    except Exception:
        return None


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /status - Muestra información avanzada del sistema y bot

    - Si lo usa un administrador (ADMIN_IDS): muestra info avanzada + estado del userbot.
    - Si lo usa cualquier otro usuario: muestra un mensaje simple con latencia y uptime del bot.
    """
    try:
        user_id  = update.effective_user.id if update.effective_user else None
        is_admin = user_id in ADMIN_IDS

        # ⚡ Latencia (ping bot -> Telegram) - medimos siempre
        start        = time.time()
        sent_message = await update.message.reply_text("⏳ Midiendo latencia...")
        end          = time.time()
        latency_ms   = int((end - start) * 1000)
        try:
            await sent_message.delete()
        except Exception:
            pass

        # ⏱️ Uptime del BOT (no del sistema)
        bot_uptime = str(datetime.now(timezone.utc) - datetime.fromtimestamp(BOT_START_TIME, tz=timezone.utc)).split(".")[0]

        if not is_admin:  # mensaje simplificado para usuarios normales
            simple_message = (
                "✅ ¡El bot se encuentra activo!\n"
                "Usa el comando /start para comenzar.\n\n"
                f"Latencia: {latency_ms} ms\n"
                f"Uptime bot: {bot_uptime}"
            )
            await update.message.reply_text(simple_message)
            return

        # === A partir de aquí: respuesta completa para administradores ===

        # 📊 Info básica del sistema
        cpu_usage = psutil.cpu_percent(interval=1)
        memory    = psutil.virtual_memory()
        disk      = psutil.disk_usage("/")
        boot_time = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
        uptime    = datetime.now(timezone.utc) - boot_time
        python_version = sys.version.split()[0]

        # 🛠️ Info de red
        net_io       = psutil.net_io_counters()
        network_info = f"↑ {net_io.bytes_sent / (1024 ** 2):.2f} MB | ↓ {net_io.bytes_recv / (1024 ** 2):.2f} MB"

        # 🌡️ Temperatura de CPU (segura con fallback)
        cpu_temp = "No disponible"
        try:
            if hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures()
                if temps:
                    if "coretemp" in temps:
                        cpu_temp = f"{temps['coretemp'][0].current}°C"
                    elif "cpu-thermal" in temps:  # Raspberry / ARM
                        cpu_temp = f"{temps['cpu-thermal'][0].current}°C"
            if cpu_temp == "No disponible" and os.path.exists("/sys/class/thermal/thermal_zone0/temp"):
                with open("/sys/class/thermal/thermal_zone0/temp") as f:
                    cpu_temp = f"{int(f.read().strip()) / 1000:.1f}°C"
        except Exception:
            cpu_temp = "No soportado"

        # 🧾 Procesos que más consumen CPU/RAM
        try:
            top_processes = sorted(
                psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
                key=lambda p: p.info.get("cpu_percent", 0),
                reverse=True
            )[:3]
            process_list = "\n".join([
                f"  ├ {p.info.get('name','unknown')} (PID {p.info.get('pid','?')}): "
                f"CPU {p.info.get('cpu_percent',0)}% | RAM {p.info.get('memory_percent',0):.1f}%"
                for p in top_processes
            ]) if top_processes else "  └ No disponible"
        except Exception:
            process_list = "  └ No disponible"

        # 📈 Carga promedio del sistema
        load_avg = os.getloadavg() if hasattr(os, "getloadavg") else ("N/A", "N/A", "N/A")

        # 🤖 Estado del userbot
        estado_ub = _obtener_estado_userbot()
        if estado_ub is None:
            userbot_seccion = "🤖 *Userbot:*\n└ No disponible (módulo no cargado)\n"
        else:
            ub_icono  = "✅" if estado_ub["conectado"] else "❌"
            ub_estado = "Conectado" if estado_ub["conectado"] else "Desconectado"

            ub_desde = "—"
            if estado_ub["conectado_desde"]:
                ub_desde = _formatear_uptime(estado_ub["conectado_desde"])

            ub_ultimo_index = "—"
            if estado_ub["ultimo_index"]:
                delta_index     = datetime.now(timezone.utc) - estado_ub["ultimo_index"]
                mins            = int(delta_index.total_seconds() // 60)
                ub_ultimo_index = f"hace {mins} min" if mins < 60 else estado_ub["ultimo_index"].strftime("%d/%m %H:%M UTC")

            ub_indexados = estado_ub["elementos_indexados_total"]
            ub_error     = estado_ub["ultimo_error"] or "Ninguno"

            userbot_seccion = (
                f"🤖 *Userbot:*\n"
                f"├ Estado: {ub_icono} {ub_estado}\n"
                f"├ Activo desde: {ub_desde}\n"
                f"├ Último /index: {ub_ultimo_index}\n"
                f"├ Elementos indexados (sesión): {ub_indexados}\n"
                f"└ Último error: {ub_error[:80]}\n"
            )

        # 📩 Construcción del mensaje completo para admins
        status_message = (
            "📊 *Estado del Sistema:*\n"
            f"├ CPU: {cpu_usage}%\n"
            f"├ RAM: {memory.percent}% usado\n"
            f"├ Disco: {disk.percent}% usado\n"
            f"├ SO: {platform.system()} {platform.release()}\n"
            f"├ Python: {python_version}\n"
            f"├ Uptime sistema: {str(uptime).split('.')[0]}\n"
            f"└ Uptime bot: {bot_uptime}\n\n"
            "⚡ *Latencia:*\n"
            f"└ {latency_ms} ms\n\n"
            "🛠️ *Red:*\n"
            f"└ {network_info}\n\n"
            "🌡️ *Temperatura CPU:*\n"
            f"└ {cpu_temp}\n\n"
            "🧾 *Top procesos:*\n"
            f"{process_list}\n\n"
            "📈 *Carga Promedio:*\n"
            f"└ 1m: {load_avg[0]} | 5m: {load_avg[1]} | 15m: {load_avg[2]}\n\n"
            f"{userbot_seccion}"
        )

        await update.message.reply_text(status_message, parse_mode="Markdown")

    except Exception as e:
        logging.error(f"Error en /status: {e}")
        try:
            await update.message.reply_text("❌ Error obteniendo estado del sistema.")
        except Exception:
            logging.error("No se pudo notificar al usuario sobre el error.")


def register_status_handler(application) -> None:
    """Registra el handler para /status"""
    application.add_handler(CommandHandler("status", status_command))