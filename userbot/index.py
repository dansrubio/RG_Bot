import re
import logging
from telethon import events
from config import is_admin

logger = logging.getLogger(__name__)

def register_index_handler(client, estado_userbot, helpers):
    """
    Registra el handler del comando /index en el cliente de Telethon.
    """
    obtener_ultimo_id_bd = helpers["obtener_ultimo_id_bd"]
    recolectar_mensajes = helpers["recolectar_mensajes"]
    detectar_bloques = helpers["detectar_bloques"]
    guardar_bloques = helpers["guardar_bloques"]
    encolar_publicacion = helpers["encolar_publicacion"]
    enviar_confirmacion = helpers["enviar_confirmacion"]
    chat_es_almacen = helpers["chat_es_almacen"]

    # 🛠️ REGEX CORREGIDO: Los grupos de captura de números ahora son opcionales (?:...)?
    @client.on(events.NewMessage(pattern=re.compile(r"^/index(?:\s+(\d+)\s+(\d+))?", re.IGNORECASE)))
    async def handler_index(event):
        try:
            # Seguridad estricta
            if not is_admin(event.sender_id):
                return
            
            chat_id = event.chat_id
            
            # Validar almacén
            if not chat_es_almacen(chat_id):
                await event.reply("⚠️ Este chat no está configurado como un almacén válido en `ALMACENES_MAP`.")
                return

            match = event.pattern_match
            
            # 🔄 LÓGICA HÍBRIDA: Manual vs Automático
            if match.group(1) and match.group(2):
                # Modo Manual (ej. /index 100 200)
                desde_id = int(match.group(1))
                hasta_id = int(match.group(2))
                if desde_id > hasta_id:
                    await event.reply("❌ El ID de inicio no puede ser mayor que el ID final.")
                    return
            else:
                # Modo Automático (comportamiento recuperado de tu código antiguo)
                desde_id = obtener_ultimo_id_bd(chat_id)
                hasta_id = event.message.id - 1
                
                if desde_id >= hasta_id:
                    await event.reply("✅ El almacén ya está completamente al día. No hay mensajes nuevos para indexar.")
                    return

            status_msg = await event.reply(f"🔍 Analizando y recolectando mensajes en el rango [{desde_id} - {hasta_id}]...")

            # Recolectar mensajes
            mensajes = await recolectar_mensajes(client, chat_id, desde_id, hasta_id, status_msg)
            
            if not mensajes:
                await status_msg.edit("❌ No se encontraron mensajes en el rango especificado o hubo un problema de conectividad.")
                return

            # Detectar y procesar bloques
            bloques = detectar_bloques(mensajes, hasta_id)
            if not bloques:
                await status_msg.edit("ℹ️ No se detectaron bloques de elementos nuevos (faltó la foto o el texto clave `🎲 Géneros:`).")
                return

            # Guardar en BD
            ids_creados = guardar_bloques(bloques, chat_id)
            if not ids_creados:
                await status_msg.edit("ℹ️ El rango analizado ya se encuentra indexado en la base de datos.")
                return

            # Encolar para el bot principal
            solicitado_por = event.sender_id if event.sender_id else 0
            task_id = encolar_publicacion(ids_creados, chat_id, solicitado_por)

            # Actualizar memoria del bot
            from datetime import datetime, timezone
            estado_userbot["ultimo_index"] = datetime.now(timezone.utc)
            estado_userbot["elementos_indexados_total"] += len(ids_creados)

            # Confirmar y limpiar
            await status_msg.delete()
            await enviar_confirmacion(chat_id, task_id, ids_creados, len(mensajes))

        except Exception as e:
            logger.error(f"Error crítico en handler_index: {e}", exc_info=True)
            await event.reply(f"💥 Error inesperado durante la indexación: {str(e)[:100]}")