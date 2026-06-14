"""
Comandos para información de usuarios y chats
"""
import logging
from telegram import Update, User
from telegram.ext import ContextTypes, CommandHandler
import html


async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra información de un usuario mencionado o respondido"""
    message = update.effective_message
    user: User = None

    if message and message.reply_to_message:  # Si es respuesta a un mensaje
        user = message.reply_to_message.from_user
    elif context.args:  # Si se pasa @username como argumento
        username = context.args[0].lstrip('@')
        try:
            chat = update.effective_chat
            member = await context.bot.get_chat_member(chat.id, username)
            user = member.user
        except Exception:
            await message.reply_text("❌ No se pudo encontrar ese usuario en este chat.")
            return
    else:
        await message.reply_text("Responde a un mensaje o usa /info @username para ver información de un usuario.")
        return

    text = (
        f"👤 <b>Información de usuario</b>\n"
        f"• Nombre: {html.escape(user.full_name)}\n"
        f"• Username: @{user.username if user.username else 'Sin username'}\n"
        f"• ID: <code>{user.id}</code>\n"
        f"• ¿Bot?: {'Sí' if user.is_bot else 'No'}\n"
        f"• ¿Premium?: {'Sí' if getattr(user, 'is_premium', False) else 'No'}"
    )
    await message.reply_text(text, parse_mode="HTML")


async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el ID del chat (grupo o privado) donde se usa el comando"""
    chat = update.effective_chat
    chat_type = {
        "private": "Privado",
        "group": "Grupo",
        "supergroup": "Supergrupo"
    }.get(chat.type, chat.type)

    text = (
        f"🆔 <b>ID del chat</b>\n"
        f"• Tipo: {chat_type}\n"
        f"• Título: {html.escape(chat.title) if chat.title else 'Privado'}\n"
        f"• ID: <code>{chat.id}</code>"
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def mi_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra información del usuario que usa el comando"""
    user = update.effective_user
    text = (
        f"👤 <b>Tu información</b>\n"
        f"• Nombre: {html.escape(user.full_name)}\n"
        f"• Username: @{user.username if user.username else 'Sin username'}\n"
        f"• ID: <code>{user.id}</code>\n"
        f"• ¿Bot?: {'Sí' if user.is_bot else 'No'}\n"
        f"• ¿Premium?: {'Sí' if getattr(user, 'is_premium', False) else 'No'}"
    )
    await update.effective_message.reply_text(text, parse_mode="HTML")


def register_userinfo_handlers(application):
    """Registra los comandos relacionados con información de usuarios y grupos"""
    try:
        application.add_handler(CommandHandler("info", info_command))  # Información de otros usuarios
        application.add_handler(CommandHandler("id", id_command))  # ID del chat actual
        application.add_handler(CommandHandler("mi_info", mi_info_command))  # Tu propia información
    except Exception as e:
        logging.error(f"❌ Error registrando handlers de información: {e}")