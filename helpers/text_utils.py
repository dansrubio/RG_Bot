"""
Utilidades para procesamiento de texto
Funciones compartidas para nombres de elementos y botones
"""

import re
import logging

logger = logging.getLogger(__name__)


def extraer_primera_linea(texto: str) -> str:
    """Extrae la primera línea de un texto sin modificaciones"""
    if not texto:
        return ""
    return texto.strip().split("\n")[0].strip()


def limpiar_para_boton(texto: str, max_caracteres: int = 45) -> str:
    """
    Limpia texto para nombre de botón cortando en el último espacio

    Args:
        texto: Texto a procesar
        max_caracteres: Límite de caracteres (por defecto 45)

    Returns:
        Texto cortado en el último espacio si excede el límite
    """
    primera_linea = extraer_primera_linea(texto)

    if not primera_linea:
        return "Ver más"

    if len(primera_linea) <= max_caracteres:
        return primera_linea

    texto_cortado = primera_linea[:max_caracteres] # Cortar en el límite
    ultimo_espacio = texto_cortado.rfind(' ') # Buscar el último espacio

    if ultimo_espacio > 0: # Si hay un espacio, cortar ahí
        return texto_cortado[:ultimo_espacio].strip()
    else: # Si no hay espacios, cortar directamente
        return texto_cortado.strip()


def limpiar_para_elemento(texto: str) -> str:
    """
    Extrae la primera línea SIN modificaciones para nombre de elemento

    Returns:
        Primera línea del texto tal cual está en el mensaje
    """
    primera_linea = extraer_primera_linea(texto)
    return primera_linea if primera_linea else "Sin_Titulo"