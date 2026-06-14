from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from .secure_keys import SecureKeyGenerator


async def random_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Genera claves seguras: contraseña, PIN y token de acceso"""

    try:
        # Crear instancia del generador
        generador = SecureKeyGenerator()

        # Generar todas las claves
        claves = generador.generar_conjunto_completo()

        # Formatear mensaje de respuesta
        mensaje = (
            "🔐 *Claves Seguras Generadas*\n\n"
            f"🔒 **Contraseña:** `{claves['contraseña']}`\n"
            f"📱 **PIN (4 dígitos):** `{claves['pin']}`\n"
            f"🎫 **Token (6 dígitos):** `{claves['token']}`\n\n"
            "⚠️ *Estas claves no son almacenadas por el bot*\n"
            "🔄 *Usa /random para generar nuevas claves*"
        )

        await update.message.reply_text(
            mensaje,
            parse_mode='Markdown'
        )

    except Exception as e:
        await update.message.reply_text(
            f"❌ Error al generar claves: {str(e)}",
            parse_mode='Markdown'
        )


def register_random_handler(application: Application):
    """Registra el handler del comando /random"""
    application.add_handler(CommandHandler("random", random_command))