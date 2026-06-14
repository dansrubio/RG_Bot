"""
Sistema de notificaciones privadas para usuarios sancionados
Incluye notificaciones para mutes y baneos
Contacto directo con el administrador principal: @daniel_srub (ID: 7611870072)
"""

import logging
from typing import Optional
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError, Forbidden, BadRequest
from config import BOT_REGLAMENTO_URL

# Datos del administrador principal de contacto
ADMIN_CONTACT_ID = 7611870072
ADMIN_CONTACT_USERNAME = "daniel_srub"

class NotificationService:
    """Servicio para enviar notificaciones privadas a usuarios"""

    # === NOTIFICACIONES DE MUTE ===

    @staticmethod
    async def enviar_notificacion_mute(
        bot: Bot,
        user_id: int,
        username: str = None,
        razon: str = None,
        duracion_texto: str = None,
        admin_username: str = None
    ) -> bool:
        """
        Envía notificación privada al usuario muteado

        Args:
            bot: Instancia del bot de Telegram
            user_id: ID del usuario a notificar
            username: Username del usuario (opcional)
            razon: Razón del mute (opcional)
            duracion_texto: Texto de la duración (opcional)
            admin_username: Username del admin (opcional)

        Returns:
            bool: True si se envió correctamente
        """
        try:
            # Construir mensaje personalizado
            mensaje = NotificationService._construir_mensaje_mute(
                username=username,
                razon=razon,
                duracion_texto=duracion_texto,
                admin_username=admin_username
            )

            # Construir teclado con botones
            teclado = NotificationService._construir_teclado_mute(user_id)

            # Enviar mensaje privado
            await bot.send_message(
                chat_id=user_id,
                text=mensaje,
                reply_markup=teclado,
                parse_mode='HTML',
                disable_web_page_preview=True
            )

            logging.info(f"✅ Notificación de mute enviada a usuario {user_id}")
            return True

        except Forbidden:
            logging.warning(f"⚠️ Usuario {user_id} no ha iniciado chat con el bot")
            return False

        except BadRequest as e:
            logging.warning(f"⚠️ Error enviando notificación a {user_id}: {e}")
            return False

        except TelegramError as e:
            logging.error(f"⛔ Error de Telegram enviando notificación: {e}")
            return False

        except Exception as e:
            logging.error(f"⛔ Error enviando notificación: {e}")
            return False

    @staticmethod
    def _construir_mensaje_mute(
        username: str = None,
        razon: str = None,
        duracion_texto: str = None,
        admin_username: str = None
    ) -> str:
        """
        Construye el mensaje de notificación de mute

        Returns:
            str: Mensaje formateado en HTML
        """
        # Encabezado
        mensaje = "🔇 <b>NOTIFICACIÓN DE SANCIÓN</b>\n\n"

        # Información básica
        if username:
            mensaje += f"<b>Usuario:</b> @{username}\n"

        mensaje += "<b>Sanción:</b> Silencio temporal\n"

        # Duración
        if duracion_texto:
            mensaje += f"<b>Duración:</b> {duracion_texto}\n"
        else:
            mensaje += "<b>Duración:</b> Indefinida\n"

        # Razón
        if razon:
            mensaje += f"<b>Motivo:</b> {razon}\n"

        # Admin que aplicó la sanción
        if admin_username:
            mensaje += f"<b>Aplicado por:</b> @{admin_username}\n"

        mensaje += "\n"

        # Mensaje principal
        mensaje += (
            "Has sido <b>silenciado temporalmente</b> en nuestra comunidad "
            "por incumplir el reglamento oficial.\n\n"
            "Durante este período no podrás enviar mensajes en los grupos de la comunidad.\n\n"
        )

        # Información de apelación
        mensaje += (
            "📞 <b>¿Deseas apelar esta sanción?</b>\n"
            f"Puedes comunicarte directamente con <a href='tg://user?id={ADMIN_CONTACT_ID}'>@{ADMIN_CONTACT_USERNAME}</a> "
            "para solicitar una revisión de tu caso.\n\n"
        )

        # Información adicional
        mensaje += (
            "⚠️ <b>Importante:</b>\n"
            "• Esta sanción se aplica automáticamente a todos los grupos de la comunidad\n"
            "• El reglamento está disponible en el botón de abajo\n"
            "• Las sanciones son revisadas periódicamente\n"
        )

        # Contacto directo
        mensaje += (
            "\n<b>Contacto directo del administrador principal:</b>\n"
            f"• Usuario: @{ADMIN_CONTACT_USERNAME}\n"
            f"• ID: {ADMIN_CONTACT_ID}\n"
        )

        return mensaje

    @staticmethod
    def _construir_teclado_mute(user_id: int) -> InlineKeyboardMarkup:
        """
        Construye el teclado inline para la notificación de mute

        Returns:
            InlineKeyboardMarkup: Teclado con botones
        """
        botones = []

        # Botón del reglamento (si está configurado)
        if BOT_REGLAMENTO_URL:
            botones.append([
                InlineKeyboardButton(
                    "📜 Ver Reglamento",
                    url=BOT_REGLAMENTO_URL
                )
            ])

        # Botón de contacto con admin principal
        botones.append([
            InlineKeyboardButton(
                "📞 Contactar Admin",
                url=f"https://t.me/{ADMIN_CONTACT_USERNAME}"
            )
        ])

        # Botón de información del usuario
        botones.append([
            InlineKeyboardButton(
                "ℹ️ Tu Perfil",
                url=f"tg://user?id={user_id}"
            )
        ])

        return InlineKeyboardMarkup(botones)

    # === NOTIFICACIONES DE BAN ===

    @staticmethod
    async def enviar_notificacion_ban(
        bot: Bot,
        user_id: int,
        username: str = None,
        razon: str = None,
        admin_username: str = None
    ) -> bool:
        """
        Envía notificación privada al usuario baneado

        Args:
            bot: Instancia del bot de Telegram
            user_id: ID del usuario a notificar
            username: Username del usuario (opcional)
            razon: Razón del ban (opcional)
            admin_username: Username del admin (opcional)

        Returns:
            bool: True si se envió correctamente
        """
        try:
            # Construir mensaje personalizado
            mensaje = NotificationService._construir_mensaje_ban(
                username=username,
                razon=razon,
                admin_username=admin_username
            )

            # Construir teclado con botones
            teclado = NotificationService._construir_teclado_ban(user_id)

            # Enviar mensaje privado
            await bot.send_message(
                chat_id=user_id,
                text=mensaje,
                reply_markup=teclado,
                parse_mode='HTML',
                disable_web_page_preview=True
            )

            logging.info(f"✅ Notificación de ban enviada a usuario {user_id}")
            return True

        except Forbidden:
            logging.warning(f"⚠️ Usuario {user_id} no ha iniciado chat con el bot")
            return False

        except BadRequest as e:
            logging.warning(f"⚠️ Error enviando notificación a {user_id}: {e}")
            return False

        except TelegramError as e:
            logging.error(f"⛔ Error de Telegram enviando notificación: {e}")
            return False

        except Exception as e:
            logging.error(f"⛔ Error enviando notificación: {e}")
            return False

    @staticmethod
    def _construir_mensaje_ban(
        username: str = None,
        razon: str = None,
        admin_username: str = None
    ) -> str:
        """
        Construye el mensaje de notificación de ban

        Returns:
            str: Mensaje formateado en HTML
        """
        # Encabezado
        mensaje = "🚫 <b>NOTIFICACIÓN DE BANEO PERMANENTE</b>\n\n"

        # Información básica
        if username:
            mensaje += f"<b>Usuario:</b> @{username}\n"

        mensaje += "<b>Sanción:</b> Baneo permanente\n"
        mensaje += "<b>Duración:</b> Permanente\n"

        # Razón
        if razon:
            mensaje += f"<b>Motivo:</b> {razon}\n"

        # Admin que aplicó la sanción
        if admin_username:
            mensaje += f"<b>Aplicado por:</b> @{admin_username}\n"

        mensaje += "\n"

        # Mensaje principal
        mensaje += (
            "Has sido <b>baneado permanentemente</b> de nuestra comunidad "
            "por incumplir gravemente el reglamento oficial.\n\n"
            "Esta sanción te impide participar en todos los grupos de la comunidad "
            "y es de carácter permanente.\n\n"
        )

        # Información de apelación
        mensaje += (
            "📞 <b>¿Deseas apelar esta sanción?</b>\n"
            f"Si consideras que esta sanción fue injusta, puedes comunicarte directamente "
            f"con <a href='tg://user?id={ADMIN_CONTACT_ID}'>@{ADMIN_CONTACT_USERNAME}</a> "
            "para solicitar una revisión de tu caso.\n\n"
        )

        # Información adicional
        mensaje += (
            "⚠️ <b>Información importante:</b>\n"
            "• Esta sanción se aplica a todos los grupos de la comunidad\n"
            "• El baneo es permanente hasta nueva decisión administrativa\n"
            "• Puedes revisar el reglamento oficial usando el botón de abajo\n"
            "• Los baneos solo pueden ser removidos por un administrador\n"
        )

        # Contacto directo
        mensaje += (
            "\n<b>Contacto directo del administrador principal:</b>\n"
            f"• Usuario: @{ADMIN_CONTACT_USERNAME}\n"
            f"• ID: {ADMIN_CONTACT_ID}\n"
        )

        return mensaje

    @staticmethod
    def _construir_teclado_ban(user_id: int) -> InlineKeyboardMarkup:
        """
        Construye el teclado inline para la notificación de ban

        Returns:
            InlineKeyboardMarkup: Teclado con botones
        """
        botones = []

        # Botón del reglamento (si está configurado)
        if BOT_REGLAMENTO_URL:
            botones.append([
                InlineKeyboardButton(
                    "📜 Ver Reglamento",
                    url=BOT_REGLAMENTO_URL
                )
            ])

        # Botón de contacto con admin principal
        botones.append([
            InlineKeyboardButton(
                "📞 Contactar Admin",
                url=f"https://t.me/{ADMIN_CONTACT_USERNAME}"
            )
        ])

        # Botón de información del usuario
        botones.append([
            InlineKeyboardButton(
                "ℹ️ Tu Perfil",
                url=f"tg://user?id={user_id}"
            )
        ])

        return InlineKeyboardMarkup(botones)

    # === CONFIRMACIONES PARA ADMINISTRADORES ===

    @staticmethod
    async def enviar_confirmacion_admin(
        bot: Bot,
        admin_chat_id: int,
        user_id: int,
        username: str = None,
        duracion_texto: str = None,
        razon: str = None,
        grupos_aplicados: int = 0,
        notificacion_enviada: bool = False
    ) -> bool:
        """
        Envía confirmación al administrador sobre el mute aplicado

        Args:
            bot: Instancia del bot
            admin_chat_id: Chat donde enviar la confirmación
            user_id: ID del usuario muteado
            username: Username del usuario
            duracion_texto: Duración del mute
            razon: Razón del mute
            grupos_aplicados: Número de grupos donde se aplicó
            notificacion_enviada: Si se envió notificación privada

        Returns:
            bool: True si se envió correctamente
        """
        try:
            # Construir mensaje de confirmación
            mensaje = "✅ <b>MUTE APLICADO CORRECTAMENTE</b>\n\n"

            # Información del usuario
            if username:
                mensaje += f"<b>Usuario:</b> @{username} (<code>{user_id}</code>)\n"
            else:
                mensaje += f"<b>Usuario ID:</b> <code>{user_id}</code>\n"

            # Duración
            if duracion_texto:
                mensaje += f"<b>Duración:</b> {duracion_texto}\n"
            else:
                mensaje += "<b>Duración:</b> Indefinida (máximo permitido por Telegram)\n"

            # Razón
            if razon:
                mensaje += f"<b>Motivo:</b> {razon}\n"

            mensaje += f"<b>Grupos afectados:</b> {grupos_aplicados}\n"

            # Estado de notificación
            if notificacion_enviada:
                mensaje += "✅ <b>Notificación privada:</b> Enviada correctamente\n"
            else:
                mensaje += "⚠️ <b>Notificación privada:</b> No se pudo enviar (usuario no ha iniciado chat)\n"

            # Contacto directo del admin principal
            mensaje += (
                "\n<b>Contacto directo del administrador principal:</b>\n"
                f"• Usuario: @{ADMIN_CONTACT_USERNAME}\n"
                f"• ID: {ADMIN_CONTACT_ID}\n"
            )

            # Enviar confirmación
            await bot.send_message(
                chat_id=admin_chat_id,
                text=mensaje,
                parse_mode='HTML'
            )

            return True

        except Exception as e:
            logging.error(f"⛔ Error enviando confirmación a admin: {e}")
            return False

    @staticmethod
    async def enviar_confirmacion_admin_ban(
        bot: Bot,
        admin_chat_id: int,
        user_id: int,
        username: str = None,
        razon: str = None,
        grupos_aplicados: int = 0,
        notificacion_enviada: bool = False
    ) -> bool:
        """
        Envía confirmación al administrador sobre el ban aplicado

        Args:
            bot: Instancia del bot
            admin_chat_id: Chat donde enviar la confirmación
            user_id: ID del usuario baneado
            username: Username del usuario
            razon: Razón del ban
            grupos_aplicados: Número de grupos donde se aplicó
            notificacion_enviada: Si se envió notificación privada

        Returns:
            bool: True si se envió correctamente
        """
        try:
            # Construir mensaje de confirmación
            mensaje = "✅ <b>BAN APLICADO CORRECTAMENTE</b>\n\n"

            # Información del usuario
            if username:
                mensaje += f"<b>Usuario:</b> @{username} (<code>{user_id}</code>)\n"
            else:
                mensaje += f"<b>Usuario ID:</b> <code>{user_id}</code>\n"

            mensaje += "<b>Duración:</b> Permanente\n"

            # Razón
            if razon:
                mensaje += f"<b>Motivo:</b> {razon}\n"

            mensaje += f"<b>Grupos afectados:</b> {grupos_aplicados}\n"

            # Estado de notificación
            if notificacion_enviada:
                mensaje += "✅ <b>Notificación privada:</b> Enviada correctamente\n"
            else:
                mensaje += "⚠️ <b>Notificación privada:</b> No se pudo enviar (usuario no ha iniciado chat)\n"

            # Estado del usuario actualizado
            mensaje += "✅ <b>Estado en BD:</b> Actualizado a BAN_USER\n"

            # Contacto directo del admin principal
            mensaje += (
                "\n<b>Contacto directo del administrador principal:</b>\n"
                f"• Usuario: @{ADMIN_CONTACT_USERNAME}\n"
                f"• ID: {ADMIN_CONTACT_ID}\n"
            )

            # Enviar confirmación
            await bot.send_message(
                chat_id=admin_chat_id,
                text=mensaje,
                parse_mode='HTML'
            )

            return True

        except Exception as e:
            logging.error(f"⛔ Error enviando confirmación a admin: {e}")
            return False