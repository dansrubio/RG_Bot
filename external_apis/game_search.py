import logging
import httpx
import asyncio
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

# Importamos la función de validación desde tu config.py
from config import is_staff 

logger = logging.getLogger(__name__)

SITIOS_BUSQUEDA = {
    "PiviGames": "https://pivigames.blog/?s={}",
    "FitGirl Repacks": "https://fitgirl-repacks.site/?s={}",
    "GameDrive": "https://gamedrive.org/?s={}"
}

# Caché en memoria para la paginación { "query": [lista_de_resultados_formateados] }
CACHE_BUSQUEDAS = {}
RESULTADOS_POR_PAGINA = 5

async def buscar_en_sitios_web(query: str) -> list:
    """Realiza la búsqueda y devuelve una lista de resultados combinados."""
    query_words = [w.lower() for w in query.split() if len(w) > 2]
    if not query_words:
        query_words = [query.lower()]

    resultados_totales = []

    async def _buscar(site_name, base_url):
        url = base_url.format(quote_plus(query))
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            async with httpx.AsyncClient(follow_redirects=True, http2=True) as client:
                response = await client.get(url, headers=headers, timeout=10.0)
                soup = BeautifulSoup(response.content, "html.parser")
                
                enlaces = soup.select("main h2 a, #primary h2 a, h2 a, h3 a, .entry-title a, .post-title a, article a")
                for a in enlaces:
                    titulo = a.get_text(strip=True)
                    link = a.get("href")
                    if not titulo or not link: continue
                    
                    t_lower, l_lower = titulo.lower(), link.lower()
                    if any(x in t_lower for x in ["upcoming repacks", "page", "lossless repack", "scene release"]): continue
                    if "/category/" in l_lower or "/tag/" in l_lower or titulo.isnumeric(): continue
                    if not any(word in t_lower for word in query_words): continue
                    
                    resultados_totales.append(f"🔹 <b>{site_name}</b>\n  ▪️ <a href='{link}'>{titulo}</a>")
        except Exception as e:
            logger.warning(f"Error al escrapear {site_name}: {e}")

    await asyncio.gather(*[_buscar(nombre, url) for nombre, url in SITIOS_BUSQUEDA.items()])
    return list(dict.fromkeys(resultados_totales)) # Elimina duplicados manteniendo el orden

def construir_mensaje_paginado(query: str, pagina: int) -> tuple[str, InlineKeyboardMarkup]:
    resultados = CACHE_BUSQUEDAS.get(query, [])
    total_paginas = max(1, (len(resultados) + RESULTADOS_POR_PAGINA - 1) // RESULTADOS_POR_PAGINA)
    
    if not resultados:
        return f"🎮 <b>BÚSQUEDA:</b> <i>{query}</i>\n\n❌ <i>No se encontraron resultados en las webs externas.</i>", None

    inicio = pagina * RESULTADOS_POR_PAGINA
    fin = inicio + RESULTADOS_POR_PAGINA
    bloque = resultados[inicio:fin]

    texto = f"🎮 <b>RESULTADOS PARA:</b> <i>{query}</i>\n"
    texto += f"📑 <b>Página {pagina + 1} de {total_paginas}</b>\n{'━'*30}\n\n"
    texto += "\n\n".join(bloque)

    botones = []
    nav_row = []
    if pagina > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"gspage:{query}:{pagina-1}"))
    if pagina < total_paginas - 1:
        nav_row.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"gspage:{query}:{pagina+1}"))
    
    if nav_row: botones.append(nav_row)
    botones.append([InlineKeyboardButton("🗑 Cerrar Búsqueda", callback_data="gsclose")])
    
    return texto, InlineKeyboardMarkup(botones)

async def comando_busqueda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manejador principal del comando /busqueda"""
    user_id = update.effective_user.id
    if not is_staff(user_id):
        return await update.effective_message.reply_text("⛔ <b>Acceso denegado.</b>", parse_mode="HTML")

    if not context.args:
        return await update.effective_message.reply_text("❌ <b>Falta el nombre del juego.</b>\nUso: <code>/busqueda [juego]</code>", parse_mode="HTML")

    query = " ".join(context.args)
    msg_estado = await update.effective_message.reply_text("🔍 <i>Buscando en la web, por favor espera...</i>", parse_mode="HTML")

    resultados = await buscar_en_sitios_web(query)
    CACHE_BUSQUEDAS[query] = resultados

    texto, teclado = construir_mensaje_paginado(query, 0)
    await msg_estado.edit_text(text=texto, parse_mode="HTML", reply_markup=teclado, disable_web_page_preview=True)

async def manejar_paginacion_busqueda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manejador para los botones de paginación y cierre"""
    query_cb = update.callback_query
    await query_cb.answer()
    
    if query_cb.data == "gsclose":
        return await query_cb.message.delete()

    # Formato esperado del callback_data: gspage:query_text:numero_pagina
    _, query, pagina_str = query_cb.data.split(":")
    pagina = int(pagina_str)
    
    texto, teclado = construir_mensaje_paginado(query, pagina)
    try:
        await query_cb.edit_message_text(text=texto, parse_mode="HTML", reply_markup=teclado, disable_web_page_preview=True)
    except Exception:
        pass # Ignorar errores si el mensaje no cambia

def register_search_handler(app: Application):
    """Registra el manejador en la aplicación principal."""
    app.add_handler(CommandHandler("busqueda", comando_busqueda))
    app.add_handler(CallbackQueryHandler(manejar_paginacion_busqueda, pattern="^gs(page|close)"))