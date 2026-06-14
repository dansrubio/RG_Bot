"""
Handler para búsqueda de películas y series en TMDB.
Incluye soporte de auto-limpieza, búsqueda progresiva y paginación interactiva.
"""

import html
import logging
import re
import requests
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from config import is_staff, TMDB_API_KEY

logger = logging.getLogger(__name__)

MAX_DESCRIPTION_LENGTH = 500
TMDB_BASE_URL = "https://api.themoviedb.org/3"


def limpiar_nombre_archivo_cine(texto: str) -> str:
    """
    Limpia nombres de archivos multimedia (resoluciones, años, codecs, ripeos)
    para aislar el título real de la película o serie.
    """
    if not texto:
        return ""
    
    nombre = texto.lower()
    
    # Quitar etiquetas de calidad, codecs, formatos y grupos comunes
    patrones_basura = [
        r'\b(1080p|720p|4k|2160p|uhd|bluray|blu-ray|brrip|dvdrip|hdtv|web-dl|webrip)\b',
        r'\b(x264|x265|hevc|h264|h265|aac|dts|dd5\.1|ac3)\b',
        r'\b(dual|latino|castellano|subtitulado|subbed|multi)\b',
        r'\b(remux|repack|cine|rip)\b',
        r'\b(yts|yify|rarbg|psa|galaxyrg|fgt)\b'
    ]
    
    for patron in patrones_basura:
        nombre = re.sub(patron, '', nombre)
        
    # Quitar años (ej. .2024. o [2019]) dejando el espacio
    nombre = re.sub(r'[\(\[\s\.]\d{4}[\)\]\s\.]', ' ', nombre)
    
    # Reemplazar puntos, guiones y guiones bajos por espacios
    nombre = re.sub(r'[\.\-_]', ' ', nombre)
    
    # Quitar extensiones de video comunes
    nombre = re.sub(r'\b(mp4|mkv|avi|mov|flv|iso)\b', '', nombre)
    
    # Limpiar espacios dobles o residuales
    nombre = re.sub(r'\s+', ' ', nombre).strip()
    
    return nombre.title()


def truncate_text(text, max_length=MAX_DESCRIPTION_LENGTH):
    if not text:
        return ""
    if len(text) > max_length:
        truncated = text[:max_length].rsplit(' ', 1)[0]
        return truncated + "..."
    return text


def hashtags_from_genres(genres):
    if not genres:
        return ""
    hashtags = []
    for genre in genres:
        genre_name = genre.get('name', '').strip() if isinstance(genre, dict) else str(genre).strip()
        if genre_name:
            hashtag = "#" + re.sub(r'[^a-zA-Z0-9ñáéíóúÑÁÉÍÓÚ]', '', genre_name.replace(' ', ''))
            hashtags.append(hashtag)
    return " ".join(hashtags) if hashtags else ""


def get_movie_trailer(movie_id, media_type="movie"):
    """Busca el trailer oficial en YouTube desde la API de TMDB"""
    try:
        url = f"{TMDB_BASE_URL}/{media_type}/{movie_id}/videos?api_key={TMDB_API_KEY}&language=es-ES"
        response = requests.get(url, timeout=10)
        videos = response.json().get("results", [])
        
        if not videos:
            url = f"{TMDB_BASE_URL}/{media_type}/{movie_id}/videos?api_key={TMDB_API_KEY}&language=en-US"
            response = requests.get(url, timeout=10)
            videos = response.json().get("results", [])

        for video in videos:
            if video.get("site") == "YouTube" and video.get("type") in ["Trailer", "Teaser"]:
                return f"https://www.youtube.com/watch?v={video.get('key')}"
        return None
    except Exception:
        return None


def build_tmdb_post(media_id, media_type="movie"):
    """Construye el diccionario de datos listos para el post de Telegram"""
    try:
        url = f"{TMDB_BASE_URL}/{media_type}/{media_id}?api_key={TMDB_API_KEY}&language=es-ES"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        title = data.get('title', data.get('name', 'Sin título')).strip()
        release_date = data.get('release_date', data.get('first_air_date', 'Fecha no disponible')).strip()
        
        genres = data.get('genres', [])
        hashtags = hashtags_from_genres(genres)
        
        vote_average = data.get('vote_average')
        rating = f"{round(vote_average, 1)}/10" if vote_average else None
        
        overview = data.get('overview', 'Sin sinopsis disponible.')
        description_truncated = truncate_text(overview, MAX_DESCRIPTION_LENGTH)
        
        poster_path = data.get('poster_path')
        image_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
        
        trailer_url = get_movie_trailer(media_id, media_type)
        tmdb_page_url = f"https://www.themoviedb.org/{media_type}/{media_id}"

        extra_info = ""
        if media_type == "tv":
            seasons = data.get('number_of_seasons', 1)
            episodes = data.get('number_of_episodes', 0)
            extra_info = f"📺 <b>Temporadas:</b> {seasons} | 🎞️ <b>Episodios:</b> {episodes}"
        else:
            runtime = data.get('runtime', 0)
            if runtime:
                extra_info = f"⏳ <b>Duración:</b> {runtime} min"

        return {
            'title': title,
            'id': media_id,
            'media_type': media_type,
            'hashtags': hashtags,
            'release_date': release_date,
            'rating': rating,
            'description': description_truncated,
            'image_url': image_url,
            'trailer_url': trailer_url,
            'tmdb_page_url': tmdb_page_url,
            'extra_info': extra_info
        }
    except Exception as e:
        logger.error(f"❌ Error construyendo post de TMDB: {e}")
        return None


def format_cine_telegram(post):
    if not post:
        return None

    # CAMBIO AQUÍ: Ahora el título del post de entrega incluye solo el emoji, un espacio y el nombre
    icon = "🎬" if post['media_type'] == "movie" else "📺"
    lines = [
        f"<b>{icon} {html.escape(post['title'])}</b>",
        ""
    ]
    if post['hashtags']:
        lines.append(f"🎭 <b>Géneros:</b> {post['hashtags']}")
    if post['release_date'] != 'Fecha no disponible':
        lines.append(f"📅 <b>Lanzamiento:</b> {html.escape(post['release_date'])}")
    if post['rating']:
        lines.append(f"⭐ <b>TMDB Rating:</b> {html.escape(post['rating'])}")
    if post['extra_info']:
        lines.append(post['extra_info'])

    lines.extend(["", "<b>Sinopsis:</b>"])
    lines.append(f"<blockquote>{html.escape(post['description'])}</blockquote>" if post['description'] else "<blockquote>Sin descripción disponible</blockquote>")
    lines.append("")

    links_line = []
    if post.get('trailer_url'):
        links_line.append(f"<a href='{post['trailer_url']}'>📺 Ver Trailer</a>")
    if post.get('tmdb_page_url'):
        links_line.append(f"<a href='{post['tmdb_page_url']}'>🌐 Ficha TMDB</a>")
    
    if links_line:
        lines.append(" | ".join(links_line))

    formatted = "\n".join(lines)
    return formatted[:4093] + "..." if len(formatted) > 4096 else formatted


def build_cine_keyboard(results, page=0):
    per_page = 9
    start, end = page * per_page, (page * per_page) + per_page
    buttons = []

    for r in results[start:end]:
        title = r.get("title", r.get("name", "Sin título"))
        media_type = r.get("media_type", "movie")
        icon = "🎬" if media_type == "movie" else "📺"
        
        # MANTENIDO AQUÍ: Los años se siguen agregando al botón de la lista interactiva
        year = r.get("release_date", r.get("first_air_date", ""))[:4]
        year_str = f" ({year})" if year else ""
        
        btn_text = f"{icon} {title}"
        if len(btn_text) > 28:
            btn_text = btn_text[:25] + "..."
        btn_text += year_str

        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"tmdbmedia_{media_type}_{r['id']}")])

    nav_buttons = []
    if start > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"tmdbpage_{page - 1}"))
    if end < len(results):
        nav_buttons.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"tmdbpage_{page + 1}"))
    if nav_buttons:
        buttons.append(nav_buttons)

    return InlineKeyboardMarkup(buttons)


async def buscarcine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_staff(user_id):
        await update.message.reply_text("🚫 No tienes permiso para usar este comando.")
        return

    raw_query = " ".join(context.args).strip()
    if not raw_query:
        await update.message.reply_text("❌ Debes escribir el nombre de la película o serie.\n\nEjemplo: <code>/cine Matrix</code>", parse_mode="HTML")
        return

    nombre_limpio = limpiar_nombre_archivo_cine(raw_query)
    query_actual = nombre_limpio if nombre_limpio else raw_query
    
    results = []
    intento_fallbacks = False
    termino_exitoso = query_actual

    try:
        while len(query_actual.split()) >= 1:
            search_url = f"{TMDB_BASE_URL}/search/multi?api_key={TMDB_API_KEY}&query={query_actual}&language=es-ES&page=1"
            response = requests.get(search_url, timeout=10)
            response.raise_for_status()

            all_results = response.json().get("results", [])
            results = [item for item in all_results if item.get('media_type') in ['movie', 'tv']]

            if results:
                termino_exitoso = query_actual
                break
            
            palabras = query_actual.split()
            if len(palabras) <= 1:
                break
            
            query_actual = " ".join(palabras[:-1])
            intento_fallbacks = True

        if not results and nombre_limpio != raw_query:
            query_actual = raw_query
            search_url = f"{TMDB_BASE_URL}/search/multi?api_key={TMDB_API_KEY}&query={query_actual}&language=es-ES&page=1"
            response = requests.get(search_url, timeout=10)
            all_results = response.json().get("results", [])
            results = [item for item in all_results if item.get('media_type') in ['movie', 'tv']]
            termino_exitoso = raw_query
            intento_fallbacks = False

        if not results:
            await update.message.reply_text(f"❌ No se encontraron producciones para: <b>{html.escape(raw_query)}</b>", parse_mode="HTML")
            return

        context.user_data[f'tmdb_{chat_id}_results'] = results
        context.user_data[f'tmdb_{chat_id}_query'] = raw_query
        context.user_data[f'tmdb_{chat_id}_page'] = 0

        texto_busqueda = f"<b>{html.escape(raw_query)}</b>"
        if intento_fallbacks:
            texto_busqueda += f" <i>(Filtro inteligente: {html.escape(termino_exitoso)})</i>"
        elif nombre_limpio != raw_query and termino_exitoso == nombre_limpio:
            texto_busqueda += f" <i>(Procesado como: {html.escape(nombre_limpio)})</i>"

        await update.message.reply_text(
            f"🎬 Resultados para: {texto_busqueda}\n\nElige una opción:",
            reply_markup=build_cine_keyboard(results, page=0),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"❌ Error en búsqueda de TMDB: {e}")
        await update.message.reply_text(f"❌ Error en la búsqueda: {str(e)}")


async def tmdb_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        chat_id = update.effective_chat.id
        
        if query.data.startswith("tmdbpage_"):
            page = int(query.data.split("_")[1])
            tmdb_results = context.user_data.get(f'tmdb_{chat_id}_results', [])
            if not tmdb_results:
                await query.edit_message_text("❌ No hay resultados para paginar.")
                return

            context.user_data[f'tmdb_{chat_id}_page'] = page
            await query.edit_message_reply_markup(reply_markup=build_cine_keyboard(tmdb_results, page=page))
            return

        if query.data.startswith("tmdbmedia_"):
            partes = query.data.split("_")
            media_type = partes[1]
            media_id = partes[2]
            
            await query.edit_message_text("⏳ Obteniendo información de la cartelera...")

            post = build_tmdb_post(media_id, media_type)
            if not post:
                await query.edit_message_text("❌ No se pudo obtener la información de TMDB.")
                return

            caption = format_cine_telegram(post)
            if not caption:
                await query.edit_message_text("❌ Error al formatear la información.")
                return

            if post.get('image_url'):
                await context.bot.send_photo(chat_id=chat_id, photo=post['image_url'], caption=caption, parse_mode="HTML")
            else:
                await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode="HTML")

            await query.delete_message()
    except Exception as e:
        logger.error(f"❌ Error en tmdb_button: {e}", exc_info=True)
        try:
            await query.edit_message_text(f"❌ Error: {str(e)[:100]}")
        except Exception:
            pass


def register_cine_handlers(application):
    """Registra los handlers del módulo en la app principal."""
    application.add_handler(CommandHandler(["cine", "movie", "tv"], buscarcine))
    application.add_handler(CallbackQueryHandler(tmdb_button, pattern="^(tmdbmedia_|tmdbpage_)"))