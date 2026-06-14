"""
Handler para búsqueda de juegos en Steam utilizando la API pública de Valve.
Incluye soporte de auto-limpieza inteligente y búsqueda progresiva para nombres de archivos complejos.
"""

import html
import logging
import re
import requests
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from config import is_staff
from external_apis.services.steam_telegraph_service import steam_telegraph_service

logger = logging.getLogger(__name__)

MAX_DESCRIPTION_LENGTH = 500


def limpiar_nombre_archivo(texto: str) -> str:
    """
    Limpia nombres de archivos de escenas (RUNE, Goldberg, zip, iso, fechas)
    para aislar el nombre real del juego.
    """
    if not texto:
        return ""
    
    nombre = texto.lower()
    
    # Quitar prefijos comunes de grupos
    nombre = re.sub(r'^(rune|codename|goldberg|tenoke|flt|skidrow|razor1911|p2p)[\-_]', '', nombre)
    
    # Quitar sufijos de grupos y estados de desarrollo al final
    sufijos_basura = [
        r'[\-_](goldberg|goldberg\s*emulator|rune|tenoke|flt|skidrow|codex|plaza|fitgirl|dodi|elamigos)',
        r'[\-_]early[\-_]access', r'early[\-_]access',
        r'[\-_]pre[\-_]activated',
        r'\.v?\d{6,8}',  # Fechas formato v20230206 o 20230206
        r'\.v?\d+(\.\d+)*', # Versiones estándar como v1.0.3 o 2.0
    ]
    for sufijo in sufijos_basura:
        nombre = re.sub(sufijo, '', nombre)
        
    # Reemplazar puntos, guiones y guiones bajos por espacios
    nombre = re.sub(r'[\.\-_]', ' ', nombre)
    
    # Quitar extensiones de archivos comunes
    nombre = re.sub(r'\b(zip|rar|7z|iso|exe|tar|gz)\b', '', nombre)
    
    # Limpiar espacios dobles o residuales
    nombre = re.sub(r'\s+', ' ', nombre).strip()
    
    return nombre.title()


def clean_html(text):
    if not text:
        return ""
    text = re.sub(r'(<br\s*/?>)+', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


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
        genre_name = genre.get('description', '').strip() if isinstance(genre, dict) else str(genre).strip()
        if genre_name:
            hashtag = "#" + re.sub(r'[^a-zA-Z0-9ñáéíóúÑÁÉÍÓÚ]', '', genre_name.replace(' ', ''))
            hashtags.append(hashtag)
    return " ".join(hashtags) if hashtags else ""


def get_screenshots_for_telegraph(data):
    try:
        screenshots = data.get('screenshots', [])
        if isinstance(screenshots, list):
            return [shot.get('path_full') for shot in screenshots[:5] if isinstance(shot, dict) and shot.get('path_full')]
        return None
    except Exception:
        return None


def get_review_summary_from_api(appid):
    try:
        reviews_url = f"https://store.steampowered.com/appreviews/{appid}?json=1&language=spanish"
        response = requests.get(reviews_url, timeout=10)
        response.raise_for_status()
        reviews_data = response.json()

        if not reviews_data.get('success', False):
            return None

        query_summary = reviews_data.get('query_summary', {})
        review_score_desc = query_summary.get('review_score_desc', '')
        total_positive = query_summary.get('total_positive', 0)
        total_negative = query_summary.get('total_negative', 0)

        if not review_score_desc:
            return None

        label_map = {
            'Overwhelmingly Positive': 'Extremadamente positivas',
            'Very Positive': 'Muy positivas',
            'Mostly Positive': 'Principalmente positivas',
            'Mixed': 'Variadas',
            'Mostly Negative': 'Principalmente negativas',
            'Very Negative': 'Muy negativas',
            'Overwhelmingly Negative': 'Extremadamente negativas',
            'Positive': 'Positivas',
            'Negative': 'Negativas',
        }
        label_es = label_map.get(review_score_desc, review_score_desc)
        total_reviews = total_positive + total_negative
        if total_reviews > 0:
            positive_percentage = round((total_positive / total_reviews) * 100)
            return f"{label_es} ({positive_percentage}%)"
        return label_es
    except Exception:
        return None


def get_game_requirements(data):
    try:
        requirements = {}
        pc_requirements = data.get('pc_requirements', {})
        if isinstance(pc_requirements, dict):
            for req_type in ['minimum', 'recommended']:
                req_val = pc_requirements.get(req_type, '')
                if isinstance(req_val, str) and req_val.strip():
                    clean_req = clean_html(req_val)
                    if clean_req:
                        requirements[req_type] = clean_req
        return requirements if requirements else None
    except Exception:
        return None


def get_game_trailer(data):
    try:
        movies = data.get("movies", [])
        if not isinstance(movies, list) or len(movies) == 0:
            return None
        for highlight_only in [True, False]:
            for movie in movies:
                if not isinstance(movie, dict) or (highlight_only and not movie.get('highlight', False)):
                    continue
                for quality_key in ['hls_h264', 'dash_h264', 'dash_av1']:
                    url = movie.get(quality_key, '').strip()
                    if url:
                        return url
        return None
    except Exception:
        return None


def build_steam_game_post(appid):
    try:
        details_url = f"https://store.steampowered.com/api/appdetails?appids={appid}&l=spanish&cc=ES"
        response = requests.get(details_url, timeout=10)
        response.raise_for_status()
        api_data = response.json()

        if str(appid) not in api_data or not api_data[str(appid)].get('success', False):
            return None

        data = api_data[str(appid)].get('data', {})
        game_name = data.get('name', 'Sin título').strip()
        
        if not game_name or game_name == 'Sin título':
            return None

        genres = [g.get('description', '').strip() for g in data.get('genres', []) if isinstance(g, dict)]
        hashtags = hashtags_from_genres(genres)
        release_date = data.get('release_date', {}).get('date', 'Fecha no disponible').strip()
        metacritic_score = data.get('metacritic', {}).get('score')

        developers = ", ".join([d.strip() for d in data.get('developers', []) if d.strip()]) or "Desconocido"
        publishers = ", ".join([p.strip() for p in data.get('publishers', []) if p.strip()]) or "Desconocido"

        short_desc = clean_html(data.get('short_description', data.get('detailed_description', '')))
        description_truncated = truncate_text(short_desc, MAX_DESCRIPTION_LENGTH)

        trailer_url = get_game_trailer(data)
        requirements = get_game_requirements(data)
        review_summary = get_review_summary_from_api(appid)
        screenshots_urls = get_screenshots_for_telegraph(data)

        requirements_telegraph_url = None
        if requirements or screenshots_urls or short_desc:
            requirements_telegraph_url = steam_telegraph_service.create_requirements_page(
                game_name=game_name,
                full_data=data,
                requirements=requirements,
                screenshots_urls=screenshots_urls
            )

        return {
            'game_name': game_name,
            'appid': appid,
            'hashtags': hashtags,
            'release_date': release_date,
            'metacritic_score': metacritic_score,
            'review_summary': review_summary,
            'developers': developers,
            'publishers': publishers,
            'description': description_truncated,
            'trailer_url': trailer_url,
            'requirements_telegraph_url': requirements_telegraph_url
        }
    except Exception as e:
        logger.error(f"❌ Error construyendo post de Steam: {e}")
        return None


def format_post_telegram(post):
    if not post:
        return None

    lines = [
        f"<b>{html.escape(post['game_name'])}</b>",
        ""
    ]
    if post['hashtags']:
        lines.append(f"🎲 <b>Géneros:</b> {post['hashtags']}")
    if post['release_date'] != 'Fecha no disponible':
        lines.append(f"📅 <b>Lanzamiento:</b> {html.escape(post['release_date'])}")
    if post['metacritic_score']:
        lines.append(f"⭐ <b>Metacritic:</b> {html.escape(str(post['metacritic_score']))}/100")
    if post['review_summary']:
        lines.append(f"📊 <b>Reviews:</b> {html.escape(post['review_summary'])}")
    if post['developers'] != 'Desconocido':
        lines.append(f"👨‍💻 <b>Desarrollador:</b> {html.escape(post['developers'])}")
    if post['publishers'] != 'Desconocido':
        lines.append(f"🏢 <b>Publicador:</b> {html.escape(post['publishers'])}")

    lines.extend(["", "<b>Descripción:</b>"])
    lines.append(f"<blockquote>{html.escape(post['description'])}</blockquote>" if post['description'] else "<blockquote>Sin descripción disponible</blockquote>")
    lines.append("")

    links_line = []
    if post.get('trailer_url'):
        links_line.append(f"<a href='{post['trailer_url']}'>📺 Trailer</a>")
    if post.get('requirements_telegraph_url'):
        links_line.append(f"<a href='{post['requirements_telegraph_url']}'>📚 Información</a>")
    
    if links_line:
        lines.append(" | ".join(links_line))

    formatted = "\n".join(lines)
    return formatted[:4093] + "..." if len(formatted) > 4096 else formatted


def build_steam_keyboard(results, page=0):
    per_page = 9
    start, end = page * per_page, (page * per_page) + per_page
    buttons = []

    for r in results[start:end]:
        name = r.get("name", "Sin título")
        btn_text = name[:30] + "..." if len(name) > 30 else name
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"steamgame_{r['id']}")])

    nav_buttons = []
    if start > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"steampage_{page - 1}"))
    if end < len(results):
        nav_buttons.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"steampage_{page + 1}"))
    if nav_buttons:
        buttons.append(nav_buttons)

    return InlineKeyboardMarkup(buttons)


def is_dlc_or_soundtrack(name):
    exclude_keywords = ['dlc', 'soundtrack', 'ost', 'voice pack', 'pack', 'demo', 'supporter pack', 'cosmetic', 'season pass', 'bundle', 'artbook', 'manual', 'wallpaper']
    name_lower = name.lower()
    return any(keyword in name_lower for keyword in exclude_keywords)


async def buscarjuego(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_staff(user_id):
        await update.message.reply_text("🚫 No tienes permiso para usar este comando.")
        return

    raw_query = " ".join(context.args).strip()
    if not raw_query:
        await update.message.reply_text("❌ Debes escribir el nombre del juego o archivo a buscar.\n\nEjemplo: <code>/game Elden Ring</code>", parse_mode="HTML")
        return

    # 1. Limpieza inicial del nombre del archivo
    nombre_limpio = limpiar_nombre_archivo(raw_query)
    query_actual = nombre_limpio if nombre_limpio else raw_query
    
    results = []
    intento_fallbacks = False
    termino_exitoso = query_actual

    try:
        # Loop de búsqueda progresiva (Fallback)
        # Si no hay resultados, va eliminando la última palabra del string hasta que encuentre algo o se quede con 1 palabra
        while len(query_actual.split()) >= 1:
            search_url = f"https://store.steampowered.com/api/storesearch/?term={query_actual}&l=spanish&cc=ES"
            response = requests.get(search_url, timeout=10)
            response.raise_for_status()

            all_results = response.json().get("items", [])
            results = [item for item in all_results if not is_dlc_or_soundtrack(item.get('name', ''))]

            if results:
                termino_exitoso = query_actual
                break
            
            # Si no hubo resultados, recortamos la última palabra e indicamos que se usó el fallback
            palabras = query_actual.split()
            if len(palabras) <= 1:
                break
            
            query_actual = " ".join(palabras[:-1])
            intento_fallbacks = True

        # Último recurso: si el fallback progresivo falló por completo, intentamos con el texto 100% original de entrada
        if not results and nombre_limpio != raw_query:
            query_actual = raw_query
            search_url = f"https://store.steampowered.com/api/storesearch/?term={query_actual}&l=spanish&cc=ES"
            response = requests.get(search_url, timeout=10)
            all_results = response.json().get("items", [])
            results = [item for item in all_results if not is_dlc_or_soundtrack(item.get('name', ''))]
            termino_exitoso = raw_query
            intento_fallbacks = False

        if not results:
            await update.message.reply_text(f"❌ No se encontraron juegos para: <b>{html.escape(raw_query)}</b>", parse_mode="HTML")
            return

        context.user_data[f'steam_{chat_id}_results'] = results
        context.user_data[f'steam_{chat_id}_query'] = raw_query
        context.user_data[f'steam_{chat_id}_page'] = 0

        # Formatear el texto de cabecera de forma clara
        texto_busqueda = f"<b>{html.escape(raw_query)}</b>"
        if intento_fallbacks:
            texto_busqueda += f" <i>(Filtro inteligente: {html.escape(termino_exitoso)})</i>"
        elif nombre_limpio != raw_query and termino_exitoso == nombre_limpio:
            texto_busqueda += f" <i>(Procesado como: {html.escape(nombre_limpio)})</i>"

        await update.message.reply_text(
            f"🎮 Resultados para: {texto_busqueda}\n\nElige un juego:",
            reply_markup=build_steam_keyboard(results, page=0),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"❌ Error en búsqueda de Steam: {e}")
        await update.message.reply_text(f"❌ Error en la búsqueda: {str(e)}")


async def steam_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        chat_id = update.effective_chat.id
        
        if query.data.startswith("steampage_"):
            page = int(query.data.split("_")[1])
            steam_results = context.user_data.get(f'steam_{chat_id}_results', [])
            if not steam_results:
                await query.edit_message_text("❌ No hay resultados para paginar.")
                return

            context.user_data[f'steam_{chat_id}_page'] = page
            await query.edit_message_reply_markup(reply_markup=build_steam_keyboard(steam_results, page=page))
            return

        if query.data.startswith("steamgame_"):
            appid = query.data.replace("steamgame_", "")
            await query.edit_message_text("⏳ Obteniendo información del juego...")

            post = build_steam_game_post(appid)
            if not post:
                await query.edit_message_text("❌ No se pudo obtener la información del juego.")
                return

            caption = format_post_telegram(post)
            if not caption:
                await query.edit_message_text("❌ Error al formatear la información del juego.")
                return

            image_url = None
            try:
                details_url = f"https://store.steampowered.com/api/appdetails?appids={appid}&l=spanish"
                response = requests.get(details_url, timeout=10)
                app_data = response.json().get(str(appid), {}).get('data', {})
                image_url = app_data.get('header_image')
            except Exception:
                pass

            if image_url:
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=image_url, caption=caption, parse_mode="HTML")
            else:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=caption, parse_mode="HTML")

            await query.delete_message()
    except Exception as e:
        logger.error(f"❌ Error en steam_button: {e}", exc_info=True)
        try:
            await query.edit_message_text(f"❌ Error: {str(e)[:100]}")
        except Exception:
            pass


def register_game_handlers(application):
    """Registra los handlers del módulo."""
    steam_telegraph_service.init_client()
    application.add_handler(CommandHandler(["game", "g"], buscarjuego))
    application.add_handler(CallbackQueryHandler(steam_button, pattern="^(steamgame_|steampage_)"))