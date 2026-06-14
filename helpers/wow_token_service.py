"""
Servicio WoW Token simplificado
Solo obtiene datos actuales de la API sin almacenamiento
"""

import aiohttp
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict

logger = logging.getLogger(__name__)


class WoWTokenService:
    """Servicio simplificado para obtener datos actuales del WoW Token"""

    # Ruta de imagen opcional
    IMAGE_PATH = Path("data/wow_token_image.jpg")

    # Configuración de regiones
    REGIONES = {
        "us": {"emoji": "🇺🇸", "nombre": "Estados Unidos"},
        "eu": {"emoji": "🇪🇺", "nombre": "Europa"},
    }

    def __init__(self):
        """Inicializa el servicio"""
        pass

    def get_image_path(self) -> Optional[str]:
        """Retorna la ruta de la imagen si existe"""
        return str(self.IMAGE_PATH) if self.IMAGE_PATH.exists() else None

    async def get_token_message(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Obtiene mensaje con precios actuales del WoW Token
        Returns:
            Tuple[mensaje, ruta_imagen]: Mensaje formateado y ruta de imagen
        """
        try:
            # Obtener datos de las APIs
            async with aiohttp.ClientSession() as session:
                retail_data = await self._fetch_data(session, "retail")
                classic_data = await self._fetch_data(session, "classic")

                if not retail_data or not classic_data:
                    logger.warning("No se pudieron obtener datos de las APIs")
                    return None, None

                # Construir mensaje
                mensaje = "<b>💰 Precios actuales del Token en World of Warcraft:</b>\n\n"

                # Procesar cada región
                for region in self.REGIONES.keys():
                    precios = self._extract_region_prices(region, retail_data, classic_data)
                    texto_region = self._format_region(region, precios)
                    mensaje += texto_region + "\n"

                # Agregar información adicional
                mensaje += "\n<i>🔄 Datos obtenidos en tiempo real</i>"

                return mensaje.strip(), self.get_image_path()

        except Exception as e:
            logger.error(f"❌ Error obteniendo precios del token: {e}")
            return None, None

    async def _fetch_data(self, session: aiohttp.ClientSession, game_type: str) -> Optional[Dict]:
        """Obtiene datos de la API externa"""
        url = f"https://data.wowtoken.app/v2/current/{game_type}.json"
        try:
            async with session.get(url, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()

                    # Validar estructura de datos
                    if not isinstance(data, dict):
                        logger.error(f"❌ Datos inválidos de {game_type}: no es dict")
                        return None

                    return data
                else:
                    logger.error(f"❌ Error HTTP {response.status} para {game_type}")
                    return None

        except aiohttp.ClientTimeout:
            logger.error(f"⏰ Timeout consultando {game_type} API")
            return None
        except Exception as e:
            logger.error(f"❌ Error inesperado obteniendo datos {game_type}: {e}")
            return None

    def _extract_region_prices(self, region: str, retail_data: Dict, classic_data: Dict) -> Dict[str, int]:
        """Extrae precios de una región específica con validaciones"""
        retail_prices = retail_data.get(region, [])
        classic_prices = classic_data.get(region, [])

        retail_price = 0
        classic_price = 0

        # Validar y extraer precio retail
        if isinstance(retail_prices, list) and len(retail_prices) >= 2:
            try:
                retail_price = int(float(retail_prices[1]))
                if retail_price < 0:
                    retail_price = 0
            except (ValueError, TypeError, IndexError):
                logger.warning(f"⚠️ Precio retail inválido para {region}: {retail_prices}")

        # Validar y extraer precio classic
        if isinstance(classic_prices, list) and len(classic_prices) >= 2:
            try:
                classic_price = int(float(classic_prices[1]))
                if classic_price < 0:
                    classic_price = 0
            except (ValueError, TypeError, IndexError):
                logger.warning(f"⚠️ Precio classic inválido para {region}: {classic_prices}")

        return {
            f"{region}_retail": retail_price,
            f"{region}_classic": classic_price,
        }

    def _format_region(self, region: str, precios: Dict[str, int]) -> str:
        """Formatea región con precios actuales"""
        info = self.REGIONES[region]
        emoji_bandera = info["emoji"]
        nombre = info["nombre"]

        retail_key = f"{region}_retail"
        classic_key = f"{region}_classic"

        retail_price = precios.get(retail_key, 0)
        classic_price = precios.get(classic_key, 0)

        # Formatear precios con disponibilidad
        retail_text = f"{retail_price:,} oro" if retail_price > 0 else "No disponible"
        classic_text = f"{classic_price:,} oro" if classic_price > 0 else "No disponible"

        return (
            f"{emoji_bandera} <b>{nombre}</b> ({region.upper()}):\n"
            f"🔹 <b>Retail:</b> {retail_text}\n"
            f"🔸 <b>Classic:</b> {classic_text}\n"
        )