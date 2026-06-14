"""
Sistema de autorrespuesta a comandos del bot
Maneja comandos predefinidos con respuestas formateadas
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode
from config import BOT_REGLAMENTO_URL


async def donate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra información sobre donativos a la comunidad"""
    
    share_url = "https://t.me/share/url?url=%F0%9F%91%80%20Bro%2C%20%C3%A9chale%20un%20ojo%20a%20este%20canal%20%F0%9F%91%89%20%40Refugio_Gamer%20%2F%20Es%20un%20catalogo%20para%20descargar%20GRATIS%20Juegos%20para%20PC"
    
    mensaje = (
        "💌 <b>Apoya a la Comunidad Refugio Gamer</b>\n\n"
        
        "Refugio Gamer es un proyecto creado por y para la comunidad. "
        "Cada donativo nos ayuda a mantener servidores, mejorar herramientas "
        "y seguir ofreciendo un espacio gratuito, rápido y sin publicidad invasiva.\n\n"
        
        "⚡ <b>Los aportes son totalmente voluntarios.</b>\n"
        "Nada está bloqueado ni condicionado por donar. "
        "Simplemente ayudas a mantener vivo el proyecto.\n\n"
        
        "🪙 <b>Billeteras Disponibles</b>\n\n"
        
        "💵 <b>USDT — Red Solana</b>\n"
        "<code>5F6t9VMiJrPAr8qCHtux7UVeFEQmeqxKTvSRyESfHven</code>\n"
        
        "⚠️ <i>Enviar únicamente mediante la red Solana.</i>\n\n"
        
        "💵 <b>USDT — Red Tron (TRC20)</b>\n"
        "<code>TR3ApWUDS1phiYNsB8Uzz8BuPpNJgSia8V</code>\n"
        
        "⚠️ <i>Enviar únicamente mediante la red TRC20.</i>\n\n"
        
        "🟣 <b>Solana (SOL)</b>\n"
        "<code>GHK5aUw1wbFAc9LdKmwxybxvM5SfUJfvPECb6KkJAy5c</code>\n\n"
        
        "⚪ <b>Litecoin (LTC)</b>\n"
        "<code>ltc1qdxsu20sqym9s3k8agn398vcqnj2c3q04m0xlng</code>\n\n"
        
        "💳 <b>Donaciones en Moneda Nacional</b>\n\n"
        
        "🇨🇺 <b>Moneda Libremente Convertible (MLC)</b>\n"
        "<code>9225-0699-9096-5357</code>\n\n"
        
        "🇨🇺 <b>Peso Cubano (CUP)</b>\n"
        "<code>9224-0699-9261-3287</code>\n\n"
        
        "🤝 <b>¿No puedes donar?</b>\n"
        "Compartir nuestro canal con amigos también ayuda muchísimo 💚"
    )

    keyboard = [[InlineKeyboardButton("📢 Compartir canal", url=share_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        mensaje,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )

async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra información sobre el reglamento de la comunidad"""
    mensaje = (
        "📜 <b>Reglamento de la Comunidad</b>\n\n"
        "Puedes conocer el reglamento completo de nuestra comunidad accediendo a este post. "
        "Te invitamos a leerlo para mantener un espacio seguro, respetuoso y organizado para todos."
    )

    keyboard = [[InlineKeyboardButton("📖 Reglamento",
                                      url=BOT_REGLAMENTO_URL)]]  # Botón con enlace al reglamento
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(mensaje, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


def register_auto_response_handler(app: Application):
    """Registra los handlers de autorrespuesta"""
    app.add_handler(CommandHandler('donate', donate_command))  # Comando de donativos
    app.add_handler(CommandHandler('rules', rules_command))  # Comando de reglamento