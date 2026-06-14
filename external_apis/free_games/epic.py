"""
Fuente: Epic Games Store
Usa la API publica de promociones de Epic.
"""

import logging
from datetime import datetime
import aiohttp

logger = logging.getLogger(__name__)

URL = (
    "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
    "?locale=es-ES&country=MX&allowCountries=MX"
)


def _formatear_fecha(iso: str) -> str:
    """Convierte fecha ISO 8601 a DD/MM/YYYY; retorna '' si falla"""
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except Exception:
        return ""


async def fetch(session: aiohttp.ClientSession) -> list[dict]:
    """Retorna juegos gratis actuales de Epic Games Store"""
    try:
        async with session.get(URL, timeout=aiohttp.ClientTimeout(total=12)) as r:
            r.raise_for_status()
            data = await r.json(content_type=None)
    except Exception as e:
        logger.error(f"[Epic] Error en request: {e}")
        return []

    juegos = []
    try:
        elementos = data["data"]["Catalog"]["searchStore"]["elements"]

        for item in elementos:
            promos = (item.get("promotions") or {}).get("promotionalOffers", [])
            if not promos:
                continue

            # Buscar oferta activa con 100% de descuento y extraer fecha de fin
            fecha_fin = ""
            es_gratis = False
            for grupo in promos:
                for oferta in grupo.get("promotionalOffers", []):
                    if oferta.get("discountSetting", {}).get("discountPercentage") == 0:
                        es_gratis = True
                        fecha_fin = _formatear_fecha(oferta.get("endDate", ""))
                        break
                if es_gratis:
                    break

            if not es_gratis:
                continue

            slug = item.get("productSlug") or item.get("urlSlug", "")
            imagen = next(
                (img["url"] for img in item.get("keyImages", [])
                 if img.get("type") in ("Thumbnail", "DieselStoreFrontWide", "OfferImageWide")),
                ""
            )

            # Fecha de lanzamiento del juego
            fecha_lanzamiento = _formatear_fecha(
                item.get("releaseDate") or item.get("effectiveDate", "")
            )

            juegos.append({
                "id":                item.get("id", ""),
                "titulo":            item.get("title", "Sin titulo"),
                "descripcion":       item.get("description", ""),
                "url":               f"https://store.epicgames.com/es-ES/p/{slug}" if slug
                                     else "https://store.epicgames.com/es-ES/free-games",
                "imagen":            imagen,
                "fuente":            "Epic Games",
                "valor":             "",  # Epic no expone precio original en este endpoint
                "fecha_lanzamiento": fecha_lanzamiento,
                "fecha_fin_promo":   fecha_fin,
            })

    except (KeyError, TypeError) as e:
        logger.error(f"[Epic] Error parseando respuesta: {e}")

    return juegos