"""
Handler simplificado para el comando /wow_token
Solo maneja la consulta de precios actuales
"""

import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode
from pathlib import Path

from helpers.wow_token_service import WoWTokenService

logger = logging.getLogger(__name__)


async def token_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /wow_token para mostrar precios actuales"""
    try:
        service = WoWTokenService()

        # Obtener datos del token
        mensaje, imagen_path = await service.get_token_message()

        if not mensaje:
            await update.message.reply_text(
                "❌ No se pudieron obtener los precios del token.",
                parse_mode=ParseMode.HTML
            )
            return

        # Intentar enviar con imagen si está disponible
        message_sent = False

        if imagen_path and Path(imagen_path).exists():
            try:
                with open(imagen_path, 'rb') as photo:
                    await update.message.reply_photo(
                        photo=photo,
                        caption=mensaje,
                        parse_mode=ParseMode.HTML
                    )
                message_sent = True
                logger.debug("✅ Mensaje con imagen enviado correctamente")
            except Exception as e:
                logger.error(f"❌ Error enviando imagen: {e}")

        # Enviar solo texto si no se pudo enviar la imagen
        if not message_sent:
            await update.message.reply_text(
                mensaje,
                parse_mode=ParseMode.HTML
            )
            logger.debug("✅ Mensaje de texto enviado")

        logger.info(f"Usuario {update.effective_user.id} consultó precios de WoW Token")

    except Exception as e:
        logger.error(f"Error en comando /wow_token: {e}")
        await update.message.reply_text(
            "❌ Error interno al obtener los precios del token.",
            parse_mode=ParseMode.HTML
        )


async def debug_token_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando de debug para diagnosticar problemas con la API"""
    try:
        await update.message.reply_text("🔍 Ejecutando diagnóstico de WoW Token API...")

        # Test directo de la API
        import aiohttp
        async with aiohttp.ClientSession() as session:
            try:
                # Test retail
                async with session.get("https://data.wowtoken.app/v2/current/retail.json", timeout=15) as response:
                    if response.status == 200:
                        retail_data = await response.json()
                        retail_text = f"✅ Retail API: OK ({len(retail_data)} regiones)"
                        for region, data in retail_data.items():
                            if isinstance(data, list) and len(data) >= 2:
                                retail_text += f"\n  - {region}: {data[1]} oro"
                    else:
                        retail_text = f"❌ Retail API: Error {response.status}"

                # Test classic
                async with session.get("https://data.wowtoken.app/v2/current/classic.json", timeout=15) as response:
                    if response.status == 200:
                        classic_data = await response.json()
                        classic_text = f"✅ Classic API: OK ({len(classic_data)} regiones)"
                        for region, data in classic_data.items():
                            if isinstance(data, list) and len(data) >= 2:
                                classic_text += f"\n  - {region}: {data[1]} oro"
                    else:
                        classic_text = f"❌ Classic API: Error {response.status}"

            except Exception as e:
                retail_text = f"❌ Retail API: Excepción {e}"
                classic_text = f"❌ Classic API: Excepción {e}"

        debug_message = f"""🔍 <b>Diagnóstico WoW Token API</b>

{retail_text}

{classic_text}

🌐 <b>URLs probadas:</b>
- https://data.wowtoken.app/v2/current/retail.json  
- https://data.wowtoken.app/v2/current/classic.json

💡 <b>Nota:</b> Este bot obtiene datos en tiempo real sin almacenamiento."""

        await update.message.reply_text(debug_message, parse_mode=ParseMode.HTML)

    except Exception as e:
        await update.message.reply_text(f"❌ Error en diagnóstico: {e}")


def register_wow_token_handlers(application: Application) -> None:
    """Registra los handlers de WoW Token en la aplicación"""
    try:
        application.add_handler(CommandHandler("wow_token", token_command))
        application.add_handler(CommandHandler("debug_token", debug_token_command))

    except Exception as e:
        logger.error(f"❌ Error registrando handlers de WoW Token: {e}")
        raise