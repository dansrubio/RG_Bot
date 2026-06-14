"""
Sistema de notificaciones masivas para administradores
Permite enviar mensajes personalizados a todos los usuarios del bot
"""

import logging
import warnings
import asyncio
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters
)
from telegram.constants import ParseMode
from telegram.error import TelegramError, Forbidden, BadRequest
from telegram.warnings import PTBUserWarning  # Importar la clase específica
from config import is_admin
from database.base import get_database

warnings.filterwarnings('ignore', category=PTBUserWarning)  # Silenciar warnings específicos de PTB

TEXTO, IMAGEN, BOTONES, CONFIRMAR = range(4)  # Estados del wizard

# Configuración
MAX_REINTENTOS = 3  # Intentos por usuario fallido
DELAY_ENTRE_ENVIOS = 0.05  # Segundos entre envíos (evita rate limit)
BATCH_SIZE = 30  # Usuarios por lote (Telegram permite ~30 msg/segundo)


class NotifySystem:
    """Sistema de notificaciones masivas"""

    @staticmethod
    async def comando_notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Inicia el proceso de notificación masiva (solo admins)"""
        if not update.message:  # Validar que existe el mensaje
            return ConversationHandler.END

        user_id = update.effective_user.id

        if not is_admin(user_id):  # Verificar permisos
            await update.message.reply_text("❌ No tienes permisos para usar este comando.")
            return ConversationHandler.END

        context.user_data.clear()  # Limpiar datos previos

        mensaje = (
            "📢 <b>Sistema de Notificaciones Masivas</b>\n\n"
            "Vamos a crear un mensaje para enviar a todos los usuarios.\n\n"
            "📝 <b>Paso 1/4:</b> Envía el texto del mensaje.\n"
            "Puedes usar formato HTML (<b>negrita</b>, <i>cursiva</i>, etc.)\n\n"
            "Escribe /cancelar en cualquier momento para abortar."
        )
        await update.message.reply_text(mensaje, parse_mode=ParseMode.HTML)
        return TEXTO

    @staticmethod
    async def recibir_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Recibe el texto del mensaje"""
        if not update.message or not update.message.text:  # Validar mensaje
            return TEXTO

        if update.message.text == "/cancelar":
            await update.message.reply_text("❌ Proceso cancelado.")
            return ConversationHandler.END

        if len(update.message.text) > 1024:  # Validar longitud (límite de caption en Telegram)
            await update.message.reply_text("❌ El texto es demasiado largo (máximo 1024 caracteres).")
            return TEXTO

        context.user_data['texto'] = update.message.text_html  # Guardar texto con formato HTML

        mensaje = (
            "✅ Texto guardado.\n\n"
            "🖼️ <b>Paso 2/4:</b> Envía una imagen (opcional).\n\n"
            "Puedes:\n"
            "• Enviar una foto\n"
            "• Enviar una URL de imagen\n"
            "• Escribir /saltar para omitir"
        )
        await update.message.reply_text(mensaje, parse_mode=ParseMode.HTML)
        return IMAGEN

    @staticmethod
    async def recibir_imagen(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Recibe la imagen (foto o URL)"""
        if not update.message:  # Validar mensaje
            return IMAGEN

        if update.message.text == "/cancelar":
            await update.message.reply_text("❌ Proceso cancelado.")
            return ConversationHandler.END

        if update.message.text == "/saltar":  # Omitir imagen
            context.user_data['imagen'] = None
            context.user_data['imagen_tipo'] = None
        elif update.message.photo:  # Foto enviada
            context.user_data['imagen'] = update.message.photo[-1].file_id
            context.user_data['imagen_tipo'] = 'file_id'
        elif update.message.text and update.message.text.startswith(('http://', 'https://')):  # URL enviada
            context.user_data['imagen'] = update.message.text
            context.user_data['imagen_tipo'] = 'url'
        else:
            await update.message.reply_text("❌ Por favor envía una foto, una URL válida o /saltar")
            return IMAGEN

        mensaje = (
            "✅ Imagen configurada.\n\n"
            "🔘 <b>Paso 3/4:</b> Configura botones (opcional).\n\n"
            "Formato: <code>Texto | URL</code>\n"
            "Ejemplo: <code>Ver más | https://ejemplo.com</code>\n\n"
            "Puedes enviar varios botones, uno por línea.\n"
            "Escribe /saltar para omitir."
        )
        await update.message.reply_text(mensaje, parse_mode=ParseMode.HTML)
        return BOTONES

    @staticmethod
    async def recibir_botones(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Recibe los botones inline"""
        if not update.message or not update.message.text:  # Validar mensaje
            return BOTONES

        if update.message.text == "/cancelar":
            await update.message.reply_text("❌ Proceso cancelado.")
            return ConversationHandler.END

        if update.message.text == "/saltar":  # Omitir botones
            context.user_data['botones'] = []
        else:
            try:
                botones = []
                lineas = update.message.text.strip().split('\n')

                if len(lineas) > 8:  # Límite de botones (Telegram permite máximo 8 filas)
                    await update.message.reply_text("❌ Máximo 8 botones permitidos.")
                    return BOTONES

                for linea in lineas:
                    if not linea.strip():  # Ignorar líneas vacías
                        continue

                    if '|' not in linea:
                        await update.message.reply_text(
                            "❌ Formato incorrecto. Usa: <code>Texto | URL</code>",
                            parse_mode=ParseMode.HTML
                        )
                        return BOTONES

                    texto, url = linea.split('|', 1)
                    texto = texto.strip()
                    url = url.strip()

                    if not texto or len(texto) > 64:  # Validar texto del botón
                        await update.message.reply_text("❌ El texto del botón debe tener entre 1 y 64 caracteres.")
                        return BOTONES

                    if not url.startswith(('http://', 'https://')):
                        await update.message.reply_text("❌ La URL debe comenzar con http:// o https://")
                        return BOTONES

                    botones.append({'texto': texto, 'url': url})

                context.user_data['botones'] = botones

            except Exception as e:
                logging.error(f"Error procesando botones: {e}")
                await update.message.reply_text("❌ Error al procesar los botones. Intenta de nuevo.")
                return BOTONES

        return await NotifySystem.mostrar_preview(update, context)  # Mostrar vista previa

    @staticmethod
    async def mostrar_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Muestra vista previa del mensaje y pide confirmación"""
        texto = context.user_data.get('texto', '')
        imagen = context.user_data.get('imagen')
        imagen_tipo = context.user_data.get('imagen_tipo')
        botones = context.user_data.get('botones', [])

        keyboard = []  # Crear teclado con botones configurados
        for boton in botones:
            keyboard.append([InlineKeyboardButton(boton['texto'], url=boton['url'])])

        keyboard.append([  # Agregar botones de confirmación
            InlineKeyboardButton("✅ Enviar", callback_data="notify_confirm"),
            InlineKeyboardButton("❌ Cancelar", callback_data="notify_cancel")
        ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        mensaje_preview = (
            "👀 <b>Vista Previa del Mensaje</b>\n\n"
            "Este es el mensaje que se enviará a todos los usuarios:\n"
            "━━━━━━━━━━━━━━━━━━━\n\n"
        )

        try:
            if imagen:  # Enviar preview con imagen si existe
                msg = await update.message.reply_photo(
                    photo=imagen,
                    caption=texto,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                )
            else:  # Enviar preview sin imagen
                msg = await update.message.reply_text(
                    mensaje_preview + texto,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                )

            context.user_data['preview_message_id'] = msg.message_id  # Guardar ID del mensaje

        except BadRequest as e:
            logging.error(f"Error en formato HTML: {e}")
            await update.message.reply_text(
                "❌ Error en el formato HTML del mensaje. Verifica las etiquetas."
            )
            return ConversationHandler.END
        except Exception as e:
            logging.error(f"Error mostrando preview: {e}")
            await update.message.reply_text(
                "❌ Error al generar la vista previa. Intenta de nuevo."
            )
            return ConversationHandler.END

        return CONFIRMAR

    @staticmethod
    async def enviar_mensaje_usuario(
            context: ContextTypes.DEFAULT_TYPE,
            user_id: int,
            texto: str,
            imagen: Optional[str],
            imagen_tipo: Optional[str],
            reply_markup: Optional[InlineKeyboardMarkup]
    ) -> tuple[bool, str]:
        """Envía mensaje a un usuario con reintentos"""
        for intento in range(MAX_REINTENTOS):
            try:
                if imagen:
                    await context.bot.send_photo(
                        chat_id=user_id,
                        photo=imagen,
                        caption=texto,
                        reply_markup=reply_markup,
                        parse_mode=ParseMode.HTML
                    )
                else:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=texto,
                        reply_markup=reply_markup,
                        parse_mode=ParseMode.HTML
                    )
                return True, "success"  # Envío exitoso

            except Forbidden:
                return False, "blocked"  # Usuario bloqueó el bot
            except BadRequest as e:
                if "chat not found" in str(e).lower():
                    return False, "not_found"  # Chat no encontrado
                return False, "bad_request"  # Otro error de solicitud
            except TelegramError as e:
                if intento < MAX_REINTENTOS - 1:  # Reintentar si no es el último intento
                    await asyncio.sleep(1)  # Esperar antes de reintentar
                    continue
                logging.error(f"Error enviando a {user_id}: {e}")
                return False, "error"  # Error desconocido

        return False, "max_retries"  # Se agotaron los reintentos

    @staticmethod
    async def confirmar_envio(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Procesa la confirmación y envía el mensaje masivo"""
        query = update.callback_query
        await query.answer()

        if query.data == "notify_cancel":
            try:
                if query.message.photo:
                    await query.edit_message_caption(caption="❌ Envío cancelado.", reply_markup=None)
                else:
                    await query.edit_message_text("❌ Envío cancelado.", reply_markup=None)
            except Exception:
                pass  # Ignorar errores al editar mensaje
            context.user_data.clear()
            return ConversationHandler.END

        texto = context.user_data.get('texto', '')  # Obtener datos del mensaje
        imagen = context.user_data.get('imagen')
        imagen_tipo = context.user_data.get('imagen_tipo')
        botones = context.user_data.get('botones', [])

        keyboard = []  # Crear teclado final
        for boton in botones:
            keyboard.append([InlineKeyboardButton(boton['texto'], url=boton['url'])])

        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

        try:  # Notificar inicio de envío
            if query.message.photo:
                await query.edit_message_caption(caption="📤 Iniciando envío masivo...", reply_markup=None)
            else:
                await query.edit_message_text("📤 Iniciando envío masivo...", reply_markup=None)
        except Exception:
            pass  # Ignorar errores al editar

        db = get_database()  # Obtener todos los usuarios
        usuarios = list(db.usuarios.find({}, {"_id": 1}))

        total = len(usuarios)
        exitosos = 0
        bloqueados = 0
        no_encontrados = 0
        errores = 0

        status_msg = None  # Mensaje de estado en tiempo real
        try:
            status_msg = await context.bot.send_message(
                chat_id=update.effective_user.id,
                text="📊 Progreso: 0/{} (0%)".format(total),
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

        for i, usuario in enumerate(usuarios, 1):  # Enviar mensaje a cada usuario
            user_id = usuario['_id']

            exito, tipo_error = await NotifySystem.enviar_mensaje_usuario(
                context, user_id, texto, imagen, imagen_tipo, reply_markup
            )

            if exito:
                exitosos += 1
            elif tipo_error == "blocked":
                bloqueados += 1
            elif tipo_error == "not_found":
                no_encontrados += 1
            else:
                errores += 1

            if i % BATCH_SIZE == 0:  # Actualizar progreso cada lote
                await asyncio.sleep(1)  # Pausa entre lotes (evita rate limit)

                if status_msg and i % 100 == 0:  # Actualizar mensaje cada 100 usuarios
                    try:
                        porcentaje = (i / total) * 100
                        await status_msg.edit_text(
                            f"📊 Progreso: {i}/{total} ({porcentaje:.1f}%)\n"
                            f"✅ Exitosos: {exitosos}",
                            parse_mode=ParseMode.HTML
                        )
                    except Exception:
                        pass  # Ignorar errores al actualizar

            await asyncio.sleep(DELAY_ENTRE_ENVIOS)  # Pequeña pausa entre envíos

        if status_msg:  # Eliminar mensaje de progreso
            try:
                await status_msg.delete()
            except Exception:
                pass

        fallidos = bloqueados + no_encontrados + errores
        resultado = (  # Enviar resumen final
            f"✅ <b>Envío completado</b>\n\n"
            f"📊 <b>Estadísticas:</b>\n"
            f"• Total de usuarios: {total}\n"
            f"• Enviados correctamente: {exitosos}\n"
            f"• Fallidos: {fallidos}\n"
            f"  - Bloqueados: {bloqueados}\n"
            f"  - Chat no encontrado: {no_encontrados}\n"
            f"  - Otros errores: {errores}\n"
            f"• Tasa de éxito: {(exitosos / total * 100) if total > 0 else 0:.1f}%"
        )

        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text=resultado,
            parse_mode=ParseMode.HTML
        )

        context.user_data.clear()
        return ConversationHandler.END

    @staticmethod
    async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancela el proceso en cualquier momento"""
        if update.message:
            await update.message.reply_text("❌ Proceso de notificación cancelado.")
        context.user_data.clear()
        return ConversationHandler.END

    @staticmethod
    async def timeout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja el timeout de la conversación"""
        if update.message:
            await update.message.reply_text(
                "⏱️ Se agotó el tiempo de espera. Usa /notify para comenzar de nuevo."
            )
        context.user_data.clear()
        return ConversationHandler.END


def register_notify_handler(application):
    """Registra el handler de notificaciones masivas"""
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('notify', NotifySystem.comando_notify)],
        states={
            TEXTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, NotifySystem.recibir_texto)],
            IMAGEN: [
                MessageHandler(filters.PHOTO, NotifySystem.recibir_imagen),
                CommandHandler('saltar', NotifySystem.recibir_imagen),  # /saltar es comando, necesita su propio handler
                MessageHandler(filters.TEXT & ~filters.COMMAND, NotifySystem.recibir_imagen)
            ],
            BOTONES: [
                CommandHandler('saltar', NotifySystem.recibir_botones),  # /saltar es comando, necesita su propio handler
                MessageHandler(filters.TEXT & ~filters.COMMAND, NotifySystem.recibir_botones)
            ],
            CONFIRMAR: [CallbackQueryHandler(NotifySystem.confirmar_envio, pattern="^notify_")],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, NotifySystem.timeout_handler)]
        },
        fallbacks=[
            CommandHandler('cancelar', NotifySystem.cancelar),
        ],
        conversation_timeout=300  # Timeout de 5 minutos
    )

    application.add_handler(conv_handler)