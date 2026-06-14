"""
Capa de acceso a la PokeAPI.
Obtiene, combina y normaliza datos de pokemon, especie, cadena evolutiva,
movimientos, ítems y tipos.
"""

import httpx
import logging
import random

logger = logging.getLogger(__name__)

BASE_URL = "https://pokeapi.co/api/v2"

# Traducción de tipos al español con emojis
TIPOS_ES: dict[str, str] = {
    "normal":   "⚪ Normal",    "fire":     "🔥 Fuego",
    "water":    "💧 Agua",      "electric": "⚡ Eléctrico",
    "grass":    "🌿 Planta",    "ice":      "❄️ Hielo",
    "fighting": "🥊 Lucha",    "poison":   "☠️ Veneno",
    "ground":   "🌍 Tierra",   "flying":   "🌬️ Volador",
    "psychic":  "🔮 Psíquico", "bug":      "🐛 Bicho",
    "rock":     "🪨 Roca",      "ghost":    "👻 Fantasma",
    "dragon":   "🐉 Dragón",   "dark":     "🌑 Siniestro",
    "steel":    "⚙️ Acero",    "fairy":    "✨ Hada",
}

# Mapa inverso para aceptar nombres en español: "fuego" → "fire"
TIPOS_ES_A_EN: dict[str, str] = {
    "normal": "normal",   "fuego": "fire",       "agua": "water",
    "electrico": "electric", "eléctrico": "electric", "planta": "grass",
    "hielo": "ice",       "lucha": "fighting",   "veneno": "poison",
    "tierra": "ground",   "volador": "flying",   "psiquico": "psychic",
    "psíquico": "psychic","bicho": "bug",        "roca": "rock",
    "fantasma": "ghost",  "dragon": "dragon",    "dragón": "dragon",
    "siniestro": "dark",  "acero": "steel",      "hada": "fairy",
}

# Clases de daño de movimientos
CLASES_MOV_ES: dict[str, str] = {
    "physical": "⚔️ Físico",
    "special":  "💥 Especial",
    "status":   "🔄 Estado",
}

# Traducción de hábitats con emoji
HABITATS_ES: dict[str, str] = {
    "cave":          "🕳️ Cueva",
    "forest":        "🌲 Bosque",
    "grassland":     "🌾 Pradera",
    "mountain":      "⛰️ Montaña",
    "rare":          "🌟 Raro",
    "rough-terrain": "🪨 Terreno escarpado",
    "sea":           "🌊 Mar",
    "urban":         "🏙️ Urbano",
    "waters-edge":   "🏞️ Orilla del agua",
}

# Traducción de grupos huevo
GRUPOS_HUEVO_ES: dict[str, str] = {
    "monster":    "Monstruo",   "water1":     "Agua 1",
    "bug":        "Bicho",      "flying":     "Volador",
    "field":      "Campo",      "fairy":      "Hada",
    "grass":      "Planta",     "human-like": "Humanoide",
    "water3":     "Agua 3",     "mineral":    "Mineral",
    "amorphous":  "Amorfo",     "water2":     "Agua 2",
    "ditto":      "Ditto",      "dragon":     "Dragón",
    "no-eggs":    "Sin huevos",
}

# Traducción de métodos de encuentro con emoji
METODOS_ES: dict[str, str] = {
    "walk":          "🌿 Hierba",
    "old-rod":       "🎣 Caña vieja",
    "good-rod":      "🎣 Super caña",
    "super-rod":     "🎣 Mega caña",
    "surf":          "🏄 Surf",
    "rock-smash":    "🪨 Romperocas",
    "headbutt":      "🌳 Cabezazo",
    "gift":          "🎁 Regalo",
    "cave":          "🕳️ Cueva",
    "fishing":       "🎣 Pesca",
    "slot2-grass":   "🌿 Slot 2",
    "pokeradar":     "📡 Poké Radar",
}

# Etiquetas de estadísticas para el bloque de display
STATS_ES: dict[str, str] = {
    "hp":               "❤️ PS     ",
    "attack":           "⚔️ ATK    ",
    "defense":          "🛡️ DEF    ",
    "special-attack":   "💥 SP.ATK ",
    "special-defense":  "🔰 SP.DEF ",
    "speed":            "⚡️ SPEED  ",
}


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS INTERNOS
# ══════════════════════════════════════════════════════════════════════════════

def _extraer_genera(entradas: list[dict]) -> str:
    """Devuelve la categoría oficial del Pokémon en español; fallback al inglés"""
    for e in entradas:
        if e["language"]["name"] == "es":
            return e["genus"]
    for e in entradas:
        if e["language"]["name"] == "en":
            return e["genus"]
    return ""


def _limpiar_zona(nombre_area: str) -> str:
    """'pallet-town-area' → 'Pallet Town', elimina sufijos genéricos de área"""
    limpio = nombre_area.replace("-area", "").replace("-zone", "")
    return " ".join(p.capitalize() for p in limpio.split("-"))


def _formatear_nombre(nombre: str) -> str:
    """Convierte 'mr-mime' → 'Mr Mime', maneja guiones y capitaliza cada palabra"""
    return " ".join(p.capitalize() for p in nombre.replace("-", " ").split())


def _barra_stat(valor: int, maximo: int = 255, longitud: int = 10) -> str:
    """Genera una barra visual tipo '▰▰▰▰▰▱▱▱▱▱' escalada al máximo"""
    relleno = round(valor * longitud / maximo)
    return "▰" * relleno + "▱" * (longitud - relleno)


def _extraer_descripcion(entradas: list[dict]) -> str:
    """Busca descripción en español; si no existe, usa la primera en inglés"""
    for entrada in entradas:
        if entrada["language"]["name"] == "es":
            return entrada["flavor_text"].replace("\n", " ").replace("\f", " ")
    for entrada in entradas:
        if entrada["language"]["name"] == "en":
            return entrada["flavor_text"].replace("\n", " ").replace("\f", " ")
    return "Sin descripción disponible."


def _extraer_efecto(entradas: list[dict]) -> str:
    """
    Extrae el efecto corto desde effect_entries (movimientos e ítems).
    Prioriza español; si no hay, usa inglés. Prefiere short_effect sobre effect.
    """
    for entrada in entradas:
        if entrada["language"]["name"] == "es":
            return entrada.get("short_effect") or entrada.get("effect", "")
    for entrada in entradas:
        if entrada["language"]["name"] == "en":
            return entrada.get("short_effect") or entrada.get("effect", "")
    return "Sin descripción disponible."


def _recorrer_cadena(nodo: dict, padre: str | None = None) -> list[tuple[str, str | None]]:
    """
    Recorre recursivamente el árbol de evoluciones y devuelve:
    [(nombre_especie, nombre_padre), ...]
    Soporta ramas múltiples (Eevee, etc.)
    """
    resultado = [(nodo["species"]["name"], padre)]
    for siguiente in nodo.get("evolves_to", []):  # itera cada rama posible
        resultado.extend(_recorrer_cadena(siguiente, nodo["species"]["name"]))
    return resultado


def _obtener_evoluciones(cadena_raw: dict, nombre: str) -> tuple[str | None, list[str]]:
    """
    A partir del árbol crudo devuelve (preevolucion, [evoluciones_siguientes])
    para el Pokémon indicado.
    """
    nodos = _recorrer_cadena(cadena_raw["chain"])  # aplana todo el árbol
    anterior = None
    siguientes = []

    for especie, padre in nodos:
        if especie == nombre:
            anterior = padre  # nodo padre = preevolución directa
        if padre == nombre:
            siguientes.append(especie)  # hijos directos = evoluciones

    return anterior, siguientes


def _calcular_multiplicadores(relaciones_por_tipo: list[dict]) -> dict[str, float]:
    """
    Recibe la lista de damage_relations de cada tipo del Pokémon y
    devuelve {nombre_tipo_en: multiplicador_final} para los 18 tipos.
    Multiplica los factores cuando el Pokémon tiene dos tipos.
    """
    todos_los_tipos = list(TIPOS_ES.keys())  # 18 tipos como referencia base
    resultado: dict[str, float] = {t: 1.0 for t in todos_los_tipos}  # todos comienzan en ×1

    for relaciones in relaciones_por_tipo:
        for tipo in relaciones.get("double_damage_from", []):  # ×2 para este tipo
            nombre = tipo["name"]
            if nombre in resultado:
                resultado[nombre] *= 2.0

        for tipo in relaciones.get("half_damage_from", []):    # ×0.5 para este tipo
            nombre = tipo["name"]
            if nombre in resultado:
                resultado[nombre] *= 0.5

        for tipo in relaciones.get("no_damage_from", []):      # ×0 para este tipo
            nombre = tipo["name"]
            if nombre in resultado:
                resultado[nombre] *= 0.0

    return resultado


def _agrupar_por_multiplicador(multiplicadores: dict[str, float]) -> dict[float, list[str]]:
    """Agrupa los tipos por su multiplicador final, excluyendo los neutros (×1)"""
    grupos: dict[float, list[str]] = {}
    for tipo, mult in multiplicadores.items():
        if mult == 1.0:  # neutros no se muestran
            continue
        grupos.setdefault(mult, []).append(tipo)
    return grupos


async def _get(cliente: httpx.AsyncClient, url: str) -> dict | None:
    """Realiza una petición GET y devuelve JSON o None si hay error"""
    try:
        respuesta = await cliente.get(url, timeout=10)
        respuesta.raise_for_status()
        return respuesta.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None  # recurso no encontrado — error esperado
        logger.warning(f"HTTP error en {url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error inesperado al consultar {url}: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIONES PÚBLICAS — POKÉMON
# ══════════════════════════════════════════════════════════════════════════════

async def obtener_debilidades(tipos_raw: list[str]) -> dict | None:
    """
    Consulta /type/{nombre} para cada tipo y calcula:
    - defensiva: {multiplicador: [tipos que atacan al Pokémon]}
    - ofensiva:  [tipos a los que el Pokémon hace ×2] (unión de sus tipos)
    Retorna None si hay error de red.
    """
    async with httpx.AsyncClient() as cliente:
        relaciones_lista = []
        for tipo in tipos_raw:
            datos_tipo = await _get(cliente, f"{BASE_URL}/type/{tipo}")
            if datos_tipo is None:
                return None
            relaciones_lista.append(datos_tipo["damage_relations"])

    # ── Defensiva: multiplicadores cruzados ───────────────────────────────
    multiplicadores = _calcular_multiplicadores(relaciones_lista)
    grupos_raw      = _agrupar_por_multiplicador(multiplicadores)
    defensiva: dict[float, list[str]] = {
        mult: [TIPOS_ES.get(t, t.capitalize()) for t in tipos]
        for mult, tipos in grupos_raw.items()
    }

    # ── Ofensiva: unión de double_damage_to de cada tipo ──────────────────
    ofensiva_raw: set[str] = set()
    for relaciones in relaciones_lista:
        for tipo in relaciones.get("double_damage_to", []):  # tipos a los que hace ×2
            ofensiva_raw.add(tipo["name"])

    ofensiva = [TIPOS_ES.get(t, t.capitalize()) for t in sorted(ofensiva_raw)]

    return {"defensiva": defensiva, "ofensiva": ofensiva}


async def obtener_encuentros(nombre: str) -> list[dict] | None:
    """
    Consulta /pokemon/{nombre}/encounters y devuelve una lista normalizada de:
    [{"zona": str, "metodos": [str], "versiones": [str]}, ...]
    Limitado a 10 zonas para no saturar el mensaje.
    Retorna lista vacía si el Pokémon no aparece en la naturaleza (ej: legendarios).
    Retorna None solo si hay error de red.
    """
    async with httpx.AsyncClient() as cliente:
        raw = await _get(cliente, f"{BASE_URL}/pokemon/{nombre}/encounters")

    if raw is None:
        return None  # error de red real
    if not raw:
        return []    # lista vacía = no aparece en la naturaleza

    resultado = []
    for entrada in raw[:10]:  # limitar a 10 zonas
        zona = _limpiar_zona(entrada["location_area"]["name"])

        # Recopilar métodos únicos de todos los version_details
        metodos_raw = set()
        versiones   = []
        for vd in entrada.get("version_details", []):
            versiones.append(_formatear_nombre(vd["version"]["name"]))
            for enc in vd.get("encounter_details", []):
                metodos_raw.add(enc["method"]["name"])

        metodos = [METODOS_ES.get(m, _formatear_nombre(m)) for m in metodos_raw]

        resultado.append({
            "zona":      zona,
            "metodos":   metodos,
            "versiones": versiones,
        })

    return resultado


async def obtener_datos_completos(nombre: str) -> dict | None:
    """
    Punto de entrada principal del módulo.
    Combina datos de /pokemon, /pokemon-species y /evolution-chain
    y devuelve un dict normalizado listo para mostrar.

    Retorna None si el Pokémon no existe.
    """
    nombre = nombre.lower().strip()  # normalizar siempre antes de consultar

    async with httpx.AsyncClient() as cliente:
        # ── 1. Datos base del Pokémon ──────────────────────────────────────
        datos = await _get(cliente, f"{BASE_URL}/pokemon/{nombre}")
        if datos is None:
            return None

        # ── 2. Datos de especie (descripción + cadena evolutiva + extras) ────
        especie = await _get(cliente, f"{BASE_URL}/pokemon-species/{nombre}")
        descripcion  = "Sin descripción disponible."
        url_cadena   = None
        genera        = ""
        es_legendario = False
        es_mitico     = False
        habitat       = None
        grupos_huevo  = []
        mega_evoluciones: list[str] = []

        if especie:
            descripcion   = _extraer_descripcion(especie.get("flavor_text_entries", []))
            url_cadena    = especie.get("evolution_chain", {}).get("url")
            genera        = _extraer_genera(especie.get("genera", []))
            es_legendario = especie.get("is_legendary", False)
            es_mitico     = especie.get("is_mythical", False)

            hab = especie.get("habitat")  # puede ser None
            if hab:
                habitat = HABITATS_ES.get(hab["name"], _formatear_nombre(hab["name"]))

            grupos_huevo = [
                GRUPOS_HUEVO_ES.get(g["name"], _formatear_nombre(g["name"]))
                for g in especie.get("egg_groups", [])
            ]

            # Mega evoluciones: varieties cuyo nombre contiene "mega"
            mega_evoluciones = [
                v["pokemon"]["name"]
                for v in especie.get("varieties", [])
                if "mega" in v["pokemon"]["name"]
            ]

        # ── 3. Cadena evolutiva ────────────────────────────────────────────
        anterior, siguientes = None, []
        if url_cadena:
            cadena_raw = await _get(cliente, url_cadena)
            if cadena_raw:
                anterior, siguientes = _obtener_evoluciones(cadena_raw, nombre)

        # ── 4. Construir tipos con traducción ──────────────────────────────
        tipos_raw = [t["type"]["name"] for t in datos["types"]]  # nombres en inglés para la API
        tipos = [TIPOS_ES.get(t, t.capitalize()) for t in tipos_raw]  # versión display con emoji

        # ── 5. Habilidades (capitalizar, quitar guiones) ───────────────────
        habilidades = [
            _formatear_nombre(h["ability"]["name"])
            for h in datos["abilities"]
            if not h["is_hidden"]  # excluir habilidades ocultas del listado principal
        ]
        habilidades_ocultas = [
            _formatear_nombre(h["ability"]["name"])
            for h in datos["abilities"]
            if h["is_hidden"]
        ]

        # ── 6. Estadísticas base ───────────────────────────────────────────
        stats = {
            s["stat"]["name"]: s["base_stat"]  # solo el valor numérico
            for s in datos["stats"]
        }

        # ── 7. Imagen oficial (artwork de alta calidad) ────────────────────
        sprites = datos.get("sprites", {})
        imagen = (
            sprites.get("other", {})
            .get("official-artwork", {})
            .get("front_default")
            or sprites.get("front_default")  # fallback al sprite normal
        )

        return {
            "id":                   datos["id"],
            "nombre":               nombre,
            "nombre_display":       _formatear_nombre(nombre),
            "genera":               genera,           # "Pokémon Ratón"
            "es_legendario":        es_legendario,
            "es_mitico":            es_mitico,
            "habitat":              habitat,           # puede ser None
            "grupos_huevo":         grupos_huevo,      # lista, puede ser vacía
            "tipos":                tipos,
            "tipos_raw":            tipos_raw,
            "habilidades":          habilidades,
            "habilidades_ocultas":  habilidades_ocultas,
            "stats":                stats,
            "descripcion":          descripcion,
            "imagen":               imagen,
            "peso_kg":              datos["weight"] / 10,
            "altura_m":             datos["height"] / 10,
            "evolucion_anterior":   anterior,
            "evoluciones":          siguientes,
            "mega_evoluciones":     mega_evoluciones,  # lista de nombres como "charizard-mega-x"
        }


async def obtener_pokemon_aleatorio() -> dict | None:
    """Obtiene un Pokémon al azar entre los IDs 1-1025 (generaciones 1–9)"""
    id_aleatorio = str(random.randint(1, 1025))
    return await obtener_datos_completos(id_aleatorio)


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIONES PÚBLICAS — MOVIMIENTOS
# ══════════════════════════════════════════════════════════════════════════════

async def obtener_movimiento(nombre: str) -> dict | None:
    """
    Consulta /move/{nombre} y devuelve un dict normalizado con:
    tipo, clase, poder, precisión, PP y descripción.
    Retorna None si el movimiento no existe.
    """
    nombre = nombre.lower().strip().replace(" ", "-")  # "thunder bolt" → "thunder-bolt"

    async with httpx.AsyncClient() as cliente:
        datos = await _get(cliente, f"{BASE_URL}/move/{nombre}")

    if datos is None:
        return None

    tipo_raw  = datos["type"]["name"]
    clase_raw = datos["damage_class"]["name"]

    # Preferir flavor_text en español; si no hay, usar effect corto en inglés
    descripcion = _extraer_descripcion(datos.get("flavor_text_entries", []))
    if descripcion == "Sin descripción disponible.":
        descripcion = _extraer_efecto(datos.get("effect_entries", []))

    return {
        "nombre":         datos["name"],
        "nombre_display": _formatear_nombre(datos["name"]),
        "tipo":           TIPOS_ES.get(tipo_raw, tipo_raw.capitalize()),
        "clase":          CLASES_MOV_ES.get(clase_raw, clase_raw.capitalize()),
        "poder":          datos.get("power") or "—",     # None si es movimiento de estado
        "precision":      datos.get("accuracy") or "—",  # None en algunos movimientos
        "pp":             datos.get("pp") or "—",
        "descripcion":    descripcion,
    }


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIONES PÚBLICAS — ÍTEMS
# ══════════════════════════════════════════════════════════════════════════════

async def obtener_item(nombre: str) -> dict | None:
    """
    Consulta /item/{nombre} y devuelve un dict normalizado con:
    nombre en español, categoría, costo, efecto e imagen (sprite).
    Retorna None si el ítem no existe.
    """
    nombre = nombre.lower().strip().replace(" ", "-")  # "master ball" → "master-ball"

    async with httpx.AsyncClient() as cliente:
        datos = await _get(cliente, f"{BASE_URL}/item/{nombre}")

    if datos is None:
        return None

    # Nombre localizado en español
    nombre_es = ""
    for entry in datos.get("names", []):
        if entry["language"]["name"] == "es":
            nombre_es = entry["name"]
            break

    efecto = _extraer_efecto(datos.get("effect_entries", []))

    return {
        "nombre":         datos["name"],
        "nombre_display": nombre_es or _formatear_nombre(datos["name"]),
        "categoria":      _formatear_nombre(datos.get("category", {}).get("name", "—")),
        "costo":          datos.get("cost", 0),
        "efecto":         efecto,
        "imagen":         datos.get("sprites", {}).get("default"),  # sprite PNG pequeño
    }


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIONES PÚBLICAS — TIPOS
# ══════════════════════════════════════════════════════════════════════════════

async def obtener_tipo(nombre: str) -> dict | None:
    """
    Consulta /type/{nombre} y devuelve la tabla completa de relaciones:
    - Atacando: tipos a los que hace ×2, ×½ o ×0
    - Defendiendo: tipos que le hacen ×2, ×½ o ×0
    Acepta nombres en inglés y en español (fuego, fire, etc.)
    Retorna None si el tipo no existe.
    """
    nombre_lower = nombre.lower().strip()
    nombre_en    = TIPOS_ES_A_EN.get(nombre_lower, nombre_lower)  # español → inglés si aplica

    async with httpx.AsyncClient() as cliente:
        datos = await _get(cliente, f"{BASE_URL}/type/{nombre_en}")

    if datos is None:
        return None

    rel = datos["damage_relations"]

    def _traducir(lista: list[dict]) -> list[str]:  # convierte lista de dicts a nombres con emoji
        return [TIPOS_ES.get(t["name"], _formatear_nombre(t["name"])) for t in lista]

    return {
        "nombre":        nombre_en,
        "nombre_display": TIPOS_ES.get(nombre_en, _formatear_nombre(nombre_en)),
        "doble_daño_a":  _traducir(rel.get("double_damage_to",   [])),  # ×2 atacando
        "mitad_daño_a":  _traducir(rel.get("half_damage_to",     [])),  # ×½ atacando
        "sin_daño_a":    _traducir(rel.get("no_damage_to",       [])),  # ×0 atacando
        "doble_daño_de": _traducir(rel.get("double_damage_from", [])),  # ×2 recibiendo
        "mitad_daño_de": _traducir(rel.get("half_damage_from",   [])),  # ×½ recibiendo
        "sin_daño_de":   _traducir(rel.get("no_damage_from",     [])),  # ×0 recibiendo
    }