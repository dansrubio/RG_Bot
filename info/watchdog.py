"""
Sistema de monitoreo y alertas del servidor
"""
import logging
import psutil

# Configuración de logging: solo muestra WARNING y ERROR de librerías externas
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO  # Tus logs propios se siguen mostrando
)

# Silenciar logs ruidosos de librerías externas
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)

# Estado de las últimas alertas para evitar spam
last_alert_state = {"cpu": False, "ram": False, "disk": False}
CPU_THRESHOLD = 110  # Umbral de CPU en %
RAM_THRESHOLD = 110  # Umbral de RAM en %
DISK_THRESHOLD = 110  # Umbral de disco en %


async def watchdog_task(application):
    """Tarea de monitoreo que se ejecuta periódicamente"""
    global last_alert_state

    from config import ADMIN_IDS  # Importación local

    cpu_usage = psutil.cpu_percent(interval=1)  # Obtener métricas del sistema
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('/')

    alerts = []

    # Verificar CPU
    if cpu_usage > CPU_THRESHOLD and not last_alert_state["cpu"]:
        alerts.append(f"⚠️ CPU alta: {cpu_usage}%")
        last_alert_state["cpu"] = True
    elif cpu_usage <= CPU_THRESHOLD:
        last_alert_state["cpu"] = False

    # Verificar RAM
    if ram.percent > RAM_THRESHOLD and not last_alert_state["ram"]:
        alerts.append(f"⚠️ RAM alta: {ram.percent}% ({ram.used / (1024 ** 3):.2f} GB usados)")
        last_alert_state["ram"] = True
    elif ram.percent <= RAM_THRESHOLD:
        last_alert_state["ram"] = False

    # Verificar disco
    if disk.percent > DISK_THRESHOLD and not last_alert_state["disk"]:
        alerts.append(f"⚠️ Disco casi lleno: {disk.percent}% ({disk.used / (1024 ** 3):.2f} GB usados)")
        last_alert_state["disk"] = True
    elif disk.percent <= DISK_THRESHOLD:
        last_alert_state["disk"] = False

    # Enviar alertas a administradores
    if alerts:
        alert_msg = "🚨 **ALERTA DEL SERVIDOR** 🚨\n" + "\n".join(alerts)
        for admin_id in ADMIN_IDS:
            try:
                await application.bot.send_message(
                    chat_id=admin_id,
                    text=alert_msg,
                    parse_mode="Markdown"
                )
            except Exception as e:
                logging.error(f"Error enviando alerta a admin {admin_id}: {e}")


def register_watchdog(application, interval_seconds=60):
    """Registra el sistema de monitoreo con intervalo configurable"""
    try:
        application.job_queue.run_repeating(
            lambda ctx: application.create_task(watchdog_task(application)),
            interval=interval_seconds,
            first=5  # Primer chequeo después de 5 segundos
        )
    except Exception as e:
        logging.error(f"❌ Error registrando watchdog: {e}")
