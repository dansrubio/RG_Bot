"""
Sistema de verificación automática de nuevos usuarios en grupos
- Silencia a nuevos usuarios hasta verificar
- Verificación con botón que redirige al privado del bot, persistencia por usuario y grupo
- Limpieza automática de mensajes y expulsión si no verifican
"""

import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import ContextTypes, MessageHandler, filters

from config import GROUP_ADMIN_ID, BOT_URL
from database.crud.usuario_crud import UsuarioCRUD

PERMISOS_VERIFICACION = ChatPermissions(can_send_messages=False)

PERMISOS_NORMAL = ChatPermissions(
    can_send_messages=True,
    can_send_other_messages=True,  # cubre audios, fotos, videos, docs, etc.
    can_send_polls=True,
    can_add_web_page_previews=True,
    can_invite_users=True,
    can_change_info=False,
    can_pin_messages=False
)

bienvenida_pendiente = {}

async def nuevo_usuario_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler: Detecta nuevos usuarios en grupos y aplica verificación automática
    """
    try:
        message = update.effective_message
        chat = update.effective_chat

        # Solo filtra grupos administrados
        if chat.id not in GROUP_ADMIN_ID:
            return

        for miembro in update.message.new_chat_members:
            user_id = miembro.id
            username = miembro.username

            # Verificar si el usuario está en la base de datos
            usuario = UsuarioCRUD.crear_o_actualizar_usuario(user_id)

            # Verificar estado directamente en Telegram
            miembro = await context.bot.get_chat_member(chat.id, user_id)
            if miembro.status in ['restricted', 'kicked']:
                logging.info(f"Usuario {user_id} ya está restringido o expulsado en {chat.id}, sin acción")
                continue

            if usuario.esta_verificado:
                logging.info(f"Usuario {user_id} ya verificado en grupo {chat.id}, sin acción")
                continue

            try:
                await context.bot.restrict_chat_member(
                    chat_id=chat.id,
                    user_id=user_id,
                    permissions=PERMISOS_VERIFICACION
                )
                logging.info(f"Silenciado nuevo usuario {user_id} en {chat.id}")
            except Exception as e:
                logging.error(f"No se pudo silenciar a {user_id} en {chat.id}: {e}")

            # Botón que redirige al bot privado con parámetro /start
            url_verificacion = f"{BOT_URL}?start=verificar_{chat.id}_{user_id}"
            boton = InlineKeyboardMarkup([[
                InlineKeyboardButton("🟢 VERIFICARME 🟢", url=url_verificacion)
            ]])

            bienvenida = await message.reply_text(
                f"👋 Bienvenido @{username or user_id}! Para participar, pulsa el botón de verificación.",
                reply_markup=boton
            )

            task = asyncio.create_task(
                manejar_expulsion_y_limpieza(context, chat.id, user_id, bienvenida.message_id)
            )
            bienvenida_pendiente[(chat.id, user_id)] = {
                'msg_id': bienvenida.message_id,
                'timer': task
            }

    except Exception as e:
        logging.error(f"Error en nuevo_usuario_handler: {e}")

async def manejar_expulsion_y_limpieza(context, group_id, user_id, msg_id):
    """
    Espera 5 minutos, si el usuario no verifica, borra mensaje y expulsa usuario
    """
    try:
        await asyncio.sleep(5 * 60)
        if UsuarioCRUD.esta_verificado(user_id, group_id):
            return
        try:
            await context.bot.delete_message(chat_id=group_id, message_id=msg_id)
        except Exception:
            pass
        try:
            await context.bot.ban_chat_member(chat_id=group_id, user_id=user_id)
            await context.bot.unban_chat_member(chat_id=group_id, user_id=user_id)
            logging.info(f"Usuario {user_id} expulsado de {group_id} por no verificar")
        except Exception as e:
            logging.error(f"No se pudo expulsar a {user_id} de {group_id}: {e}")
        key = (group_id, user_id)
        if key in bienvenida_pendiente:
            del bienvenida_pendiente[key]
    except Exception as e:
        logging.error(f"Error en manejar_expulsion_y_limpieza: {e}")

def register_verification_handler(application):
    """
    Registra el sistema de verificación en la aplicación de Telegram
    """
    try:
        application.add_handler(
            MessageHandler(
                filters.StatusUpdate.NEW_CHAT_MEMBERS,
                nuevo_usuario_handler
            )
        )
    except Exception as e:
        logging.error(f"Error registrando verification handler: {e}")