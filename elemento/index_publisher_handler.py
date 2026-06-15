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
    return is_admin(user_id) or is_moderator(user_id)


def obtener_tarea(task_id: str) -> dict | None:
    try:
        return get_database().publicacion_pendiente.find_one(
            {"_id": task_id, "estado": "pendiente"}
        )
    except Exception as e:
        logger.error(f"Error obteniendo tarea {task_id}: {e}")
        return None


def marcar_tarea(task_id: str, estado: str) -> None:
    try:
        get_database().publicacion_pendiente.update_one(
            {"_id": task_id},
            {"$set": {"estado": estado}}
        )
    except Exception as e:
        logger.error(f"Error actualización tarea {task_id}: {e}")


def formatear_peso(bytes_total: int) -> str:
    if bytes_total <= 0:
        return ""
    if bytes_total >= 1_073_741_824:
        valor = bytes_total / 1_073_741_824
        return f"{valor:.2f} GB".rstrip("0").rstrip(".")
    if bytes_total >= 1_048_576:
        valor = bytes_total / 1_048_576
        return f"{valor:.1f} MB" if valor % 1 else f"{int(valor)} MB"
    return f"{bytes_total / 1024:.0f} KB"


def normalizar_chat_id(chat_id: int) -> int:
    """Extrae el número absoluto limpio del ID para comparaciones seguras"""
    id_abs = abs(chat_id)
    if str(id_abs).startswith("100"):
        return int(str(id_abs)[3:])
    return id_abs

def obtener_canal_destino(almacen_origen: int) -> int:
    """Busca el destino normalizando los IDs para evitar errores de mapeo"""
    if not almacen_origen or not ALMACENES_MAP:
        return CANAL_ELEMENTOS
    id_norm = normalizar_chat_id(almacen_origen)
    for almac, dest in ALMACENES_MAP.items():
        if normalizar_chat_id(almac) == id_norm:
            return dest
    return CANAL_ELEMENTOS


def entidades_a_html(texto: str, entidades: list) -> str:
    if not entidades or not texto:
        return escape(texto)

    entidades_ord = sorted(entidades, key=lambda e: e.offset)
    texto_utf16  = texto.encode("utf-16-le")
    chars_utf16  = [texto_utf16[i:i+2] for i in range(0, len(texto_utf16), 2)]

    pos_utf16_a_py = {}
    py_idx = 0
    utf16_idx = 0
    for ch in texto:
        pos_utf16_a_py[utf16_idx] = py_idx
        utf16_len = len(ch.encode("utf-16-le")) // 2
        utf16_idx += utf16_len
        py_idx    += 1
    pos_utf16_a_py[utf16_idx] = py_idx

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
            resultado.extend(eventos_by_pos[i][0])
        resultado.append(escape(ch))
        if i in eventos_by_pos:
            resultado.extend(eventos_by_pos[i][1])

    fin = len(texto)
    if fin in eventos_by_pos:
        resultado.extend(eventos_by_pos[fin][1])

    return "".join(resultado)


def inyectar_peso_en_caption(caption: str, peso_bytes: int, num_archivos: int) -> str:
    partes = []
    peso_str = formatear_peso(peso_bytes)
    if peso_str:
        partes.append(f"<b>💾 Tamaño:</b> {peso_str}")
    if num_archivos > 0:
        partes.append(f"<b>📚 Archivos:</b> {num_archivos}")
    if not partes:
        return caption
    
    caption_clean = caption.strip()
    if caption_clean.endswith("</blockquote>"):
        separador = "\n"
    else:
        separador = "\n\n" if caption_clean else ""
        
    return f"{caption_clean}{separador}{' '.join(partes)}"


def extraer_enlaces_juego(texto_plano: str, entidades: list) -> dict:
    enlaces = {'trailer': None, 'mas_informacion': None}
    if not texto_plano or not entidades:
        return enlaces
    
    emoji_map = {
        '📺': 'trailer', '🎬': 'trailer',
        '📚': 'mas_informacion', '📊': 'mas_informacion', '🚂': 'mas_informacion'
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
            
            if emoji_encontrado and url and not enlaces.get(emoji_encontrado):
                enlaces[emoji_encontrado] = url
        except Exception as e:
            continue
    return enlaces


def limpiar_enlaces_del_caption(caption: str) -> str:
    if not caption:
        return caption
    patron1 = r"\n?\s*[🎬📊🚂📺📚]\s*(?:Trailer|Requisitos|Steam|Más Información|Mas Informacion)?\s*\|\s*[🎬📊🚂📺📚].*$"
    caption = re.sub(patron1, "", caption, flags=re.MULTILINE | re.IGNORECASE)
    patron2 = r"\n?\s*(?:[🎬📊🚂📺📚]\s*\|?\s*){2,}\s*$"
    caption = re.sub(patron2, "", caption, flags=re.MULTILINE)
    caption = re.sub(r"\n{3,}", "\n\n", caption)
    caption = re.sub(r"</blockquote>\s*\n+", "</blockquote>", caption)
    return caption.strip()


def construir_teclado_juego(enlaces: dict) -> InlineKeyboardMarkup | None:
    botones_fila = []
    enlaces_validos = [
        ('trailer', '📺 Trailer', enlaces.get('trailer')),
        ('mas_informacion', '📚 Información', enlaces.get('mas_informacion')),
    ]
    for tipo, emoji_texto, url in enlaces_validos:
        if url and isinstance(url, str) and url.startswith(('http://', 'https://', 't.me/')):
            try:
                botones_fila.append(InlineKeyboardButton(text=emoji_texto, url=url))
            except Exception:
                pass
    if not botones_fila:
        return None
    return InlineKeyboardMarkup([botones_fila])


def combinar_teclados(keyboard_base: InlineKeyboardMarkup | None, keyboard_juego: InlineKeyboardMarkup | None) -> InlineKeyboardMarkup:
    botones_combinados = []
    if keyboard_base and keyboard_base.inline_keyboard:
        botones_combinados.extend(keyboard_base.inline_keyboard)
    if keyboard_juego and keyboard_juego.inline_keyboard:
        botones_combinados.extend(keyboard_juego.inline_keyboard)
    return InlineKeyboardMarkup(botones_combinados) if botones_combinados else InlineKeyboardMarkup([])


def procesar_elemento_para_publicar(texto_mensaje: str, entidades_orig: list, peso_bytes: int, num_archivos: int) -> tuple[str, dict]:
    enlaces_juego = extraer_enlaces_juego(texto_mensaje, entidades_orig)
    if hay_urls_a_limpiar(texto_mensaje):
        caption_base, entidades_base = limpiar_texto_y_entidades(texto_mensaje, entidades_orig)
    else:
        caption_base, entidades_base = texto_mensaje, list(entidades_orig)

    entidades_filtradas = []
    urls_juego_valores = [v for v in enlaces_juego.values() if v]
    for ent in entidades_base:
        tipo = ent.type.name.lower() if hasattr(ent.type, "name") else str(ent.type)
        if tipo == "text_link" and ent.url in urls_juego_valores:
            continue  
        entidades_filtradas.append(ent)

    caption_html = entidades_a_html(caption_base, entidades_filtradas)
    caption_html = limpiar_enlaces_del_caption(caption_html)
    caption_final = inyectar_peso_en_caption(caption_html, peso_bytes, num_archivos)
    return caption_final, enlaces_juego


# ──────────────────────────────────────────────
# CALLBACK — botones Confirmar / Cancelar
# ──────────────────────────────────────────────

async def index_publicar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        f"⏳ <b>Publicando {total} elementos...</b>\n\nIniciando proceso...",
        parse_mode=ParseMode.HTML
    )

    canal_destino_usado = None

    for idx, elemento_id in enumerate(elemento_ids, 1):
        msg_tmp_ids = []

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

            almacen_origen = elemento_data.get("almacen_id") or ADMINISTRATION_GROUP
            canal_destino = obtener_canal_destino(almacen_origen)
            canal_destino_usado = canal_destino

            # 🛠️ HACK: Bypass de protección de reenvío.
            # Copiamos primero (permitido) y reenviamos esa copia para leer las entities enteras
            msg_tmp_copy = await context.bot.copy_message(
                chat_id=query.message.chat_id,
                from_chat_id=almacen_origen,
                message_id=id_inicio
            )
            msg_tmp_ids.append(msg_tmp_copy.message_id)

            mensaje_origen = await context.bot.forward_message(
                chat_id=query.message.chat_id,
                from_chat_id=query.message.chat_id,
                message_id=msg_tmp_copy.message_id
            )
            msg_tmp_ids.append(mensaje_origen.message_id)

            tiene_caption   = mensaje_origen.caption is not None
            texto_mensaje   = mensaje_origen.caption or mensaje_origen.text or ""
            boton_texto     = extraer_primer_linea(texto_mensaje)
            urls_especiales = extraer_urls_especiales(texto_mensaje)
            entidades_orig  = mensaje_origen.caption_entities or mensaje_origen.entities or []

            caption_final, enlaces_juego = procesar_elemento_para_publicar(
                texto_mensaje, entidades_orig, peso_bytes, num_archivos
            )

            keyboard_base = construir_teclado_botones(enlace_elemento, boton_texto, urls_especiales)
            keyboard_juego = construir_teclado_juego(enlaces_juego)
            keyboard = combinar_teclados(keyboard_base, keyboard_juego)

            copy_kwargs = {
                "chat_id":      canal_destino,
                "from_chat_id": almacen_origen,
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

        except Exception as e:
            logger.error(f"Error publicando elemento {elemento_id}: {e}", exc_info=True)
            errores += 1

        finally:
            # Limpieza segura sin importar si falló
            for m_id in msg_tmp_ids:
                try:
                    await context.bot.delete_message(chat_id=query.message.chat_id, message_id=m_id)
                except Exception:
                    pass

        try:
            await query.edit_message_text(
                f"⏳ <b>Publicando {total} elementos...</b>\n\n"
                f"📊 Progreso: <code>{idx}/{total}</code>\n"
                f"✅ Exitosos: <code>{exitosos}</code>\n"
                f"❌ Errores: <code>{errores}</code>",
                parse_mode=ParseMode.HTML
            )
        except TelegramError:
            pass

    try:
        await query.edit_message_text(
            f"✅ <b>Publicación completada</b>\n\n"
            f"📦 Total procesados: <code>{total}</code>\n"
            f"✅ Exitosos: <code>{exitosos}</code>\n"
            f"❌ Errores: <code>{errores}</code>\n"
            f"📺 Canal: <code>{canal_destino_usado or CANAL_ELEMENTOS}</code>\n"
            f"👤 Confirmado por: {escape(user.first_name)}",
            parse_mode=ParseMode.HTML
        )
    except TelegramError:
        pass


def register_index_publisher_handler(application):
    application.add_handler(CallbackQueryHandler(
        index_publicar_callback,
        pattern=r"^idxpub_(confirm|cancel)_"
    ))