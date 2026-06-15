"""
Comando /user para consultar información de usuarios
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from database.crud.usuario_crud import UsuarioCRUD


def _construir_nombre(usuario: dict) -> str:
    """Arma el nombre completo a partir del dict del usuario"""
    partes = [p for p in (usuario.get("name"), usuario.get("lastname")) if p]  # Filtra None
    if partes:
        return " ".join(partes)
    if usuario.get("username"):
        return f"@{usuario['username']}"
    return f"Usuario {usuario['_id']}"


async def user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not context.args:
            await update.message.reply_text("Uso: /user @username o /user ID")
            return

        query = context.args[0]
        usuario = None

        if query.startswith('@'):
            usuario = UsuarioCRUD.obtener_usuario_por_username(query)  # Busca por username
        elif query.isdigit():
            usuario = UsuarioCRUD.obtener_usuario(int(query))  # Busca por ID numérico
        else:
            await update.message.reply_text("Formato inválido. Usa @username o ID numérico.")
            return

        if not usuario:
            await update.message.reply_text(f"Usuario {query} no encontrado.")
            return

        nombre = _construir_nombre(usuario)  # Nombre legible sin crashear

        texto = (
            f"👤 <b>Usuario:</b> {nombre}\n"
            f"🆔 <b>ID:</b> <code>{usuario['_id']}</code>\n"
        )

        if usuario.get("username"):  # Solo muestra username si existe
            texto += f"📱 <b>Username:</b> @{usuario['username']}\n"

        rango = (usuario.get("rango") or "desconocido").title()  # .value ya no aplica, es string en el dict
        estado = (usuario.get("estado") or "desconocido").title()

        texto += (
            f"🎭 <b>Rango:</b> {rango}\n"
            f"🔄 <b>Estado:</b> {estado}\n"
            f"💬 <b>Mensajes:</b> {usuario.get('contador_mensajes', 0)}\n"
            f"⚠️ <b>Strikes:</b> {usuario.get('strikes', 0)}\n"
        )

        comentarios = usuario.get("comentario")
        if comentarios:  # Solo muestra si hay comentarios registrados
            ultimo = comentarios[-1] if isinstance(comentarios, list) else comentarios
            texto += f"📝 <b>Último comentario:</b> {ultimo}\n"

        await update.message.reply_text(texto, parse_mode="HTML")

    except Exception as e:
        logging.error(f"Error en comando /user: {e}")
        await update.message.reply_text("Error interno al consultar usuario.")


def register_user_command_handler(application):
    application.add_handler(CommandHandler("user", user_command))