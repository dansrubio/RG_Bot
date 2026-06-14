"""
Agrega todas las fuentes y las ejecuta en paralelo.
Importa desde epic.py, gog.py y steam.py.
"""

import asyncio
import logging
import aiohttp

from . import epic, gog

from . import steam

logger = logging.getLogger(__name__)


async def obtener_juegos_gratis() -> list[dict]:
    """Consulta Epic, GOG y Steam en paralelo y devuelve todos los juegos gratis"""
    async with aiohttp.ClientSession() as session:
        resultados = await asyncio.gather(
            epic.fetch(session),
            gog.fetch(session),
            steam.fetch(session),
            return_exceptions=True,
        )

    juegos = []
    nombres = ["Epic", "GOG", "Steam"]
    for nombre, r in zip(nombres, resultados):
        if isinstance(r, list):
            juegos.extend(r)
        else:
            logger.error(f"[{nombre}] Excepción no capturada: {r}")

    return juegos
