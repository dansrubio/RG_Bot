"""
Utilidades para parsear tiempo en formato humano
Conversión de strings como '7d6h30m' a segundos
"""

import re
import logging
from typing import Optional, Tuple


class TimeParser:
    """Parseador de tiempo en formato humano"""
    
    # Unidades de tiempo en segundos
    UNIDADES = {
        's': 1,      # segundos
        'm': 60,     # minutos
        'h': 3600,   # horas
        'd': 86400,  # días
        'w': 604800, # semanas
        'y': 31536000 # años (aproximado)
    }
    
    # Patrón regex para capturar tiempo
    PATRON_TIEMPO = re.compile(r'(\d+)([smhdwy])', re.IGNORECASE)
    
    @classmethod
    def parsear_duracion(cls, duracion_str: str) -> Optional[int]:
        """
        Parsea una cadena de tiempo y devuelve la duración en segundos
        
        Args:
            duracion_str: String de tiempo (ej: '7d6h30m')
            
        Returns:
            int: Duración en segundos o None si es inválido
        """
        if not duracion_str or not isinstance(duracion_str, str):
            return None
        
        try:
            # Limpiar la cadena
            duracion_str = duracion_str.strip().lower()
            
            # Buscar todas las coincidencias
            matches = cls.PATRON_TIEMPO.findall(duracion_str)
            
            if not matches:
                # Si no hay matches, intentar parsear como número puro (minutos)
                if duracion_str.isdigit():
                    return int(duracion_str) * 60  # Asumir minutos
                return None
            
            total_segundos = 0
            
            for cantidad, unidad in matches:
                cantidad = int(cantidad)
                
                if unidad in cls.UNIDADES:
                    total_segundos += cantidad * cls.UNIDADES[unidad]
                else:
                    logging.warning(f"⚠️ Unidad desconocida: {unidad}")
                    return None
            
            # Validar que no sea excesivo (máximo 1 año)
            if total_segundos > cls.UNIDADES['y']:
                logging.warning(f"⚠️ Duración muy larga: {total_segundos} segundos")
                return cls.UNIDADES['y']
            
            return total_segundos if total_segundos > 0 else None
            
        except Exception as e:
            logging.error(f"❌ Error parseando duración '{duracion_str}': {e}")
            return None
    
    @classmethod
    def formatear_duracion(cls, segundos: int) -> str:
        """
        Formatea una duración en segundos a texto legible
        
        Args:
            segundos: Duración en segundos
            
        Returns:
            str: Duración formateada (ej: '7 días, 6 horas, 30 minutos')
        """
        if segundos <= 0:
            return "0 segundos"
        
        try:
            partes = []
            
            # Años
            if segundos >= cls.UNIDADES['y']:
                años = segundos // cls.UNIDADES['y']
                segundos %= cls.UNIDADES['y']
                partes.append(f"{años} año{'s' if años != 1 else ''}")
            
            # Días
            if segundos >= cls.UNIDADES['d']:
                dias = segundos // cls.UNIDADES['d']
                segundos %= cls.UNIDADES['d']
                partes.append(f"{dias} día{'s' if dias != 1 else ''}")
            
            # Horas
            if segundos >= cls.UNIDADES['h']:
                horas = segundos // cls.UNIDADES['h']
                segundos %= cls.UNIDADES['h']
                partes.append(f"{horas} hora{'s' if horas != 1 else ''}")
            
            # Minutos
            if segundos >= cls.UNIDADES['m']:
                minutos = segundos // cls.UNIDADES['m']
                segundos %= cls.UNIDADES['m']
                partes.append(f"{minutos} minuto{'s' if minutos != 1 else ''}")
            
            # Segundos restantes
            if segundos > 0:
                partes.append(f"{segundos} segundo{'s' if segundos != 1 else ''}")
            
            # Unir las partes
            if len(partes) == 1:
                return partes[0]
            elif len(partes) == 2:
                return f"{partes[0]} y {partes[1]}"
            else:
                return ", ".join(partes[:-1]) + f" y {partes[-1]}"
                
        except Exception as e:
            logging.error(f"❌ Error formateando duración: {e}")
            return f"{segundos} segundos"
    
    @classmethod
    def obtener_tiempo_maximo_telegram(cls) -> int:
        """
        Obtiene el tiempo máximo de mute soportado por Telegram
        
        Returns:
            int: Segundos máximos (aproximadamente 366 días)
        """
        # Telegram permite hasta aproximadamente 366 días
        return 366 * cls.UNIDADES['d']
    
    @classmethod
    def validar_formato(cls, duracion_str: str) -> Tuple[bool, str]:
        """
        Valida si el formato de tiempo es correcto
        
        Args:
            duracion_str: String a validar
            
        Returns:
            Tuple[bool, str]: (es_valido, mensaje_error)
        """
        if not duracion_str:
            return False, "Duración vacía"
        
        segundos = cls.parsear_duracion(duracion_str)
        
        if segundos is None:
            return False, "Formato de tiempo inválido. Usa formato como '7d6h30m'"
        
        if segundos <= 0:
            return False, "La duración debe ser mayor a 0"
        
        if segundos > cls.obtener_tiempo_maximo_telegram():
            return False, "La duración excede el máximo permitido por Telegram (~366 días)"
        
        return True, ""


# === FUNCIONES DE CONVENIENCIA ===

def parsear_tiempo(duracion_str: str) -> Optional[int]:
    """Función de conveniencia para parsear tiempo"""
    return TimeParser.parsear_duracion(duracion_str)


def formatear_tiempo(segundos: int) -> str:
    """Función de conveniencia para formatear tiempo"""
    return TimeParser.formatear_duracion(segundos)