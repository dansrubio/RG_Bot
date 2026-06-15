"""
Configuración del bot de Telegram
Carga variables desde config.env y define configuraciones
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv('config.env')  # Cargar variables de entorno


# === FUNCIONES AUXILIARES DE PARSEO (DRY) ===

def _safe_int(env_key: str, default: int = 0) -> int:
    """Convierte de forma segura una variable de entorno a entero, soportando signos negativos."""
    val = os.getenv(env_key, "").strip()
    if not val:
        return default
    if val.lstrip('-').isdigit():
        return int(val)
    return default


def _parsear_ids(env_key: str) -> list[int]:
    """Parsea una lista de IDs separados por coma desde una variable de entorno."""
    val = os.getenv(env_key, "")
    return [
        int(chat_id.strip())
        for chat_id in val.split(",")
        if chat_id.strip() and chat_id.strip().lstrip("-").isdigit()
    ]


# === CONFIGURACIÓN BÁSICA ===
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')


# === DOCUMENTACIÓN DEL BOT ===
BOT_REGLAMENTO_URL = os.getenv('BOT_REGLAMENTO_URL', '')
BOT_PRIVACIDAD_URL = os.getenv('BOT_PRIVACIDAD_URL', '')


# === CONFIGURACIÓN DE USUARIOS ===
ADMIN_IDS = _parsear_ids('ADMIN_IDS')
MOD_IDS = _parsear_ids('MOD_IDS')
BOT_URL = os.getenv('BOT_URL', 'https://t.me/Rednite_bot')


# === CONFIGURACIÓN DE GRUPOS Y CANALES ===
GROUP_ADMIN_ID = _parsear_ids('GROUP_ADMIN_ID')
GP_ADMINS = _safe_int('GP_ADMINS')
ADMINISTRATION_GROUP = _safe_int('ADMINISTRATION_GROUP')

TOPIC_SOLICITUDES = _safe_int('TOPIC_SOLICITUDES', 12)
TOPIC_ERRORES = _safe_int('TOPIC_ERRORES', 14)

CANAL_ELEMENTOS = _safe_int('CANAL_ELEMENTOS')
CACHE_GROUP = _safe_int('CACHE_GROUP')
TOPIC_LOG_SOLICITUDES = _safe_int('TOPIC_LOG_SOLICITUDES', 6218)


# === TOPICS DE MONITOREO DE WEBS ===
TOPIC_GAMES_MONITOR = _safe_int('TOPIC_GAMES_MONITOR', 9121)


# === CANALES DE VERIFICACIÓN ===
VERIFICATION_CHANNELS = _parsear_ids('BOT_VERIFICATION_CHANNELS')


# === CONFIGURACIÓN DE MULTI-ALMACENES ===
# Se eliminó la redundancia evaluando de forma limpia las tuplas activas
_almacenes_fuente = [
    (ADMINISTRATION_GROUP, CANAL_ELEMENTOS), 
    (_safe_int('ALMACEN_CANAIMA'), _safe_int('CANAL_CANAIMA')),
    (_safe_int('ALMACEN_SWITCH'), _safe_int('CANAL_SWITCH')),
    (_safe_int('ALMACEN_AUDIOVISUALES'), _safe_int('CANAL_AUDIOVISUALES')),
    (_safe_int('ALMACEN_PS4'), _safe_int('CANAL_PS4'))
]
ALMACENES_MAP = {k: v for k, v in _almacenes_fuente if k != 0 and v != 0}


# === CONFIGURACIÓN DE BASE DE DATOS ===
# CORREGIDO: MONGODB_URI mapeado correctamente para evitar fallos de conexión
DATABASE_URL = os.getenv('MONGODB_URI', '')


# === APIS EXTERNAS ===
REBRANDLY_API_KEY = os.getenv('REBRANDLY_API_KEY', '')
GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')

TMDB_ACCESS_TOKEN = os.getenv('TMDB_ACCESS_TOKEN', '')
TMDB_API_KEY = os.getenv('TMDB_API_KEY', '')

STEAM_API_KEY = os.getenv('STEAM_API_KEY', '')

IGDB_CLIENT_ID = os.getenv('IGDB_CLIENT_ID', '')
IGDB_CLIENT_SECRET = os.getenv('IGDB_CLIENT_SECRET', '')

RAWG_API_KEY = os.getenv('RAWG_API_KEY', '')


# === DESTINOS DE NOTIFICACIÓN JUEGOS GRATIS ===
FREE_GAMES_GRUPOS = _parsear_ids("FREE_GAMES_GRUPOS")
FREE_GAMES_CANALES = _parsear_ids("FREE_GAMES_CANALES")
FREE_GAMES_INTERVALO_HORAS = _safe_int("FREE_GAMES_INTERVALO_HORAS", 4)


# =========================================================
# 🔐 FUNCIONES DE CONTROL
# =========================================================

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def is_moderator(user_id: int) -> bool:
    return user_id in MOD_IDS


def is_staff(user_id: int) -> bool:
    return user_id in ADMIN_IDS or user_id in MOD_IDS


def get_user_rank(user_id: int) -> str:
    if user_id in ADMIN_IDS:
        return 'admin'
    elif user_id in MOD_IDS:
        return 'moderador'
    return 'usuario'


# =========================================================
# ✅ VALIDACIONES
# =========================================================

def validate_free_games_config() -> bool:
    """Valida configuración de juegos gratis"""
    if not FREE_GAMES_GRUPOS and not FREE_GAMES_CANALES:
        logging.error("❌ Debes configurar FREE_GAMES_GRUPOS y/o FREE_GAMES_CANALES")
        return False
    return True


def validate_config() -> bool:
    """Valida la configuración general"""
    errors = []

    if not BOT_TOKEN:
        errors.append("❌ BOT_TOKEN no configurado")
    if not DATABASE_URL:
        errors.append("❌ MONGODB_URI no configurado")

    if errors:
        for error in errors:
            logging.error(error)
        logging.error("El bot no puede continuar con errores críticos")
        return False

    validate_free_games_config()
    return True


# =========================================================
# 📊 RESUMEN DE CONFIG
# =========================================================

def get_config_summary() -> dict:
    return {
        'bot_configured': bool(BOT_TOKEN),
        'admins_count': len(ADMIN_IDS),
        'moderators_count': len(MOD_IDS),

        'free_games': {
            'grupos': len(FREE_GAMES_GRUPOS),
            'canales': len(FREE_GAMES_CANALES),
            'intervalo_horas': FREE_GAMES_INTERVALO_HORAS
        },

        'apis_configured': {
            'groq': bool(GROQ_API_KEY),
            'tmdb': bool(TMDB_ACCESS_TOKEN or TMDB_API_KEY),
            'steam': bool(STEAM_API_KEY),
            'igdb': bool(IGDB_CLIENT_ID and IGDB_CLIENT_SECRET),
            'rawg': bool(RAWG_API_KEY)
        }
    }