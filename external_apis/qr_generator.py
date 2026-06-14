"""
Handler para generar códigos QR
"""
import logging
import httpx
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from urllib.parse import quote


async def qr_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Genera un código QR desde una URL proporcionada (solo administradores)"""
    from config import ADMIN_IDS  # Importación local para evitar dependencias circulares

    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:  # Verificar si el usuario es administrador
        await update.message.reply_text(
            "❌ Este comando solo está disponible para administradores.",
            reply_to_message_id=update.message.message_id
        )
        return

    if not context.args:  # Verificar que se haya proporcionado una URL
        await update.message.reply_text(
            "📖 **Uso:** `/qr <enlace>`\n\n"
            "**Ejemplo:** `/qr https://google.com`",
            parse_mode='Markdown',
            reply_to_message_id=update.message.message_id
        )
        return

    url_to_encode = ' '.join(context.args)  # Unir todos los argumentos en caso de espacios

    generating_msg = await update.message.reply_text(  # Enviar mensaje de "generando..."
        "🔄 Generando código QR...",
        reply_to_message_id=update.message.message_id
    )

    try:
        qr_image_url = await generate_qr_code(url_to_encode)  # Generar código QR usando la API

        if qr_image_url:
            try:
                await context.bot.send_photo(  # Enviar la imagen del código QR
                    chat_id=update.effective_chat.id,
                    photo=qr_image_url,
                    caption=f"✅ **Código QR generado**\n\n🔎 **Enlace:** `{url_to_encode}`",
                    parse_mode='Markdown',
                    reply_to_message_id=update.message.message_id
                )

                await generating_msg.delete()  # Eliminar mensaje de "generando..."

            except Exception as send_error:
                logging.error(f"Error al enviar imagen QR: {send_error}")
                await generating_msg.edit_text(
                    "❌ Error al enviar la imagen del código QR. "
                    "La API puede estar temporalmente no disponible."
                )

        else:
            await generating_msg.edit_text(
                "❌ No se pudo generar el código QR. "
                "Verifica que el enlace sea válido o inténtalo más tarde."
            )

    except Exception as e:
        logging.error(f"Error en comando /qr: {e}")
        await generating_msg.edit_text(
            "❌ Error interno al generar el código QR. Contacta al desarrollador."
        )


async def generate_qr_code(text: str) -> str:
    """Genera un código QR usando la API de qrserver.com (más confiable)"""
    try:
        params = {  # Configuración del QR - usando API más confiable
            'size': '1000x1000',  # Tamaño en píxeles (formato widthxheight)
            'ecc': 'H',  # Nivel de corrección de errores alto (H, Q, M, L)
            'color': '000000',  # Color del código (negro)
            'bgcolor': 'ffffff',  # Color de fondo (blanco)
            'data': text  # Texto a codificar
        }

        base_url = "https://api.qrserver.com/v1/create-qr-code/"  # API más confiable y estable

        param_string = '&'.join([f"{key}={quote(str(value))}" for key, value in params.items()])  # Crear la URL con parámetros
        qr_url = f"{base_url}?{param_string}"

        logging.info(f"Generando QR para URL: {qr_url}")  # Debug: mostrar URL generada

        async with httpx.AsyncClient(  # Verificar que la URL de la API responde correctamente
                timeout=20.0,
                follow_redirects=True,
                headers={'User-Agent': 'Mozilla/5.0 (compatible; TelegramBot)'}
        ) as client:
            try:
                response = await client.get(qr_url)

                if response.status_code == 200:
                    content_type = response.headers.get('content-type', '').lower()  # Verificar que el contenido sea una imagen
                    if 'image' in content_type or 'png' in content_type:
                        logging.info(f"QR generado exitosamente. Content-Type: {content_type}")
                        return qr_url
                    else:
                        logging.error(f"Respuesta no es una imagen. Content-Type: {content_type}")
                        return await generate_qr_code_alternative(text)  # Intentar con API alternativa
                else:
                    logging.error(f"API QR respondió con status {response.status_code}")
                    return await generate_qr_code_alternative(text)

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                logging.error(f"Error de conexión con API principal: {e}")
                return await generate_qr_code_alternative(text)

    except Exception as e:
        logging.error(f"Error al generar código QR: {e}")
        return await generate_qr_code_alternative(text)


async def generate_qr_code_alternative(text: str) -> str:
    """API alternativa para generar códigos QR (quickchart.io)"""
    try:
        params = {  # Configuración para API alternativa
            'text': text,
            'size': '1000',
            'format': 'png',
            'errorCorrectionLevel': 'H',
            'margin': 1,
            'dark': '000000',
            'light': 'ffffff'
        }

        base_url = "https://quickchart.io/qr"
        param_string = '&'.join([f"{key}={quote(str(value))}" for key, value in params.items()])
        qr_url = f"{base_url}?{param_string}"

        logging.info(f"Intentando API alternativa: {qr_url}")

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(qr_url)

            if response.status_code == 200:
                content_type = response.headers.get('content-type', '').lower()
                if 'image' in content_type or 'png' in content_type:
                    logging.info(f"QR generado con API alternativa. Content-Type: {content_type}")
                    return qr_url

            logging.error(f"API alternativa falló con status {response.status_code}")
            return None

    except Exception as e:
        logging.error(f"Error con API alternativa: {e}")
        return None


def register_qr_handler(application) -> None:
    """Registra el handler del comando /qr en la aplicación"""
    try:
        application.add_handler(CommandHandler("qr", qr_command))
    except Exception as e:
        logging.error(f"❌ Error registrando handler /qr: {e}")