"""
Fuente: GOG
Usa GamerPower API para detectar giveaways activos en GOG.
"""

import logging
from datetime import datetime
import aiohttp

logger = logging.getLogger(__name__)

URL = "https://www.gamerpower.com/api/giveaways?platform=gog&type=game"


def _formatear_fecha(texto: str) -> str:
    """Convierte 'YYYY-MM-DD HH:MM:SS' o 'N/A' a DD/MM/YYYY; retorna '' si falla"""
    if not texto or texto.strip().upper() in ("N/A", ""):
        return ""
    try:
        return datetime.strptime(texto.strip()[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return ""


async def fetch(session: aiohttp.ClientSession) -> list[dict]:
    """Retorna giveaways activos de GOG via GamerPower"""
    try:
        async with session.get(URL, timeout=aiohttp.ClientTimeout(total=12)) as r:
            r.raise_for_status()
            data = await r.json(content_type=None)
    except Exception as e:
        logger.error(f"[GOG] Error en request: {e}")
        return []

    if not isinstance(data, list):
        return []

    juegos = []
    for item in data:
        if item.get("status", "").lower() != "active":
            continue
        juegos.append({
            "id":                f"gog_{item.get('id', '')}",
            "titulo":            item.get("title", "Sin titulo"),
            "descripcion":       item.get("description", ""),
            "url":               item.get("open_giveaway", item.get("gamerpower_url", "")),
            "imagen":            item.get("image", item.get("thumbnail", "")),
            "fuente":            "GOG",
            "valor":             item.get("worth", ""),
            "fecha_lanzamiento": _formatear_fecha(item.get("published_date", "")),
            "fecha_fin_promo":   _formatear_fecha(item.get("end_date", "")),
        })

    return juegos