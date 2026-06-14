"""
Handler de publicación post-indexado — Bot principal
"""

import asyncio
import logging
import re
from html import escape

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CallbackQueryHandler
from telegram.error import TelegramError

from config import is_admin, is_moderator, BOT_URL, CANAL_ELEMENTOS, ADMINISTRATION_GROUP, ALMACENES_MAP
from database.base import get_database
from database.crud.elemento_crud import ElementoCRUD
from helpers.auto_publisher import (
    extraer_primer_linea,
    extraer_urls_especiales,
    hay_urls_a_limpiar,
    limpiar_texto_y_entidades,
    construir_teclado_botones,
)

logger = logging.getLogger(__name__)


def es_staff(user_id: int) -> bool:
    """Verifica si el usuario es admin o moderador"""
    return is_admin(user_id) or is_moderator(user_id)


def obtener_tarea(task_id: str) -> dict | None:
    """Obtiene una tarea pendiente de MongoDB"""
    try:
        return get_database().publicacion_pendiente.find_one(
            {"_id": task_id, "estado": "pendiente"}
        )
    except Exception as e:
        logger.error(f"Error obteniendo tarea {task_id}: {e}")
        return None


def marcar_tarea(task_id: str, estado: str) -> None:
    """Actualiza el estado de una tarea en MongoDB"""
    try:
        get_database().publicacion_pendiente.update_one(
            {"_id": task_id},
            {"$set": {"estado": estado}}
        )
    except Exception as e:
        logger.error(f"Error actualización tarea {task_id}: {e}")


def formatear_peso(bytes_total: int) -> str:
    """
    Convierte bytes a la unidad más legible.
    Ejemplos: 734 MB | 2.15 GB | 450 KB
    """
    if bytes_total <= 0:
        return ""
    if bytes_total >= 1_073_741_824:
        valor = bytes_total / 1_073_741_824
        return f"{valor:.2f} GB".rstrip("0").rstrip(".")
    if bytes_total >= 1_048_576:
        valor = bytes_total / 1_048_576
        return f"{valor:.1f} MB" if valor % 1 else f"{int(valor)} MB"
    return f"{bytes_total / 1024:.0f} KB"


def entidades_a_html(texto: str, entidades: list) -> str:
    """
    Convierte un texto plano + lista de MessageEntity de Telegram a HTML.
    Soporta: bold, italic, underline, strikethrough, code, pre, spoiler,
    text_link, text_mention.
    Los caracteres especiales HTML del texto se escapan correctamente.
    """
    if not entidades or not texto:
        return escape(texto)

    # Ordenar por offset ascendente para procesar de izquierda a derecha
    entidades_ord = sorted(entidades, key=lambda e: e.offset)

    # Construir lista de eventos (apertura/cierre) por posición en bytes UTF-16
    texto_utf16  = texto.encode("utf-16-le")
    chars_utf16  = [texto_utf16[i:i+2] for i in range(0, len(texto_utf16), 2)]

    # Mapear posición UTF-16 → posición en la cadena Python
    pos_utf16_a_py = {}
    py_idx = 0
    utf16_idx = 0
    for ch in texto:
        pos_utf16_a_py[utf16_idx] = py_idx
        utf16_len = len(ch.encode("utf-16-le")) // 2
        utf16_idx += utf16_len
        py_idx    += 1
    pos_utf16_a_py[utf16_idx] = py_idx  # posición final

    TAG_APERTURA = {
        "bold":                  "<b>",
        "italic":                "<i>",
        "underline":             "<u>",
        "strikethrough":         "<s>",
        "code":                  "<code>",
        "pre":                   "<pre>",
        "spoiler":               '<span class="tg-spoiler">',
        "blockquote":            "<blockquote>",
        "expandable_blockquote": "<blockquote expandable>",
    }
    TAG_CIERRE = {
        "bold":                  "</b>",
        "italic":                "</i>",
        "underline":             "</u>",
        "strikethrough":         "</s>",
        "code":                  "<code>",
        "pre":                   "</pre>",
        "spoiler":               "</span>",
        "blockquote":            "</blockquote>",
        "expandable_blockquote": "</blockquote>",
    }

    eventos = []
    for ent in entidades_ord:
        tipo      = ent.type.name.lower() if hasattr(ent.type, "name") else str(ent.type)
        ini_py    = pos_utf16_a_py.get(ent.offset, ent.offset)
        fin_py    = pos_utf16_a_py.get(ent.offset + ent.length,
                                        ent.offset + ent.length)

        if tipo == "text_link":
            url = escape(ent.url or "")
            eventos.append((ini_py, 0, f'<a href="{url}">'))
            eventos.append((fin_py, 1, "</a>"))
        elif tipo == "text_mention":
            uid = ent.user.id if ent.user else ""
            eventos.append((ini_py, 0, f'<a href="tg://user?id={uid}">'))
            eventos.append((fin_py, 1, "</a>"))
        elif tipo in TAG_APERTURA:
            eventos.append((ini_py, 0, TAG_APERTURA[tipo]))
            eventos.append((fin_py, 1, TAG_CIERRE[tipo]))

    resultado  = []
    eventos_by_pos: dict = {}
    for pos, orden, tag in eventos:
        eventos_by_pos.setdefault(pos, [[], []])
        eventos_by_pos[pos][orden].append(tag)

    for i, ch in enumerate(texto):
        if i in eventos_by_pos:
            resultado.extend(eventos_by_pos[i][0])  # aperturas antes del char

        resultado.append(escape(ch))

        if i in eventos_by_pos:
            resultado.extend(eventos_by_pos[i][1])  # cierres después del char

    fin = len(texto)
    if fin in eventos_by_pos:
        resultado.extend(eventos_by_pos[fin][1])

    return "".join(resultado)


def inyectar_peso_en_caption(caption: str, peso_bytes: int,
                              num_archivos: int) -> str:
    """
    Agrega al final del caption en negrita HTML:
      <b>💾 Tamaño: X MB</b>   <b>📚 Archivos: N</b>
    """
    partes = []
    peso_str = formatear_peso(peso_bytes)
    if peso_str:
        partes.append(f"<b>💾 Tamaño:</b> {peso_str}")
    if num_archivos > 0:
        partes.append(f"<b>📚 Archivos:</b> {num_archivos}")
    if not partes:
        return caption
    
    caption_clean = caption.strip()
    
    # FIX: Si termina en blockquote, Telegram ya mete un salto de línea grande. 
    # Usamos solo un salto \n in vez de \n\n para evitar el bache visual.
    if caption_clean.endswith("</blockquote>"):
        separador = "\n"
    else:
        separador = "\n\n" if caption_clean else ""
        
    return f"{caption_clean}{separador}{' '.join(partes)}"


def extraer_enlaces_juego(texto_plano: str, entidades: list) -> dict:
    """
    Extrae los enlaces de juego leyendo el texto plano + entidades.
    Soporta el formato nuevo y agrupa el formato legacy.
    Retorna dict con 'trailer', 'mas_informacion'
    """
    enlaces = {
        'trailer': None,
        'mas_informacion': None
    }
    
    if not texto_plano or not entidades:
        return enlaces
    
    # Nuevo mapeo que incluye soporte legacy redirigiendo a la nueva estructura
    emoji_map = {
        '📺': 'trailer',
        '🎬': 'trailer',
        '📚': 'mas_informacion',
        '📊': 'mas_informacion',
        '🚂': 'mas_informacion'
    }
    
    for ent in entidades:
        tipo = ent.type.name.lower() if hasattr(ent.type, "name") else str(ent.type)
        if tipo != "text_link":
            continue
        
        try:
            inicio = ent.offset
            fin = ent.offset + ent.length
            url = ent.url
            texto_ent = texto_plano[inicio:fin]
            
            inicio_busqueda = max(0, inicio - 50)
            antes_texto = texto_plano[inicio_busqueda:inicio]
            
            emoji_encontrado = None
            posicion_emoji = -1
            
            for emoji, clave in emoji_map.items():
                if emoji in antes_texto:
                    pos = antes_texto.rfind(emoji)
                    if pos > posicion_emoji:
                        posicion_emoji = pos
                        emoji_encontrado = clave
            
            if not emoji_encontrado:
                texto_lower = texto_ent.lower()
                if 'trailer' in texto_lower or 'video' in texto_lower:
                    emoji_encontrado = 'trailer'
                elif any(word in texto_lower for word in ['más información', 'mas informacion', 'requisito', 'requerimiento', 'steam']):
                    emoji_encontrado = 'mas_informacion'
            
            # Solo guardamos si el enlace es válido y no hemos registrado uno antes para esa clave
            if emoji_encontrado and url and not enlaces.get(emoji_encontrado):
                enlaces[emoji_encontrado] = url
        except Exception as e:
            logger.error(f"Error procesando entidad en extracción: {e}")
            continue
            
    return enlaces


def limpiar_enlaces_del_caption(caption: str) -> str:
    """
    Limpieza secundaria de seguridad para remover líneas de emojis/pipes huérfanos
    después de haber removido las entidades links (Soporta formato nuevo y legacy).
    """
    if not caption:
        return caption
    
    # Patrón actualizado para atrapar Emojis y Textos viejos + nuevos
    patron1 = r"\n?\s*[🎬📊🚂📺📚]\s*(?:Trailer|Requisitos|Steam|Más Información|Mas Informacion)?\s*\|\s*[🎬📊🚂📺📚].*$"
    caption = re.sub(patron1, "", caption, flags=re.MULTILINE | re.IGNORECASE)
    
    # Eliminar barras divisorias solas
    patron2 = r"\n?\s*(?:[🎬📊🚂📺📚]\s*\|?\s*){2,}\s*$"
    caption = re.sub(patron2, "", caption, flags=re.MULTILINE)

    # Limpiar acumulaciones excesivas de saltos de línea sin romper párrafos legítimos
    caption = re.sub(r"\n{3,}", "\n\n", caption)
    
    # FIX: Eliminar saltos de línea huérfanos que queden atrapados justo después de un blockquote cerrado
    caption = re.sub(r"</blockquote>\s*\n+", "</blockquote>", caption)
    
    return caption.strip()


def construir_teclado_juego(enlaces: dict) -> InlineKeyboardMarkup | None:
    """Construye un teclado inline con los dos botones del nuevo formato."""
    botones_fila = []
    
    enlaces_validos = [
        ('trailer', '📺 Trailer', enlaces.get('trailer')),
        ('mas_informacion', '📚 Información', enlaces.get('mas_informacion')),
    ]
    
    for tipo, emoji_texto, url in enlaces_validos:
        if url and isinstance(url, str) and url.startswith(('http://', 'https://', 't.me/')):
            try:
                botones_fila.append(InlineKeyboardButton(text=emoji_texto, url=url))
            except Exception as e:
                logger.error(f"Error creando botón {emoji_texto}: {e}")
    
    if not botones_fila:
        return None
    return InlineKeyboardMarkup([botones_fila])


def combinar_teclados(keyboard_base: InlineKeyboardMarkup | None,
                      keyboard_juego: InlineKeyboardMarkup | None) -> InlineKeyboardMarkup:
    """Combina dos teclados inline en uno solo."""
    botones_combinados = []
    if keyboard_base and keyboard_base.inline_keyboard:
        botones_combinados.extend(keyboard_base.inline_keyboard)
    if keyboard_juego and keyboard_juego.inline_keyboard:
        botones_combinados.extend(keyboard_juego.inline_keyboard)
    return InlineKeyboardMarkup(botones_combinados) if botones_combinados else InlineKeyboardMarkup([])


def procesar_elemento_para_publicar(
    texto_mensaje: str,
    entidades_orig: list,
    peso_bytes: int,
    num_archivos: int
) -> tuple[str, dict]:
    """
    Procesa un elemento extrayendo enlaces de juego, filtrando las entidades problemáticas 
    desde el origen y saneando el formato del caption resultante.
    """
    # 1. Extraer enlaces de juego intactos
    enlaces_juego = extraer_enlaces_juego(texto_mensaje, entidades_orig)
    
    # 2. Saneamiento de URLs de terceros si la función externa lo requiere
    if hay_urls_a_limpiar(texto_mensaje):
        caption_base, entidades_base = limpiar_texto_y_entidades(texto_mensaje, entidades_orig)
    else:
        caption_base, entidades_base = texto_mensaje, list(entidades_orig)

    # 3. FILTRADO CRÍTICO: Remover las entidades text_link de juego antes de compilar el HTML
    entidades_filtradas = []
    urls_juego_valores = [v for v in enlaces_juego.values() if v]
    
    for ent in entidades_base:
        tipo = ent.type.name.lower() if hasattr(ent.type, "name") else str(ent.type)
        if tipo == "text_link" and ent.url in urls_juego_valores:
            continue  
        entidades_filtradas.append(ent)

    # 4. Convertir la estructura limpia y segura a HTML nativo
    caption_html = entidades_a_html(caption_base, entidades_filtradas)
    
    # 5. Sanear remanentes visuales de la línea de enlaces y corregir saltos post-citado
    caption_html = limpiar_enlaces_del_caption(caption_html)
    
    # 6. Inyectar metadatos de peso de manera elegante (con detección inteligente de blockquotes)
    caption_final = inyectar_peso_en_caption(caption_html, peso_bytes, num_archivos)
    
    return caption_final, enlaces_juego


# ──────────────────────────────────────────────
# CALLBACK — botones Confirmar / Cancelar
# ──────────────────────────────────────────────

async def index_publicar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los botones de confirmación enviados por el userbot"""
    query = update.callback_query
    user  = query.from_user
    data  = query.data

    if not es_staff(user.id):
        await query.answer("❌ Sin permisos.", show_alert=True)
        return

    await query.answer()

    if data.startswith("idxpub_cancel_"):
        task_id = data.replace("idxpub_cancel_", "")
        marcar_tarea(task_id, "cancelado")
        await query.edit_message_text("❌ Publicación cancelada.")
        return

    if not data.startswith("idxpub_confirm_"):
        return

    task_id = data.replace("idxpub_confirm_", "")
    tarea   = obtener_tarea(task_id)

    if not tarea:
        await query.edit_message_text("❌ Tarea no encontrada o ya procesada.")
        return

    marcar_tarea(task_id, "confirmado")
    elemento_ids = tarea["elemento_ids"]
    total        = len(elemento_ids)
    exitosos     = 0
    errores      = 0

    await query.edit_message_text(
        f"⏳ **Publicando {total} elementos...**\n\nIniciando proceso...",
        parse_mode=ParseMode.MARKDOWN
    )

    canal_destino_usado = None

    for idx, elemento_id in enumerate(elemento_ids, 1):
        msg_tmp_id = None

        try:
            elemento_data = ElementoCRUD.obtener_elemento_por_id(elemento_id)
            if not elemento_data:
                logger.warning(f"Elemento {elemento_id} no encontrado, saltando")
                errores += 1
                continue

            id_inicio       = elemento_data["id_inicio"]
            token           = elemento_data["token"]
            peso_bytes      = elemento_data.get("peso_bytes", 0)
            num_archivos    = elemento_data.get("num_archivos", 0)
            enlace_elemento = f"{BOT_URL}?start={token}"

            # NUEVO SISTEMA: Origen y destino dinámicos
            almacen_origen = elemento_data.get("almacen_id") or ADMINISTRATION_GROUP
            canal_destino = ALMACENES_MAP.get(almacen_origen) or CANAL_ELEMENTOS
            canal_destino_usado = canal_destino

            mensaje_origen = await context.bot.forward_message(
                chat_id=query.message.chat_id,
                from_chat_id=almacen_origen, # Actualizado
                message_id=id_inicio
            )
            msg_tmp_id = mensaje_origen.message_id

            tiene_caption   = mensaje_origen.caption is not None
            texto_mensaje   = mensaje_origen.caption or mensaje_origen.text or ""
            boton_texto     = extraer_primer_linea(texto_mensaje)
            urls_especiales = extraer_urls_especiales(texto_mensaje)
            entidades_orig  = mensaje_origen.caption_entities or mensaje_origen.entities or []

            caption_final, enlaces_juego = procesar_elemento_para_publicar(
                texto_mensaje,
                entidades_orig,
                peso_bytes,
                num_archivos
            )

            await context.bot.delete_message(
                chat_id=query.message.chat_id,
                message_id=msg_tmp_id
            )
            msg_tmp_id = None

            keyboard_base = construir_teclado_botones(enlace_elemento, boton_texto, urls_especiales)
            keyboard_juego = construir_teclado_juego(enlaces_juego)
            keyboard = combinar_teclados(keyboard_base, keyboard_juego)

            copy_kwargs = {
                "chat_id":      canal_destino,  # Actualizado
                "from_chat_id": almacen_origen, # Actualizado
                "message_id":   id_inicio,
            }
            
            if keyboard and keyboard.inline_keyboard:
                copy_kwargs["reply_markup"] = keyboard
            
            if tiene_caption:
                copy_kwargs["caption"]    = caption_final
                copy_kwargs["parse_mode"] = ParseMode.HTML

            await context.bot.copy_message(**copy_kwargs)
            exitosos += 1

            if idx < total:
                await asyncio.sleep(3)

        except TelegramError as e:
            logger.error(f"TelegramError publicando elemento {elemento_id}: {e}")
            errores += 1
            if msg_tmp_id:
                try:
                    await context.bot.delete_message(chat_id=query.message.chat_id, message_id=msg_tmp_id)
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Error publicando elemento {elemento_id}: {e}", exc_info=True)
            errores += 1

        try:
            await query.edit_message_text(
                f"⏳ **Publicando {total} elementos...**\n\n"
                f"📊 Progreso: `{idx}/{total}`\n"
                f"✅ Exitosos: `{exitosos}`\n"
                f"❌ Errores: `{errores}`",
                parse_mode=ParseMode.MARKDOWN
            )
        except TelegramError:
            pass

    try:
        await query.edit_message_text(
            f"✅ **Publicación completada**\n\n"
            f"📦 Total procesados: `{total}`\n"
            f"✅ Exitosos: `{exitosos}`\n"
            f"❌ Errores: `{errores}`\n"
            f"📺 Canal: `{canal_destino_usado or CANAL_ELEMENTOS}`\n"
            f"👤 Confirmado por: {escape(user.first_name)}",
            parse_mode=ParseMode.MARKDOWN
        )
    except TelegramError:
        pass


def register_index_publisher_handler(application):
    """Registra el callback handler — sin CommandHandler, solo botones inline"""
    application.add_handler(CallbackQueryHandler(
        index_publicar_callback,
        pattern=r"^idxpub_(confirm|cancel)_"
    ))