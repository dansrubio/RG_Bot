"""
Módulo Unificado de Búsqueda de Videojuegos Multiplataforma (PS4, PC, Nintendo Switch y Genérico) usando la API de IGDB.
Mantiene el formato estructurado con Géneros al inicio y enlaces multimedia correspondientes.
"""

import html
import logging
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from config import is_staff, IGDB_CLIENT_ID, IGDB_CLIENT_SECRET
from external_apis.services.igdb_telegraph_service import igdb_telegraph_service

logger = logging.getLogger(__name__)

_IGDB_ACCESS_TOKEN = None

PLAYSTATION4_ID = 48
PC_ID = 6
NINTENDO_SWITCH_ID = 130

PLATFORMS_CONFIG = {
    'ps4': {'id': PLAYSTATION4_ID, 'tag': 'PS4', 'emoji': '🎮'},
    'pc': {'id': PC_ID, 'tag': 'PC', 'emoji': '🖥️'},
    'switch': {'id': NINTENDO_SWITCH_ID, 'tag': 'Nintendo Switch', 'emoji': '🕹️'},
    'juego': {'id': None, 'tag': '', 'emoji': '👾'}
}

def get_igdb_token():
    global _IGDB_ACCESS_TOKEN
    if _IGDB_ACCESS_TOKEN:
        return _IGDB_ACCESS_TOKEN
    if not IGDB_CLIENT_ID or not IGDB_CLIENT_SECRET:
        return None
    try:
        url = "https://id.twitch.tv/oauth2/token"
        params = {"client_id": IGDB_CLIENT_ID, "client_secret": IGDB_CLIENT_SECRET, "grant_type": "client_credentials"}
        response = requests.post(url, params=params, timeout=10)
        response.raise_for_status()
        _IGDB_ACCESS_TOKEN = response.json().get("access_token")
        return _IGDB_ACCESS_TOKEN
    except Exception as e:
        logger.error(f"❌ Error al renovar token en IGDB: {e}")
        return None

def truncate_text(text, max_length=450):
    if not text: return ""
    if len(text) > max_length:
        return text[:max_length].rsplit(' ', 1)[0] + "..."
    return text

def build_igdb_keyboard(results, platform_prefix, page=0):
    per_page = 9
    start, end = page * per_page, (page * per_page) + per_page
    buttons = []
    for r in results[start:end]:
        name = r.get("name", "Sin título")
        btn_text = name[:30] + "..." if len(name) > 30 else name
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"{platform_prefix}game_{r['id']}")])
    nav_buttons = []
    if start > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"{platform_prefix}page_{page - 1}"))
    if end < len(results):
        nav_buttons.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"{platform_prefix}page_{page + 1}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    return InlineKeyboardMarkup(buttons)

async def ejecutar_busqueda_plataforma(update: Update, context: ContextTypes.DEFAULT_TYPE, platform_key: str):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    cfg = PLATFORMS_CONFIG[platform_key]

    if not is_staff(user_id):
        await update.message.reply_text("🚫 No tienes permiso para usar este comando.")
        return

    query = " ".join(context.args).strip()
    if not query:
        await update.message.reply_text(f"❌ Escribe el nombre del juego.\n\nEjemplo: <code>/{platform_key} The Witcher</code>", parse_mode="HTML")
        return

    token = get_igdb_token()
    if not token:
        await update.message.reply_text("❌ Error de autenticación con la API de IGDB.")
        return

    try:
        url = "https://api.igdb.com/v4/games"
        headers = {"Client-ID": IGDB_CLIENT_ID, "Authorization": f"Bearer {token}"}
        
        if cfg["id"]:
            body = f'search "{query}"; fields name, id; where platforms = ({cfg["id"]}); limit 20;'
            msg_tag = f" en <b>{cfg['tag']}</b>"
        else:
            body = f'search "{query}"; fields name, id; limit 20;'
            msg_tag = ""
        
        response = requests.post(url, headers=headers, data=body, timeout=10)
        response.raise_for_status()
        results = response.json()

        if not results:
            await update.message.reply_text(f"❌ No hay resultados{msg_tag} para: <b>{html.escape(query)}</b>", parse_mode="HTML")
            return

        context.user_data[f'{platform_key}_{chat_id}_results'] = results
        context.user_data[f'{platform_key}_{chat_id}_page'] = 0

        await update.message.reply_text(
            f"{cfg['emoji']} Resultados{msg_tag} para: <b>{html.escape(query)}</b>\n\nElige un título:",
            reply_markup=build_igdb_keyboard(results, platform_key, page=0),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error {platform_key}: {e}")
        await update.message.reply_text(f"❌ Error en la búsqueda de IGDB: {str(e)}")

async def buscar_ps4(update: Update, context: ContextTypes.DEFAULT_TYPE): await ejecutar_busqueda_plataforma(update, context, 'ps4')
async def buscar_pc(update: Update, context: ContextTypes.DEFAULT_TYPE): await ejecutar_busqueda_plataforma(update, context, 'pc')
async def buscar_switch(update: Update, context: ContextTypes.DEFAULT_TYPE): await ejecutar_busqueda_plataforma(update, context, 'switch')
async def buscar_juego_general(update: Update, context: ContextTypes.DEFAULT_TYPE): await ejecutar_busqueda_plataforma(update, context, 'juego')

async def igdb_platform_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    callback_data = query.data

    platform_key = None
    for k in PLATFORMS_CONFIG.keys():
        if callback_data.startswith(f"{k}page_") or callback_data.startswith(f"{k}game_"):
            platform_key = k
            break

    if not platform_key: return

    cfg = PLATFORMS_CONFIG[platform_key]

    try:
        if callback_data.startswith(f"{platform_key}page_"):
            page = int(callback_data.split("_")[1])
            results = context.user_data.get(f'{platform_key}_{chat_id}_results', [])
            if not results: return
            context.user_data[f'{platform_key}_{chat_id}_page'] = page
            await query.edit_message_reply_markup(reply_markup=build_igdb_keyboard(results, platform_key, page=page))
            return

        if callback_data.startswith(f"{platform_key}game_"):
            game_id = callback_data.replace(f"{platform_key}game_", "")
            
            loading_tag = cfg['tag'] if cfg['tag'] else "varias plataformas"
            await query.edit_message_text(f"⏳ Procesando ficha de {loading_tag} desde IGDB...")

            token = get_igdb_token()
            url = "https://api.igdb.com/v4/games"
            headers = {"Client-ID": IGDB_CLIENT_ID, "Authorization": f"Bearer {token}"}
            
            body = (
                f"fields name, summary, first_release_date, cover.url, screenshots.url, "
                f"genres.name, involved_companies.company.name, involved_companies.developer, involved_companies.publisher, "
                f"aggregated_rating, url, videos.video_id, platforms.name; where id = {game_id};"
            )
            
            resp = requests.post(url, headers=headers, data=body, timeout=10)
            resp.raise_for_status()
            game_array = resp.json()
            if not game_array: return
            
            raw_data = game_array[0]

            plataformas_api = [p.get('name') for p in raw_data.get('platforms', []) if p.get('name')]
            plataformas_str = ", ".join(plataformas_api) if plataformas_api else "No especificadas"

            # El tag final se sigue construyendo para la inyección en Telegraph
            final_tag = cfg['tag'] if cfg['tag'] else plataformas_str

            devs, pubs = [], []
            for comp in raw_data.get('involved_companies', []):
                c_name = comp.get('company', {}).get('name', 'Desconocido')
                if comp.get('developer'): devs.append({'name': c_name})
                if comp.get('publisher'): pubs.append({'name': c_name})

            release_ts = raw_data.get('first_release_date')
            release_date = datetime.utcfromtimestamp(release_ts).strftime('%Y-%m-%d') if release_ts else 'No disponible'

            cover_url = raw_data.get('cover', {}).get('url', '')
            if cover_url: cover_url = "https:" + cover_url.replace("t_thumb", "t_cover_big")

            screenshots_list = []
            if raw_data.get('screenshots'):
                for shot in raw_data.get('screenshots')[:5]:
                    shot_url = shot.get('url', '')
                    if shot_url:
                        screenshots_list.append("https:" + shot_url.replace("t_thumb", "t_720p"))

            primer_screenshot = screenshots_list[0] if screenshots_list else ""

            trailer_url = None
            videos = raw_data.get('videos', [])
            if videos and isinstance(videos, list):
                video_id = videos[0].get('video_id')
                if video_id:
                    trailer_url = f"https://www.youtube.com/watch?v={video_id}"

            game_data = {
                'name': raw_data.get('name', 'Sin título'),
                'released': release_date,
                'genres': raw_data.get('genres', []),
                'metacritic': int(raw_data.get('aggregated_rating', 0)) if raw_data.get('aggregated_rating') else 'N/A',
                'description_raw': raw_data.get('summary', 'Sin descripción disponible.'),
                'background_image': cover_url or primer_screenshot,
                'background_image_additional': primer_screenshot if cover_url else "",
                'developers': devs,
                'publishers': pubs,
                'website': raw_data.get('url', '')
            }

            telegraph_url = igdb_telegraph_service.create_igdb_page(
                game_name=game_data['name'], 
                full_data=game_data, 
                plataforma_tag=final_tag,
                screenshots_urls=screenshots_list
            )

            genres_str = ", ".join([g.get('name') for g in game_data['genres']]) or "No definidos"
            desc_short = truncate_text(game_data['description_raw'])

            # Modificado: Se eliminó el "({cfg['tag']})" o "({final_tag})" para que solo muestre el nombre del juego
            lines = [
                f"<b>{html.escape(game_data['name'])}</b>",
                "",
                f"🎲 <b>Géneros:</b> {html.escape(genres_str)}",
                f"📅 <b>Lanzamiento:</b> {html.escape(release_date)}"
            ]
            
            if game_data['metacritic'] != 'N/A':
                lines.append(f"⭐ <b>Calificación:</b> {game_data['metacritic']}/100")
            
            dev_str = ", ".join([d['name'] for d in devs])
            if dev_str:
                lines.append(f"👨‍💻 <b>Desarrollador:</b> {html.escape(dev_str)}")

            lines.extend(["", "<b>Descripción:</b>"])
            lines.append(f"<blockquote>{html.escape(desc_short)}</blockquote>\n")

            links_line = []
            if trailer_url:
                links_line.append(f"<a href='{trailer_url}'>📺 Trailer</a>")
            if telegraph_url:
                links_line.append(f"<a href='{telegraph_url}'>📚 Información</a>")

            if links_line:
                lines.append(" | ".join(links_line))

            caption = "\n".join(lines)
            image_url = game_data['background_image']

            if image_url:
                await context.bot.send_photo(chat_id=chat_id, photo=image_url, caption=caption, parse_mode="HTML")
            else:
                await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode="HTML")

            await query.delete_message()
    except Exception as e:
        logger.error(f"❌ Error procesando callback en {platform_key}: {e}", exc_info=True)

def register_ps4_handlers(application):
    """Registra los comandos cruzados e interceptores de botones."""
    igdb_telegraph_service.init_client()
    application.add_handler(CommandHandler(["ps4", "gameps4"], buscar_ps4))
    application.add_handler(CommandHandler(["pc", "gamepc"], buscar_pc))
    application.add_handler(CommandHandler(["switch", "gameswitch"], buscar_switch))
    application.add_handler(CommandHandler("juego", buscar_juego_general))
    application.add_handler(CallbackQueryHandler(igdb_platform_button, pattern="^(ps4game_|ps4page_|pcgame_|pcpage_|switchgame_|switchpage_|juegogame_|juegopage_)"))