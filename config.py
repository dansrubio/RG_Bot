"""
Configuración del bot de Telegram
Carga variables desde .env y define configuraciones
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv('config.env')  # Cargar variables de entorno


# === CONFIGURACIÓN BÁSICA ===
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')


# === DOCUMENTACIÓN DEL BOT ===
BOT_REGLAMENTO_URL = os.getenv('BOT_REGLAMENTO_URL', '')
BOT_PRIVACIDAD_URL = os.getenv('BOT_PRIVACIDAD_URL', '')


# === CONFIGURACIÓN DE USUARIOS ===
ADMIN_IDS = [
    int(admin_id.strip())
    for admin_id in os.getenv('ADMIN_IDS', '').split(',')
    if admin_id.strip() and admin_id.strip().isdigit()
]

MOD_IDS = [
    int(mod_id.strip())
    for mod_id in os.getenv('MOD_IDS', '').split(',')
    if mod_id.strip() and mod_id.strip().isdigit()
]

BOT_URL = os.getenv('BOT_URL', 'https://t.me/Rednite_bot')


# === CONFIGURACIÓN DE GRUPOS Y CANALES ===
GROUP_ADMIN_ID = [
    int(group_id.strip()) for group_id in os.getenv('GROUP_ADMIN_ID', '').split(',')
    if group_id.strip() and (group_id.strip().lstrip('-').isdigit())
]

GP_ADMINS = int(os.getenv('GP_ADMINS', '0')) if os.getenv('GP_ADMINS', '').lstrip('-').isdigit() else 0
ADMINISTRATION_GROUP = int(os.getenv('ADMINISTRATION_GROUP', '0')) if os.getenv('ADMINISTRATION_GROUP', '').lstrip('-').isdigit() else 0

TOPIC_SOLICITUDES = int(os.getenv('TOPIC_SOLICITUDES', '12'))
TOPIC_ERRORES = int(os.getenv('TOPIC_ERRORES', '14'))

CANAL_ELEMENTOS = int(os.getenv('CANAL_ELEMENTOS', '0')) if os.getenv('CANAL_ELEMENTOS', '').lstrip('-').isdigit() else 0
CACHE_GROUP = int(os.getenv('CACHE_GROUP', '0')) if os.getenv('CACHE_GROUP', '').lstrip('-').isdigit() else 0
TOPIC_LOG_SOLICITUDES = int(os.getenv('TOPIC_LOG_SOLICITUDES', '6218'))

# === TOPICS DE MONITOREO DE WEBS ===
TOPIC_GAMES_MONITOR = int(os.getenv('TOPIC_GAMES_MONITOR', '9121'))

# === CANALES DE VERIFICACIÓN ===
VERIFICATION_CHANNELS = [
    int(channel_id.strip())
    for channel_id in os.getenv('BOT_VERIFICATION_CHANNELS', '').split(',')
    if channel_id.strip() and channel_id.strip().lstrip('-').isdigit()
]

# === CONFIGURACIÓN DE MULTI-ALMACENES ===
_mapa_temp = {
    # CAMBIO AQUÍ: Usamos ADMINISTRATION_GROUP directamente
    ADMINISTRATION_GROUP: CANAL_ELEMENTOS, 
    
    int(os.getenv('ALMACEN_CANAIMA', '0')) if os.getenv('ALMACEN_CANAIMA', '').lstrip('-').isdigit() else 0: int(os.getenv('CANAL_CANAIMA', '0')) if os.getenv('CANAL_CANAIMA', '').lstrip('-').isdigit() else 0,
    int(os.getenv('ALMACEN_SWITCH', '0')) if os.getenv('ALMACEN_SWITCH', '').lstrip('-').isdigit() else 0: int(os.getenv('CANAL_SWITCH', '0')) if os.getenv('CANAL_SWITCH', '').lstrip('-').isdigit() else 0,
    int(os.getenv('ALMACEN_AUDIOVISUALES', '0')) if os.getenv('ALMACEN_AUDIOVISUALES', '').lstrip('-').isdigit() else 0: int(os.getenv('CANAL_AUDIOVISUALES', '0')) if os.getenv('CANAL_AUDIOVISUALES', '').lstrip('-').isdigit() else 0,
    int(os.getenv('ALMACEN_PS4', '0')) if os.getenv('ALMACEN_PS4', '').lstrip('-').isdigit() else 0: int(os.getenv('CANAL_PS4', '0')) if os.getenv('CANAL_PS4', '').lstrip('-').isdigit() else 0
}
ALMACENES_MAP = {k: v for k, v in _mapa_temp.items() if k != 0 and v != 0}

# === CONFIGURACIÓN DE BASE DE DATOS ===
DATABASE_URL = os.getenv('DATABASE_URL', '')


# === APIS EXTERNAS ===
REBRANDLY_API_KEY = os.getenv('REBRANDLY_API_KEY', '')
GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')

TMDB_ACCESS_TOKEN = os.getenv('TMDB_ACCESS_TOKEN', '')
TMDB_API_KEY = os.getenv('TMDB_API_KEY', '')

STEAM_API_KEY = os.getenv('STEAM_API_KEY', '')

IGDB_CLIENT_ID = os.getenv('IGDB_CLIENT_ID', '')
IGDB_CLIENT_SECRET = os.getenv('IGDB_CLIENT_SECRET', '')

RAWG_API_KEY = os.getenv('RAWG_API_KEY', '')


# =========================================================
# 🎮 CONFIGURACIÓN DE JUEGOS GRATIS
# =========================================================

def _parsear_ids(env_key: str) -> list[int]:
    """Parsea una lista de IDs separados por coma desde una variable de entorno"""
    return [
        int(chat_id.strip())
        for chat_id in os.getenv(env_key, "").split(",")
        if chat_id.strip() and chat_id.strip().lstrip("-").isdigit()
    ]


# === DESTINOS DE NOTIFICACIÓN ===
FREE_GAMES_GRUPOS = _parsear_ids("FREE_GAMES_GRUPOS")
FREE_GAMES_CANALES = _parsear_ids("FREE_GAMES_CANALES")


# === CONFIGURACIÓN DEL JOB ===
FREE_GAMES_INTERVALO_HORAS = int(os.getenv("FREE_GAMES_INTERVALO_HORAS", "4"))


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