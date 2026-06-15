import re
import os
import asyncio
import logging
from telethon import events
from telethon.errors import FloodWaitError
from config import is_admin

logger = logging.getLogger(__name__)

# Configurar el canal de respaldo desde las variables de entorno
CANAL_BACKUP = os.getenv("CANAL_BACKUP_USERBOT", "")
# Asegurar el formato correcto del ID de Telethon (-100...)
CANAL_BACKUP_ID = int(f"-100{CANAL_BACKUP}" if CANAL_BACKUP and not CANAL_BACKUP.startswith("-") else CANAL_BACKUP) if CANAL_BACKUP else None

def register_clonar_handler(client):
    # Expresión regular que acepta obligatoriamente el chat_id, y opcionalmente id_inicio e id_fin
    @client.on(events.NewMessage(pattern=re.compile(r"^/clonar\s+(-?\d+)(?:\s+(\d+))?(?:\s+(\d+))?", re.IGNORECASE)))
    async def handler_clonar(event):
        try:
            # 1. Control de accesos: Solo Administradores
            if not is_admin(event.sender_id):
                return

            if not CANAL_BACKUP_ID:
                await event.reply("❌ Error: `CANAL_BACKUP_USERBOT` no está configurado en las variables de entorno.")
                return

            match = event.pattern_match
            
            # Extraer y normalizar el chat origen (soporta si el usuario lo pone con o sin -100)
            raw_chat_origen = match.group(1)
            if not raw_chat_origen.startswith("-") and len(raw_chat_origen) > 8:
                chat_origen = int(f"-100{raw_chat_origen}")
            else:
                chat_origen = int(raw_chat_origen)

            # Detectar los parámetros opcionales de mensajes
            param_inicio = match.group(2)
            param_fin = match.group(3)

            # Obtener el último mensaje del chat para saber el límite superior real
            status_msg = await event.reply("⏳ Conectando con el chat origen para calcular el rango...")
            try:
                ultimo_msg_lista = await client.get_messages(chat_origen, limit=1)
                id_ultimo_chat = ultimo_msg_lista[0].id if ultimo_msg_lista else 1
            except Exception as e:
                logger.error(f"No se pudo obtener el último mensaje de {chat_origen}: {e}")
                await status_msg.edit(f"❌ No se pudo acceder al chat origen `{chat_origen}`. Verifica que el userbot sea miembro.")
                return

            # Asignar lógica dinámica según los parámetros provistos
            if param_inicio and param_fin:
                id_inicio = int(param_inicio)
                id_fin = int(param_fin)
                modo_texto = f"rango de IDs `[{id_inicio} - {id_fin}]`"
            elif param_inicio and not param_fin:
                id_inicio = int(param_inicio)
                id_fin = id_ultimo_chat
                modo_texto = f"desde el mensaje `{id_inicio}` hasta el final (`{id_fin}`)"
            else:
                id_inicio = 1
                id_fin = id_ultimo_chat
                modo_texto = f"el canal COMPLETO `[1 - {id_fin}]`"

            if id_inicio > id_fin:
                await status_msg.edit("❌ El ID de inicio no puede ser mayor que el ID de fin.")
                return

            await status_msg.edit(f"📦 Recolectando índices para clonar {modo_texto}...")

            mensajes_a_enviar = []
            # Traer los IDs en orden reverso (del más viejo al más nuevo) para mantener la cronología en el backup
            async for msg in client.iter_messages(chat_origen, min_id=id_inicio - 1, max_id=id_fin + 1, reverse=True):
                if msg.id >= id_inicio and msg.id <= id_fin:
                    mensajes_a_enviar.append(msg.id)

            if not mensajes_a_enviar:
                await status_msg.edit("❌ No se encontraron mensajes válidos en el rango calculado.")
                return

            await status_msg.edit(f"🚀 Iniciando transferencia de {len(mensajes_a_enviar)} mensajes hacia el canal de backup...")

            reenviados = 0
            bloque_tamano = 10  # Lotes pequeños para mitigar FloodWaits masivos
            
            for i in range(0, len(mensajes_a_enviar), bloque_tamano):
                bloque = mensajes_a_enviar[i:i + bloque_tamano]
                
                while True:
                    try:
                        await client.forward_messages(CANAL_BACKUP_ID, bloque, chat_origen)
                        reenviados += len(bloque)
                        break
                    except FloodWaitError as e:
                        logger.warning(f"⏳ FloodWait detectado en clonación. Esperando {e.seconds} segundos...")
                        await asyncio.sleep(e.seconds)
                    except Exception as e:
                        logger.error(f"Error al reenviar lote de mensajes {bloque}: {e}")
                        break
                
                # Pausa de cortesía para no saturar la API de Telegram
                await asyncio.sleep(1.5)

            await status_msg.edit(
                f"✅ **¡Proceso de Clonación Completado!**\n\n"
                f"• **Origen:** `{chat_origen}`\n"
                f"• **Destino (Backup):** `{CANAL_BACKUP_ID}`\n"
                f"• **Mensajes transferidos:** `{reenviados}`"
            )

        except Exception as e:
            logger.error(f"Error crítico en handler_clonar: {e}")
            await event.reply(f"💥 Error inesperado en el proceso de clonación: {str(e)[:120]}")