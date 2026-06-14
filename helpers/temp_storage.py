"""
Sistema de almacenamiento temporal compartido para callback_data
"""

import secrets
import string
from typing import Any, Optional
from cachetools import TTLCache

# TTL de 1 hora (3600 segundos) para datos temporales
_temp_data_store = TTLCache(maxsize=10000, ttl=3600)


def generar_temp_key() -> str:
    """Genera una clave temporal corta y única de 8 caracteres"""
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))


def guardar_temp_data(data: Any, key: str = None) -> str:
    """Guarda datos temporales y retorna una clave corta"""
    if key is None:
        key = generar_temp_key()
        while key in _temp_data_store:
            key = generar_temp_key()

    _temp_data_store[key] = data
    return key


def obtener_temp_data(key: str, eliminar: bool = True) -> Optional[Any]:
    """Obtiene datos temporales del almacenamiento"""
    if eliminar:
        return _temp_data_store.pop(key, None)
    else:
        return _temp_data_store.get(key, None)
