"""
Bot de Telegram - Punto de entrada principal
Lanza el bot principal y el userbot indexador en el mismo event loop.
Maneja tanto conexiones sincrónicas como asincrónicas a MongoDB.
"""

import asyncio
import logging
import sys
import io

# Configurar stdout con codificación UTF-8 para emojis en Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Silenciar librerías externas ANTES de sus imports para evitar logs de inicialización
for _lib in ["httpx", "httpcore", "telegram", "telethon", "telethon.crypto"]:
    logging.getLogger(_lib).setLevel(logging.CRITICAL)

from telegram import Update
from telegram.ext import Application

from config import BOT_TOKEN, validate_config
from database.manager import setup_database, shutdown_database
from database.base import close_async_database

from admin.db_backup import register_db_backup_handler
from admin.db_restore import register_db_restore_handler
from admin.status import register_status_handler
from admin.elemento_handler import register_elemento_handlers
from admin.juego_aleatorio_handler import register_juego_aleatorio_handler
from admin.top_elementos_handler import register_top_elementos_handler
from admin.busqueda_elemento_handler import register_busqueda_elemento_handler
from admin.notify_handler import register_notify_handler
from admin.mod_manager import register_mod_manager_handlers
from admin.index_publisher_handler import register_index_publisher_handler
from admin.stats_handler import register_stats_handlers
from admin.recomendaciones_handler import register_recomendaciones_handlers

from automation.message_tracker import register_message_tracker
from automation.cleaner import register_cleaner
from automation.hashtag_forwarder import register_hashtag_forwarder
from automation.start_handler import register_start_handler
from automation.verification_handler import register_verification_handler
from automation.catalogo_handler import register_catalogo_handler
from automation.yugioh_handler import register_yugioh_handler
from automation.pokedex_handler import register_pokedex_handler
from automation.autoliker_userbot import registrar_autoliker_userbot

from external_apis.rebrandly import register_rebrandly_handler
from external_apis.qr_generator import register_qr_handler
from external_apis.free_games import register_free_games_handler
from external_apis.steam_api import register_game_handlers
from external_apis.tmdb_api import register_cine_handlers  
from external_apis.igdb_api import register_ps4_handlers
from external_apis.game_search import register_search_handler

from helpers.auto_publisher import register_auto_publisher
from helpers.random_handler import register_random_handler
from helpers.wow_token_handler import register_wow_token_handlers
from helpers.auto_response import register_auto_response_handler
from helpers.daily_summary import register_daily_summary
from helpers.watchdog import register_watchdog
from helpers.user_command import register_user_command_handler

from userbot.manager import iniciar_userbot

logger = logging.getLogger(__name__)


def configurar_logging():
    """Configura logging para mostrar solo errores críticos"""
    logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(message)s',
        level=logging.INFO,
        handlers=[logging.StreamHandler(sys.stdout)]
    )


def registrar_handlers(app: Application):
    """Registra todos los handlers del bot de forma organizada"""
    handlers = [
        register_message_tracker, register_cleaner, register_hashtag_forwarder, 
        register_start_handler, register_verification_handler, register_rebrandly_handler, 
        register_qr_handler, register_auto_publisher, register_catalogo_handler,
        register_random_handler, register_wow_token_handlers, register_status_handler, 
        register_elemento_handlers, register_free_games_handler, register_pokedex_handler, 
        register_yugioh_handler, register_top_elementos_handler, register_juego_aleatorio_handler, 
        register_daily_summary, register_busqueda_elemento_handler, register_index_publisher_handler,
        register_db_backup_handler, register_db_restore_handler, register_notify_handler, 
        register_mod_manager_handlers, register_stats_handlers, register_user_command_handler, register_watchdog, 
        register_auto_response_handler, register_recomendaciones_handlers,
    ]

    for registrar in handlers:
        try:
            registrar(app)
        except Exception as e:
            logger.error(f"Error registrando {registrar.__name__}: {e}")

    # ── Módulos de búsqueda ──
    modulos_busqueda = [
        (register_game_handlers, "game_handlers"),
        (register_cine_handlers, "cine_handlers"),
        (register_ps4_handlers, "ps4_handlers"),
        (register_search_handler, "search_handler (busqueda)")
    ]
    
    for registrar, nombre in modulos_busqueda:
        try:
            registrar(app)
        except Exception as e:
            logger.error(f"Error registrando {nombre}: {e}")


async def tarea_bot(app: Application):
    """Wrapper asíncrono para inicializar y arrancar el sondeo del bot principal"""
    try:
        await app.initialize()
        await app.start()
        print("🟢 BOT INICIADO CORRECTAMENTE 🟢", flush=True)
        sys.stdout.flush()
        
        await app.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
        # Este evento mantiene vivo el bot de forma asíncrona dentro de la tarea
        await asyncio.Event().wait()
    except Exception as e:
        logger.critical(
            f"💥 Bot principal falló: {e}\n"
            f"   → Si el error dice 'token rejected', regenera el token en BotFather."
        )
        raise
    finally:
        if app.updater.running:
            await app.updater.stop()
        if app.running:
            await app.stop()
        await app.shutdown()


async def tarea_userbot():
    """Wrapper asíncrono para el ciclo de vida del userbot"""
    try:
        await iniciar_userbot()
    except asyncio.CancelledError:
        logger.info("🛑 Userbot cancelado por el proceso principal.")
    except Exception as e:
        logger.error(
            f"⚠️ Userbot falló y fue desactivado: {e}\n"
            f"   → El bot principal sigue funcionando sin el userbot.\n"
            f"   → El comando /index no estará disponible hasta reiniciar."
        )


async def main_async():
    """Supervisa y corre el bot principal y el userbot de forma paralela y segura"""
    print("Configurando el bot...", flush=True)

    if not validate_config():
        logger.error("❌ Configuración inválida")
        return 1

    if not setup_database():
        logger.error("❌ Error en base de datos")
        return 1

    app = Application.builder().token(BOT_TOKEN).build()
    registrar_handlers(app)

    logger.info("🚀 Lanzando procesos concurrentes...")

    # Creamos las referencias de tareas explícitas
    bot_task = asyncio.create_task(tarea_bot(app))
    userbot_task = asyncio.create_task(tarea_userbot())

    try:
        # Monitoreamos la tarea del bot principal. Si cae, el flujo se rompe.
        await bot_task  
    except Exception as e:
        logger.error(f"💥 Detención del loop por fallo crítico en el bot: {e}")
    finally:
        # CORREGIDO: Evita que fallos tempranos del userbot fuercen un cierre de base de datos prematuro
        if not userbot_task.done():
            logger.info("Cerrando userbot de manera limpia...")
            userbot_task.cancel()
            try:
                await userbot_task
            except asyncio.CancelledError:
                pass

        print("🗄️ Apagando conexiones de bases de datos...")
        shutdown_database()

        from database.base import MOTOR_AVAILABLE
        if MOTOR_AVAILABLE:
            await close_async_database()

    return 0


def main():
    """Punto de entrada síncrono"""
    configurar_logging()
    try:
        return asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n🛑 Proceso interrumpido por el usuario (Ctrl+C). Exiting.")
        return 0


if __name__ == '__main__':
    sys.exit(main())