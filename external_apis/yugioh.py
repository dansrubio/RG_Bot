"""
Cliente para la API pública de YGOPRODeck.
Documentación: https://ygoprodeck.com/api-guide/
Sin autenticación — límite: 20 req/s.
"""

import urllib.parse
import aiohttp

# ── Endpoints ─────────────────────────────────────────────────────────────────
_URL_API    = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
_URL_RANDOM = "https://db.ygoprodeck.com/api/v7/randomcard.php"

# ── Límites de resultados ─────────────────────────────────────────────────────
MAX_RESULTADOS           = 90  # Búsqueda por nombre (10 páginas de 9)
MAX_RESULTADOS_COLECCION = 90  # Arquetipo / set   (10 páginas de 9)

# ── Tablas de traducción ──────────────────────────────────────────────────────
_TIPOS = {
    "Effect Monster":           "Monstruo de Efecto",
    "Normal Monster":           "Monstruo Normal",
    "Fusion Monster":           "Monstruo de Fusión",
    "Ritual Monster":           "Monstruo de Ritual",
    "Synchro Monster":          "Monstruo Sincro",
    "XYZ Monster":              "Monstruo Xyz",
    "Link Monster":             "Monstruo Link",
    "Pendulum Effect Monster":  "Monstruo de Péndulo (Efecto)",
    "Pendulum Normal Monster":  "Monstruo de Péndulo (Normal)",
    "Spell Card":               "Carta Mágica",
    "Trap Card":                "Carta Trampa",
    "Token":                    "Ficha",
    "Skill Card":               "Carta de Habilidad",
}

_ATRIBUTOS = {
    "DARK":   "OSCURIDAD",
    "LIGHT":  "LUZ",
    "FIRE":   "FUEGO",
    "WATER":  "AGUA",
    "EARTH":  "TIERRA",
    "WIND":   "VIENTO",
    "DIVINE": "DIVINO",
}

_BANLIST = {
    "Banned":       "🚫 Prohibida",
    "Limited":      "1️⃣ Limitada (1 copia)",
    "Semi-Limited": "2️⃣ Semi-Limitada (2 copias)",
}


# ── Capa de transporte ────────────────────────────────────────────────────────

async def _get_json(url: str, params: dict | None = None):
    """GET genérico — devuelve el JSON crudo (dict o list), o None si falla."""
    full_url = f"{url}?{urllib.parse.urlencode(params)}" if params else url
    async with aiohttp.ClientSession() as sesion:
        async with sesion.get(full_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return None
            return await resp.json()


def _extraer_lista(datos) -> list[dict]:
    """Extrae la lista 'data' de la respuesta estándar, o devuelve []."""
    if isinstance(datos, dict):
        return datos.get("data") or []
    if isinstance(datos, list):
        return datos
    return []


def _resumir_cartas(cartas: list[dict]) -> list[dict]:
    """Reduce cada carta a {id, name, type} para el panel de selección."""
    return [{"id": c["id"], "name": c["name"], "type": c.get("type", "")} for c in cartas]


# ── Consultas a la API ────────────────────────────────────────────────────────

async def buscar_cartas(nombre: str) -> list[dict]:
    """Búsqueda fuzzy por nombre — devuelve lista resumida para el panel."""
    datos = await _get_json(_URL_API, {"fname": nombre, "num": MAX_RESULTADOS, "offset": 0})
    return _resumir_cartas(_extraer_lista(datos))


async def buscar_carta_por_id(card_id: int) -> dict | None:
    """Devuelve la carta completa por su id, o None si no existe."""
    datos = await _get_json(_URL_API, {"id": card_id})
    cartas = _extraer_lista(datos)
    return cartas[0] if cartas else None


async def buscar_carta_exacta(nombre: str) -> dict | None:
    """Búsqueda por nombre exacto (sin fuzzy) — útil para /precio."""
    datos = await _get_json(_URL_API, {"name": nombre})
    cartas = _extraer_lista(datos)
    return cartas[0] if cartas else None


async def obtener_carta_aleatoria() -> dict | None:
    """Devuelve una carta aleatoria completa desde el endpoint dedicado."""
    datos = await _get_json(_URL_RANDOM)
    return datos if isinstance(datos, dict) and "id" in datos else None  # responde sin wrapper "data"


async def buscar_por_arquetipo(arquetipo: str) -> list[dict]:
    """Devuelve lista resumida de cartas que pertenecen al arquetipo dado."""
    datos = await _get_json(
        _URL_API,
        {"archetype": arquetipo, "num": MAX_RESULTADOS_COLECCION, "offset": 0},
    )
    return _resumir_cartas(_extraer_lista(datos))


async def buscar_por_set(nombre_set: str) -> list[dict]:
    """Devuelve lista resumida de cartas de una expansión/set específico."""
    datos = await _get_json(
        _URL_API,
        {"cardset": nombre_set, "num": MAX_RESULTADOS_COLECCION, "offset": 0},
    )
    return _resumir_cartas(_extraer_lista(datos))


# ── Formateo HTML para Telegram ───────────────────────────────────────────────

def formatear_carta(carta: dict, max_desc: int = 900) -> str:
    """
    Construye el texto HTML de la carta para enviarlo como caption.
    max_desc: límite de chars para la descripción (caption de Telegram = 1024 total).
    """
    nombre    = carta.get("name", "???")
    tipo_raw  = carta.get("type", "")
    tipo      = _TIPOS.get(tipo_raw, tipo_raw)
    raza      = carta.get("race", "")
    arquetipo = carta.get("archetype", "")
    desc      = carta.get("desc", "").strip()

    es_monstruo = "Monster" in tipo_raw
    es_link     = "Link"    in tipo_raw
    es_xyz      = "XYZ"     in tipo_raw.upper()

    lineas = [f"<b>{nombre}</b>", "", f"📌 <b>Tipo:</b> {tipo}"]

    if es_monstruo:
        atributo = _ATRIBUTOS.get(carta.get("attribute", ""), carta.get("attribute", ""))
        lineas.append(f"🌀 <b>Atributo:</b> {atributo}")

        if es_link:
            lineas.append(f"🔗 <b>Link Rating:</b> {carta.get('linkval', '?')}")
        elif es_xyz:
            lineas.append(f"🔲 <b>Rango:</b> {carta.get('level', '?')}")
        else:
            lineas.append(f"⭐ <b>Nivel:</b> {carta.get('level', '?')}")

        if raza:
            lineas.append(f"🐉 <b>Raza:</b> {raza}")

        atk  = carta.get("atk", "?")
        def_ = carta.get("def", "?") if not es_link else "—"
        lineas.append(f"⚔️ <b>ATK:</b> {atk}  🛡 <b>DEF:</b> {def_}")

    if arquetipo:
        lineas.append(f"🏛 <b>Arquetipo:</b> {arquetipo}")

    banlist   = carta.get("banlist_info", {})
    estado_tcg = banlist.get("ban_tcg", "")
    if estado_tcg in _BANLIST:
        lineas.append(f"⚠️ <b>Restricción TCG:</b> {_BANLIST[estado_tcg]}")

    if desc:
        desc_mostrar = desc if len(desc) <= max_desc else desc[:max_desc].rstrip() + "…"
        lineas.append(f"\n📖 <b>Descripción:</b>\n<blockquote>{desc_mostrar}</blockquote>")

    return "\n".join(lineas)


def formatear_precios(carta: dict) -> str:
    """Construye el bloque HTML con los precios de mercado de la carta."""
    nombre   = carta.get("name", "???")
    tipo_raw = carta.get("type", "")
    tipo     = _TIPOS.get(tipo_raw, tipo_raw)
    precios  = carta.get("card_prices", [{}])[0]

    tcg    = precios.get("tcgplayer_price",   "N/D")
    mkm    = precios.get("cardmarket_price",  "N/D")
    amazon = precios.get("amazon_price",      "N/D")
    cool   = precios.get("coolstuffinc_price","N/D")

    lineas = [
        f"<b>{nombre}</b>",
        "",
        f"📌 <b>Tipo:</b> {tipo}",
        "",
        "💰 <b>Precios de mercado:</b>",
        f"  • TCGPlayer:    <code>${tcg}</code>",
        f"  • CardMarket:   <code>€{mkm}</code>",
        f"  • Amazon:       <code>${amazon}</code>",
        f"  • CoolStuffInc: <code>${cool}</code>",
    ]
    return "\n".join(lineas)


def obtener_imagen_url(carta: dict) -> str | None:
    """Devuelve la URL de la imagen principal de la carta."""
    imagenes = carta.get("card_images", [])
    return imagenes[0].get("image_url") if imagenes else None