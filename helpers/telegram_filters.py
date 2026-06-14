"""
Filtros y utilidades para identificar cuentas especiales de Telegram
"""

# IDs de cuentas oficiales de Telegram que no deben ser procesadas
TELEGRAM_OFFICIAL_IDS = {
    777000,    # Telegram
    136817688, # Channel Bot
    429000,    # Telegram Support  
    42777,     # Telegram Tips
    93372553,  # BotFather
    101374607, # Group Anonymous Bot
    1087968824, # Group Anonymous Bot (nuevo)
}

# Rangos de IDs reservados por Telegram
TELEGRAM_RESERVED_RANGES = [
    (1, 1000),        # IDs muy bajos reservados
    (777000, 777999), # Rango oficial de Telegram
]

def es_cuenta_sistema_telegram(user_id: int) -> bool:
    """
    Verifica si un ID pertenece al sistema de Telegram
    
    Args:
        user_id (int): ID del usuario a verificar
        
    Returns:
        bool: True si es cuenta del sistema, False si es usuario normal
    """
    # Verificar IDs conocidos del sistema
    if user_id in TELEGRAM_OFFICIAL_IDS:
        return True
    
    # Verificar rangos reservados
    for inicio, fin in TELEGRAM_RESERVED_RANGES:
        if inicio <= user_id <= fin:
            return True
    
    return False

def es_usuario_valido_para_tracking(user_id: int, is_bot: bool = False) -> bool:
    """
    Verifica si un usuario debe ser trackeado en la base de datos
    
    Args:
        user_id (int): ID del usuario
        is_bot (bool): Si el usuario es un bot
        
    Returns:
        bool: True si debe ser trackeado, False si debe ser ignorado
    """
    # No trackear bots
    if is_bot:
        return False
    
    # No trackear cuentas del sistema
    if es_cuenta_sistema_telegram(user_id):
        return False
    
    # No trackear IDs negativos (grupos/canales)
    if user_id < 0:
        return False
    
    return True

def obtener_tipo_cuenta(user_id: int, is_bot: bool = False) -> str:
    """
    Identifica el tipo de cuenta basado en el ID
    
    Args:
        user_id (int): ID del usuario
        is_bot (bool): Si el usuario es un bot
        
    Returns:
        str: Tipo de cuenta ('usuario', 'bot', 'sistema', 'grupo')
    """
    if user_id < 0:
        return 'grupo'
    
    if is_bot:
        return 'bot'
    
    if es_cuenta_sistema_telegram(user_id):
        return 'sistema'
    
    return 'usuario'