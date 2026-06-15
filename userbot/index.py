import re
import logging
import asyncio
from telethon import events
from telethon.errors import FloodWaitError

logger = logging.getLogger(__name__)

def register_index_handler(client, estado_userbot, helpers):
    """
    Registra el handler del comando /index en el cliente de Telethon.
    Recibe el estado global del userbot y el diccionario de funciones auxiliares.
    """
    # Desempaquetar los helpers provenientes de manager.py
    obtener_ultimo_id_bd = helpers["obtener_ultimo_id_bd"]
    recolectar_mensajes = helpers["recolectar_mensajes"]
    detectar_bloques = helpers["detectar_bloques"]
    guardar_bloques = helpers["guardar_bloques"]
    encolar_publicacion = helpers["encolar_publicacion"]
    enviar_confirmacion = helpers["enviar_confirmacion"]
    chat_es_almacen = helpers["chat_es_almacen"]

    @client.on(events.NewMessage(pattern=re.compile(r"^/index\s+(\d+)\s+(\d+)", re.IGNORECASE)))
    async def handler_index(event):
        try:
            chat_id = event.chat_id
            
            # 1. Validar si el comando se ejecuta en un chat autorizado como almacén
            if not chat_es_almacen(chat_id):
                await event.reply("⚠️ Este chat no está configurado como un almacén válido en `ALMACENES_MAP`.")
                return

            # 2. Extraer parámetros del comando (/index <desde_id> <hasta_id>)
            match = event.pattern_match
            desde_id = int(match.group(1))
            hasta_id = int(match.group(2))

            if desde_id > hasta_id:
                await event.reply("❌ El ID de inicio (`desde_id`) no puede ser mayor que el ID de fin (`hasta_id`).")
                return

            status_msg = await event.reply(f"🔍 Analizando y recolectando mensajes en el rango [{desde_id} - {hasta_id}]...")

            # 3. Recolectar mensajes usando el helper optimizado
            mensajes = await recolectar_mensajes(client, chat_id, desde_id, hasta_id)
            if not mensajes:
                await status_msg.edit("❌ No se encontraron mensajes en el rango especificado o hubo un problema de conectividad.")
                return

            # 4. Detectar estructuras de bloques de elementos en los textos extraídos
            bloques = detectar_bloques(mensajes, hasta_id)
            if not bloques:
                await status_msg.edit("ℹ️ No se detectaron bloques de elementos nuevos (faltó la foto o el texto clave `🎲 Géneros:`).")
                return

            # 5. Guardar registros en la base de datos MongoDB
            ids_creados = guardar_bloques(bloques, chat_id)
            if not ids_creados:
                await status_msg.edit("ℹ️ El rango analizado ya se encuentra indexado en la base de datos.")
                return

            # 6. Encolar tarea de publicación pendiente
            solicitado_por = event.sender_id if event.sender_id else 0
            task_id = encolar_publicacion(ids_creados, chat_id, solicitado_por)

            # 7. Actualizar el estado en memoria del userbot
            from datetime import datetime, timezone
            estado_userbot["ultimo_index"] = datetime.now(timezone.utc)
            estado_userbot["elementos_indexados_total"] += len(ids_creados)

            # 8. Notificar el éxito y enviar los botones de confirmación interactiva
            await status_msg.delete()
            await enviar_confirmacion(chat_id, task_id, ids_creados, len(mensajes))

        except Exception as e:
            logger.error(f"Error crítico en handler_index: {e}")
            await event.reply(f"💥 Error inesperado durante la indexación: {str(e)[:100]}")