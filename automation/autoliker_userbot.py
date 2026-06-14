"""
Sistema AutoLiker - Userbot (Telethon)
El userbot detecta los eventos y aplica DOS reacciones aleatorias independientes:
  1. La suya propia vía Telethon (SendReactionRequest)
  2. La del bot principal vía Bot API (setMessageReaction)

Detección del canal:
  - Usa Raw(UpdateNewChannelMessage) para capturar publicaciones del canal
    sin depender de membresía ni de que el peer esté en caché.
  - Filtra por peer_id para reaccionar solo al canal configurado.

Detección de grupos:
  - Usa NewMessage(chats=grupos_ids) con filtro de hashtags.
"""

import logging
import random

import httpx
from telethon import events
from telethon.tl import types
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionEmoji, UpdateNewChannelMessage, PeerChannel

logger = logging.getLogger(__name__)

REACCIONES_POOL = ["❤", "👍", "🔥", "🥰", "🤩", "😍", "💯", "⚡"]  # Cada actor elige emoji independientemente

HASHTAGS_SOLICITUD = {  # Hashtags que activan la reacción en grupos
    "#game", "#games", "#juego", "#juegos",
    "#solicitud", "#pedido", "#sos", "#ayuda",
    "#help", "#bug", "#report", "#error",
}


def _emoji_aleatorio() -> str:
    """Retorna un emoji aleatorio del pool"""
    return random.choice(REACCIONES_POOL)


def _tiene_hashtag_solicitud(texto: str) -> bool:
    """Verifica si el texto contiene algún hashtag del sistema de solicitudes"""
    if not texto:
        return False
    palabras = {p.lower() for p in texto.split()}
    return bool(palabras & HASHTAGS_SOLICITUD)


def _normalizar_canal_id(canal_id: int) -> int:
    """
    Convierte el ID del canal a su forma positiva sin prefijo -100.
    Telethon en Raw updates expone el channel_id sin el prefijo -100.
    Ejemplos: -1001234567890 → 1234567890 | 1234567890 → 1234567890
    """
    s = str(abs(canal_id))
    return int(s[3:]) if s.startswith("100") else int(s)


async def _reaccion_userbot(client, chat_id: int, message_id: int) -> None:
    """Reacción del userbot vía Telethon"""
    emoji = _emoji_aleatorio()
    try:
        # Resolver el peer adecuadamente. Usar solo el entero puede hacer 
        # que Telethon no envíe el access_hash correcto y Telegram lo rechace.
        peer = await client.get_input_entity(chat_id)
        
        await client(SendReactionRequest(
            peer=peer,
            msg_id=message_id,
            reaction=[ReactionEmoji(emoticon=emoji)],
        ))
        logger.debug(f"Userbot reaccionó '{emoji}' → msg {message_id} en {chat_id}")
    except Exception as e:
        error_str = str(e)
        if "ANONYMOUS_REACTIONS_DISABLED" in error_str:
            logger.warning(
                f"⚠️ Userbot no pudo reaccionar al msg {message_id} en {chat_id}: "
                "La cuenta es un 'Administrador Anónimo'. Telegram bloquea sus reacciones. "
                "Desactiva 'Ser anónimo' (Remain Anonymous) en los permisos de administrador en Telegram."
            )
        else:
            logger.warning(f"Userbot no pudo reaccionar al msg {message_id} en {chat_id}: {error_str}")


async def _reaccion_bot(bot_token: str, chat_id: int, message_id: int) -> None:
    """Reacción del bot principal vía Bot API"""
    emoji = _emoji_aleatorio()
    url   = f"https://api.telegram.org/bot{bot_token}/setMessageReaction"
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.post(url, json={
                "chat_id":    chat_id,
                "message_id": message_id,
                "reaction":   [{"type": "emoji", "emoji": emoji}],
            })
        if not resp.json().get("ok"):
            logger.debug(f"Bot API no pudo reaccionar al msg {message_id}: {resp.text[:200]}")
        else:
            logger.debug(f"Bot reaccionó '{emoji}' → msg {message_id} en {chat_id}")
    except Exception as e:
        logger.warning(f"Bot no pudo reaccionar al msg {message_id} en {chat_id}: {e}")


async def _doble_reaccion(client, bot_token: str, chat_id: int, message_id: int) -> None:
    """Dispara ambas reacciones de forma independiente con emojis distintos"""
    await _reaccion_userbot(client, chat_id, message_id)
    await _reaccion_bot(bot_token, chat_id, message_id)


def registrar_autoliker_userbot(client, bot_token: str, canal_id: int, grupos_ids: list) -> None:
    """
    Registra los event handlers del autoliker en el cliente Telethon.
    Debe llamarse ANTES de client.start() dentro de iniciar_userbot().
    """
    if canal_id:
        canal_id_raw = _normalizar_canal_id(canal_id)  # ID sin prefijo -100

        @client.on(events.Raw(UpdateNewChannelMessage))
        async def _handler_canal(update):
            """Captura publicaciones del canal vía Raw update"""
            msg = update.message
            if not isinstance(msg, types.Message):  
                return
            peer = getattr(msg, "peer_id", None)
            if not isinstance(peer, PeerChannel):  
                return
            if peer.channel_id != canal_id_raw:  
                return
            chat_id_completo = int(f"-100{peer.channel_id}")
            await _doble_reaccion(client, bot_token, chat_id_completo, msg.id)

    if grupos_ids:
        @client.on(events.NewMessage(chats=grupos_ids))
        async def _handler_grupos(event):
            """Reacciona a mensajes con hashtags de solicitud en los grupos"""
            texto = event.message.text or event.message.message or ""
            if not _tiene_hashtag_solicitud(texto):
                return
            await _doble_reaccion(client, bot_token, event.chat_id, event.message.id)


def iniciar_autoliker(client, bot_token):
    """
    Inicializa el sistema de AutoLiker registrando los canales y grupos.
    """
    CANAL_ID = 3690749382  # ID del canal al que se le añadirá la funcionalidad de autoliker
    GRUPOS_IDS = []  # Lista de grupos (vacía por ahora)

    registrar_autoliker_userbot(client, bot_token, CANAL_ID, GRUPOS_IDS)