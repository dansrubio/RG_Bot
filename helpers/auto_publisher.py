import logging
import asyncio
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, MessageEntity
from telegram.constants import ParseMode, ChatType
from telegram.ext import CommandHandler, ContextTypes, CallbackQueryHandler
from telegram.error import TelegramError

from config import is_admin, is_moderator, BOT_URL, CANAL_ELEMENTOS, ADMINISTRATION_GROUP
from database.crud.elemento_crud import ElementoCRUD
from helpers.temp_storage import guardar_temp_data, obtener_temp_data

logger = logging.getLogger(__name__)


def user_has_permissions(user_id: int) -> bool:
    """Verifica si el usuario tiene permisos"""
    return is_admin(user_id) or is_moderator(user_id)


def is_authorized_chat(chat) -> bool:
    """Verifica si el chat está autorizado"""
    return (
            chat.type == ChatType.PRIVATE or
            (ADMINISTRATION_GROUP and chat.id == ADMINISTRATION_GROUP)
    )


def obtener_elemento_id(elemento_data: dict) -> int:
    """Obtiene el ID del elemento de forma segura (MongoDB usa _id)"""
    return elemento_data.get('_id') or elemento_data.get('id', 0)


def extraer_primer_linea(texto: str) -> str:
    """Extrae primera línea sin cortar palabras (max 35 caracteres) con emojis"""
    if not texto:
        return "🔵 Acceder al Juego 🔵"
    linea = texto.strip().split("\n")[0]
    if not linea:
        return "🔵 Acceder al Juego 🔵"

    palabras = linea.strip().split()
    if not palabras:
        return "🔵 Acceder al Juego 🔵"

    resultado = palabras[0]
    i = 1
    while i < len(palabras):
        temp = resultado + " " + palabras[i]
        if len(resultado) <= 35 < len(temp):
            break
        resultado = temp
        i += 1

    if i < len(palabras):
        return f"🔵 {resultado} (...) 🔵"
    else:
        return f"🔵 {resultado} 🔵"


def extraer_urls_especiales(texto: str) -> dict:
    """
    Extrae URLs de Trailer y Steam del texto
    Busca patrones como:
    - 🎬 Trailer: [URL]
    - 🎰 Ver en Steam: [URL]
    Retorna: {'trailer': 'url', 'steam': 'url'}
    """
    urls = {'trailer': None, 'steam': None}

    if not texto:
        return urls

    # Buscar patrón: 🎬 Trailer: [URL]
    match_trailer = re.search(r'🎬\s*Trailer:\s*(https?://[^\s\n]+)', texto, re.IGNORECASE)
    if match_trailer:
        urls['trailer'] = match_trailer.group(1).strip()

    # Buscar patrón: 🎰 Ver en Steam: [URL]
    match_steam = re.search(r'🎰\s*Ver en Steam:\s*(https?://[^\s\n]+)', texto, re.IGNORECASE)
    if match_steam:
        urls['steam'] = match_steam.group(1).strip()

    return urls


def _clonar_entidad(entidad: MessageEntity, nuevo_offset: int) -> MessageEntity:
    """
    Reconstruye una MessageEntity con offset ajustado usando el constructor directo.
    Evita de_json(None) que falla silenciosamente con blockquote y expandable_blockquote.
    """
    return MessageEntity(
        type=entidad.type,
        offset=nuevo_offset,
        length=entidad.length,
        url=getattr(entidad, 'url', None),
        user=getattr(entidad, 'user', None),
        language=getattr(entidad, 'language', None),
        custom_emoji_id=getattr(entidad, 'custom_emoji_id', None),
    )


def hay_urls_a_limpiar(texto: str) -> bool:
    """Indica si el texto contiene líneas de Trailer o Steam que deben eliminarse"""
    if not texto:
        return False
    patron = r'(?:🎬\s*Trailer:|🎰\s*Ver en Steam:)\s*https?://'
    return bool(re.search(patron, texto, flags=re.IGNORECASE))


def limpiar_texto_y_entidades(texto: str, entidades: list) -> tuple[str, list]:
    """
    Elimina líneas de Trailer/Steam del texto y recalcula los offsets de todas
    las entidades, incluyendo blockquote y expandable_blockquote.
    Retorna (texto_limpio, entidades_ajustadas).
    """
    if not texto:
        return texto, entidades or []

    patron = r'\n?[^\n]*(?:🎬\s*Trailer:|🎰\s*Ver en Steam:)\s*https?://[^\n]*'

    eliminados = [(m.start(), m.end()) for m in re.finditer(patron, texto, flags=re.IGNORECASE)]

    if not eliminados:
        return texto, entidades or []

    texto_limpio = re.sub(patron, '', texto, flags=re.IGNORECASE).rstrip()

    if not entidades:
        return texto_limpio, []

    entidades_ajustadas = []
    for entidad in entidades:
        offset = entidad.offset

        dentro_eliminado = any(ini <= offset < fin for ini, fin in eliminados)  # entidad dentro de zona borrada
        if dentro_eliminado:
            continue

        chars_antes = sum(fin - ini for ini, fin in eliminados if fin <= offset)  # desplazamiento acumulado
        nuevo_offset = offset - chars_antes

        try:
            entidades_ajustadas.append(_clonar_entidad(entidad, nuevo_offset))
        except Exception as e:
            logger.warning(f"Entidad tipo '{entidad.type}' descartada al clonar: {e}")

    return texto_limpio, entidades_ajustadas


def construir_teclado_botones(enlace_elemento: str, texto_boton_acceso: str,
                              urls_especiales: dict) -> InlineKeyboardMarkup:
    """
    Construye el teclado de botones con layout:
    Fila 1: [🔵 Acceder al Juego 🔵]
    Fila 2: [🎬 Trailer] [🎰 Ver en Steam] (solo si existen)
    """
    botones = []

    # Fila 1: Botón de acceso al juego (siempre)
    botones.append([InlineKeyboardButton(texto_boton_acceso, url=enlace_elemento)])

    # Fila 2: Botones opcionales (Trailer y Steam en la misma línea)
    fila_especial = []

    if urls_especiales.get('trailer'):
        fila_especial.append(InlineKeyboardButton("🎬 Trailer", url=urls_especiales['trailer']))

    if urls_especiales.get('steam'):
        fila_especial.append(InlineKeyboardButton("🎰 Ver en Steam", url=urls_especiales['steam']))

    if fila_especial:
        botones.append(fila_especial)

    return InlineKeyboardMarkup(botones)


async def publicar_comando(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /publicar - Publica un elemento en el canal"""
    user = update.effective_user
    message = update.effective_message
    chat = update.effective_chat

    try:
        if not is_authorized_chat(chat):
            await message.reply_text(
                "❌ **Chat no autorizado**\n\n"
                "Este comando solo funciona en:\n"
                "• 💬 Chat privado conmigo\n"
                f"• 🏢 Grupo de administración (`{ADMINISTRATION_GROUP}`)",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        if not user_has_permissions(user.id):
            await message.reply_text(
                "❌ **Sin permisos**\n\n"
                f"Se requiere ser administrador o moderador.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        if not CANAL_ELEMENTOS:
            await message.reply_text(
                "❌ **Canal no configurado**\n\n"
                "La variable `CANAL_ELEMENTOS` no está definida en .env"
            )
            return

        if len(context.args) != 1:
            await message.reply_text(
                "❌ **Uso incorrecto**\n\n"
                "✅ **Formato:** `/publicar <elemento_id>`\n\n"
                "📌 **Ejemplo:** `/publicar 5`",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        try:
            elemento_id = int(context.args[0])
        except ValueError:
            await message.reply_text("❌ El ID debe ser un número entero.")
            return

        elemento_data = ElementoCRUD.obtener_elemento_por_id(elemento_id)
        if not elemento_data:
            await message.reply_text(f"❌ No se encontró elemento con ID `{elemento_id}`.")
            return

        id_inicio = elemento_data['id_inicio']
        token = elemento_data['token']
        enlace_elemento = f"{BOT_URL}?start={token}"
        rango_mensajes = elemento_data['id_final'] - elemento_data['id_inicio'] + 1

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Confirmar", callback_data=f"pub_confirm_{elemento_id}"),
                InlineKeyboardButton("❌ Cancelar", callback_data=f"pub_cancel_{elemento_id}")
            ]
        ])

        await message.reply_text(
            f"📢 **Confirmar publicación**\n\n"
            f"🏷️ **Nombre:** `{elemento_data['nombre']}`\n"
            f"🆔 **ID:** `{elemento_id}`\n"
            f"📊 **Mensajes:** `{rango_mensajes}`\n"
            f"📍 **Mensaje origen:** `{id_inicio}`\n"
            f"🔗 **Enlace:** `{enlace_elemento[:50]}...`\n\n"
            f"📺 **Canal destino:** `{CANAL_ELEMENTOS}`\n\n"
            f"⚠️ Se copiará el mensaje {id_inicio} exactamente (formato y contenido) y se agregarán:\n"
            f"• Botón con la primera línea del mensaje (sin cortar palabras, máx 35 caracteres)\n"
            f"• Botón 🎬 Trailer (si está disponible)\n"
            f"• Botón 🎰 Ver en Steam (si está disponible)\n\n"
            f"¿Deseas continuar?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Error en publicar_comando: {e}", exc_info=True)
        await message.reply_text(
            f"❌ **Error interno**\n\n"
            f"Error: `{str(e)[:100]}`",
            parse_mode=ParseMode.MARKDOWN
        )


async def publicar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los callbacks de confirmación de publicación"""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    data = query.data

    try:
        if not user_has_permissions(user.id):
            await query.edit_message_text("❌ Sin permisos.")
            return

        if data.startswith("pub_cancel_") and not data.startswith("pub_all_cancel"):
            await query.edit_message_text("❌ Publicación cancelada.")
            return

        if data.startswith("pub_all_cancel"):
            await query.edit_message_text("❌ Publicación múltiple cancelada.")
            return

        if data.startswith("pub_all_confirm_"):  # Confirmar publicación múltiple
            temp_key = data.replace("pub_all_confirm_", "")
            elemento_ids = obtener_temp_data(temp_key)

            if not elemento_ids:
                await query.edit_message_text("❌ Datos expirados. Genera los elementos nuevamente.")
                return

            await query.edit_message_text(
                f"⏳ **Publicando {len(elemento_ids)} elementos...**\n\n"
                f"📤 Iniciando proceso...",
                parse_mode=ParseMode.MARKDOWN
            )

            exitosos = 0
            errores = 0

            for idx, elemento_id in enumerate(elemento_ids, 1):
                try:
                    elemento_data = ElementoCRUD.obtener_elemento_por_id(elemento_id)
                    if not elemento_data:
                        errores += 1
                        continue

                    id_inicio = elemento_data['id_inicio']
                    token = elemento_data['token']
                    enlace_elemento = f"{BOT_URL}?start={token}"

                    mensaje_origen = await context.bot.forward_message(
                        chat_id=query.message.chat_id,
                        from_chat_id=ADMINISTRATION_GROUP,
                        message_id=id_inicio
                    )

                    # Extraer texto/caption y URLs especiales
                    tiene_caption = mensaje_origen.caption is not None
                    texto_mensaje = mensaje_origen.caption or mensaje_origen.text or ""
                    boton_texto = extraer_primer_linea(texto_mensaje)
                    urls_especiales = extraer_urls_especiales(texto_mensaje)
                    necesita_limpieza = hay_urls_a_limpiar(texto_mensaje)  # solo modificar caption si hay URLs a borrar

                    # Construir teclado con todos los botones disponibles
                    keyboard = construir_teclado_botones(enlace_elemento, boton_texto, urls_especiales)

                    await context.bot.delete_message(
                        chat_id=query.message.chat_id,
                        message_id=mensaje_origen.message_id
                    )

                    copy_kwargs = {
                        'chat_id': CANAL_ELEMENTOS,
                        'from_chat_id': ADMINISTRATION_GROUP,
                        'message_id': id_inicio,
                        'reply_markup': keyboard,
                    }
                    if tiene_caption and necesita_limpieza:  # solo sobreescribir si hay URLs que eliminar
                        entidades_originales = mensaje_origen.caption_entities or []
                        caption_limpio, entidades_limpias = limpiar_texto_y_entidades(texto_mensaje, entidades_originales)
                        copy_kwargs['caption'] = caption_limpio
                        copy_kwargs['caption_entities'] = entidades_limpias or None

                    await context.bot.copy_message(**copy_kwargs)

                    exitosos += 1

                    await query.edit_message_text(
                        f"⏳ **Publicando {len(elemento_ids)} elementos...**\n\n"
                        f"📊 Progreso: {idx}/{len(elemento_ids)}\n"
                        f"✅ Exitosos: {exitosos}\n"
                        f"❌ Errores: {errores}",
                        parse_mode=ParseMode.MARKDOWN
                    )

                    if idx < len(elemento_ids):
                        await asyncio.sleep(5)

                except Exception as e:
                    logger.error(f"Error publicando elemento {elemento_id}: {e}")
                    errores += 1

            await query.edit_message_text(
                f"✅ **Publicación múltiple completada**\n\n"
                f"📊 **Total procesados:** `{len(elemento_ids)}`\n"
                f"✅ **Exitosos:** `{exitosos}`\n"
                f"❌ **Errores:** `{errores}`\n"
                f"📺 **Canal:** `{CANAL_ELEMENTOS}`\n"
                f"👤 **Publicado por:** {user.first_name}",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        if data.startswith("pub_all_"):  # Mostrar confirmación de publicación múltiple
            temp_key = data.replace("pub_all_", "")
            elemento_ids = obtener_temp_data(temp_key, eliminar=False)

            if not elemento_ids:
                await query.edit_message_text("❌ Datos expirados. Genera los elementos nuevamente.")
                return

            if not CANAL_ELEMENTOS:
                await query.edit_message_text("❌ Canal no configurado.")
                return

            new_temp_key = guardar_temp_data(elemento_ids)

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Confirmar", callback_data=f"pub_all_confirm_{new_temp_key}"),
                    InlineKeyboardButton("❌ Cancelar", callback_data=f"pub_all_cancel")
                ]
            ])

            await query.edit_message_text(
                f"📢 **Confirmar publicación múltiple**\n\n"
                f"📊 **Total elementos:** `{len(elemento_ids)}`\n"
                f"📺 **Canal destino:** `{CANAL_ELEMENTOS}`\n\n"
                f"⚠️ Se publicarán todos los elementos en orden.\n"
                f"Cada publicación tendrá 5 segundos de pausa.\n"
                f"Se agregarán botones dinámicos según las URLs disponibles:\n"
                f"• 🎬 Trailer (si existe)\n"
                f"• 🎰 Ver en Steam (si existe)\n\n"
                f"¿Deseas continuar?",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
            return

        if data.startswith("detail_all_"):  # Mostrar detalles de elementos múltiples
            temp_key = data.replace("detail_all_", "")
            elemento_ids = obtener_temp_data(temp_key, eliminar=False)

            if not elemento_ids:
                await query.edit_message_text("❌ Datos expirados. Genera los elementos nuevamente.")
                return

            MAX_POR_MENSAJE = 10
            total_elementos = len(elemento_ids)

            new_temp_key = guardar_temp_data(elemento_ids)

            if total_elementos <= MAX_POR_MENSAJE:
                texto_detalle = f"📋 **Detalles de {total_elementos} elementos**\n\n"

                for idx, elemento_id in enumerate(elemento_ids, 1):
                    elemento_data = ElementoCRUD.obtener_elemento_por_id(elemento_id)
                    if elemento_data:
                        token = elemento_data['token']
                        token_display = f"{token[:6]}...{token[-4:]}"
                        rango = elemento_data['id_final'] - elemento_data['id_inicio'] + 1
                        elem_id = obtener_elemento_id(elemento_data)
                        texto_detalle += (
                            f"**{idx}. {elemento_data['nombre']}**\n"
                            f"🆔 `{elem_id}` | 📊 {rango} msgs | 🔑 `{token_display}`\n\n"
                        )

                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 Publicar todos", callback_data=f"pub_all_{new_temp_key}")]
                ])

                await query.edit_message_text(
                    texto_detalle,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=keyboard
                )
            else:
                texto_detalle = f"📋 **{total_elementos} elementos creados**\n\n"

                for idx, elemento_id in enumerate(elemento_ids[:5], 1):
                    elemento_data = ElementoCRUD.obtener_elemento_por_id(elemento_id)
                    if elemento_data:
                        rango = elemento_data['id_final'] - elemento_data['id_inicio'] + 1
                        texto_detalle += f"{idx}. `{elemento_data['nombre']}` ({rango} msgs)\n"

                if total_elementos > 5:
                    texto_detalle += f"\n_...y {total_elementos - 5} más_\n"

                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 Publicar todos", callback_data=f"pub_all_{new_temp_key}")]
                ])

                await query.edit_message_text(
                    texto_detalle,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=keyboard
                )
            return

        if data.startswith("pub_confirm_"):  # Publicar elemento individual
            elemento_id = int(data.split("_")[-1])

            elemento_data = ElementoCRUD.obtener_elemento_por_id(elemento_id)
            if not elemento_data:
                await query.edit_message_text("❌ Elemento no encontrado.")
                return

            if not CANAL_ELEMENTOS:
                await query.edit_message_text("❌ Canal no configurado.")
                return

            id_inicio = elemento_data['id_inicio']
            token = elemento_data['token']
            enlace_elemento = f"{BOT_URL}?start={token}"

            await query.edit_message_text(
                f"⏳ **Procesando publicación...**\n\n"
                f"📥 Copiando mensaje `{id_inicio}`...",
                parse_mode=ParseMode.MARKDOWN
            )

            try:
                mensaje_origen = await context.bot.forward_message(
                    chat_id=query.message.chat_id,
                    from_chat_id=ADMINISTRATION_GROUP,
                    message_id=id_inicio
                )

                # Extraer texto/caption y URLs especiales
                tiene_caption = mensaje_origen.caption is not None
                texto_mensaje = mensaje_origen.caption or mensaje_origen.text or ""
                boton_texto = extraer_primer_linea(texto_mensaje)
                urls_especiales = extraer_urls_especiales(texto_mensaje)
                necesita_limpieza = hay_urls_a_limpiar(texto_mensaje)  # solo modificar caption si hay URLs a borrar

                keyboard = construir_teclado_botones(enlace_elemento, boton_texto, urls_especiales)

                await context.bot.delete_message(
                    chat_id=query.message.chat_id,
                    message_id=mensaje_origen.message_id
                )

                await query.edit_message_text(
                    f"⏳ **Publicando en canal...**\n\n"
                    f"📤 Enviando a `{CANAL_ELEMENTOS}`...",
                    parse_mode=ParseMode.MARKDOWN
                )

                copy_kwargs = {
                    'chat_id': CANAL_ELEMENTOS,
                    'from_chat_id': ADMINISTRATION_GROUP,
                    'message_id': id_inicio,
                    'reply_markup': keyboard,
                }
                if tiene_caption and necesita_limpieza:  # solo sobreescribir si hay URLs que eliminar
                    entidades_originales = mensaje_origen.caption_entities or []
                    caption_limpio, entidades_limpias = limpiar_texto_y_entidades(texto_mensaje, entidades_originales)
                    copy_kwargs['caption'] = caption_limpio
                    copy_kwargs['caption_entities'] = entidades_limpias or None

                await context.bot.copy_message(**copy_kwargs)

                await query.edit_message_text(
                    f"✅ **Publicación exitosa**\n\n"
                    f"🏷️ **Nombre:** `{elemento_data['nombre']}`\n"
                    f"🆔 **ID:** `{elemento_id}`\n"
                    f"📍 **Mensaje origen:** `{id_inicio}`\n"
                    f"📺 **Canal:** `{CANAL_ELEMENTOS}`\n"
                    f"📘 **Botón principal:** `{boton_texto}`\n"
                    f"🎬 **Trailer:** {'✅ Incluido' if urls_especiales.get('trailer') else '❌ No disponible'}\n"
                    f"🎰 **Steam:** {'✅ Incluido' if urls_especiales.get('steam') else '❌ No disponible'}\n"
                    f"👤 **Publicado por:** {user.first_name}\n\n"
                    f"🔗 Enlace de acceso incluido en la publicación",
                    parse_mode=ParseMode.MARKDOWN
                )

            except TelegramError as e:
                error_msg = str(e)
                await query.edit_message_text(
                    f"❌ **Error de Telegram**\n\n"
                    f"No se pudo publicar el mensaje.\n\n"
                    f"**Posibles causas:**\n"
                    f"• El bot no es administrador del canal\n"
                    f"• El mensaje {id_inicio} no existe en el grupo admin\n"
                    f"• El canal ID es incorrecto\n\n"
                    f"**Error técnico:** `{error_msg[:100]}`",
                    parse_mode=ParseMode.MARKDOWN
                )
                logger.error(f"Error de Telegram publicando elemento {elemento_id}: {e}")

    except Exception as e:
        logger.error(f"Error en publicar_callback: {e}", exc_info=True)
        try:
            await query.edit_message_text(
                f"❌ **Error interno**\n\n"
                f"Error: `{str(e)[:100]}`",
                parse_mode=ParseMode.MARKDOWN
            )
        except:
            pass


def register_auto_publisher(application):
    """Registra el sistema de publicación automática"""
    try:
        application.add_handler(CommandHandler("publicar", publicar_comando))

        application.add_handler(CallbackQueryHandler(
            publicar_callback,
            pattern="^(pub_|detail_all_)"
        ))

    except Exception as e:
        logger.error(f"Error registrando sistema de publicación: {e}", exc_info=True)