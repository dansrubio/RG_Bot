import logging
import os
import asyncio
import httpx
import secrets
from datetime import datetime, timezone
from telethon import TelegramClient
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from telethon.errors import FloodWaitError

from database.base import get_database
from config import BOT_TOKEN, CANAL_ELEMENTOS, GROUP_ADMIN_ID, ALMACENES_MAP
from automation.autoliker_userbot import registrar_autoliker_userbot

# Importamos los registradores de comandos del Userbot
from userbot.index import register_index_handler
from userbot.info import register_info_handler

logger = logging.getLogger(__name__)

API_ID = int(os.getenv("USERBOT_API_ID", "0"))
API_HASH = os.getenv("USERBOT_API_HASH", "")
SESSION_NAME = os.getenv("USERBOT_SESSION", "rg_manager")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

_estado_userbot = {
    "conectado": False,
    "conectado_desde": None,
    "ultimo_index": None,
    "elementos_indexados_total": 0,
    "ultimo_error": None,
}

def get_estado_userbot() -> dict:
    return dict(_estado_userbot)

# =========================================================
# 🛠️ FUNCIONES AUXILIARES
# =========================================================
def es_mensaje_elemento(msg) -> bool:
    tiene_foto = isinstance(getattr(msg, "media", None), MessageMediaPhoto)
    # Convertimos a minúsculas para hacerlo insensible a fallos de tipeo
    texto_mensaje = (msg.message or "").lower()
    tiene_keyword = "🎲 géneros:" in texto_mensaje or "géneros:" in texto_mensaje
    return tiene_foto and tiene_keyword

def extraer_nombre(texto: str) -> str:
    lineas = [l.strip() for l in (texto or "").splitlines() if l.strip()]
    return lineas[0] if lineas else ""

def obtener_ultimo_id_bd(almacen_id: int) -> int:
    ultimo = get_database().elementos.find_one(
        {"almacen_id": almacen_id},
        sort=[("id_final", -1)],
        projection={"id_final": 1}
    )
    return ultimo["id_final"] if ultimo else 0

def calcular_peso_bloque(mensajes: dict, id_inicio: int, id_final: int) -> tuple:
    total_bytes = 0
    cantidad = 0
    for msg_id in range(id_inicio, id_final + 1):
        msg = mensajes.get(msg_id)
        if msg is None:
            continue
        if isinstance(getattr(msg, "media", None), MessageMediaDocument):
            doc = msg.media.document
            if doc and hasattr(doc, "size") and doc.size:
                total_bytes += doc.size
                cantidad += 1
    return total_bytes, cantidad

def formatear_peso(bytes_total: int) -> str:
    if bytes_total <= 0:
        return ""
    if bytes_total >= 1_073_741_824:
        return f"{bytes_total / 1_073_741_824:.2f} GB".rstrip("0").rstrip(".")
    if bytes_total >= 1_048_576:
        valor = bytes_total / 1_048_576
        return f"{valor:.1f} MB" if valor % 1 else f"{int(valor)} MB"
    return f"{bytes_total / 1024:.0f} KB"

def normalizar_chat_id(chat_id: int) -> int:
    id_abs = abs(chat_id)
    if str(id_abs).startswith("100"):
        return int(str(id_abs)[3:])
    return id_abs

def chat_es_almacen(chat_id_telethon: int) -> bool:
    id_abs = abs(chat_id_telethon)
    id_normalizado = normalizar_chat_id(id_abs)
    for almacen_id in ALMACENES_MAP.keys():
        almacen_abs = abs(almacen_id)
        almacen_normalizado = normalizar_chat_id(almacen_abs)
        if id_normalizado == almacen_normalizado or id_abs == almacen_abs:
            return True
    return False

async def recolectar_mensajes(client, chat_id: int, desde_id: int, hasta_id: int, status_msg=None) -> dict:
    mensajes = {}
    try:
        # Quitamos reverse=True para evitar bugs internos de Telethon en grupos grandes
        async for msg in client.iter_messages(chat_id, min_id=desde_id - 1, max_id=hasta_id + 1):
            if msg.id >= desde_id and msg.id <= hasta_id:
                mensajes[msg.id] = msg
                
    except FloodWaitError as e:
        logger.warning(f"⏳ FloodWait detectado en recolección. Esperando {e.seconds} segundos...")
        
        if status_msg:
            try:
                minutos = e.seconds // 60
                await status_msg.edit(f"⏳ **Límite de Telegram detectado.**\nEl userbot debe pausar por {minutos} minutos. Reanudará automáticamente...")
            except Exception:
                pass
                
        await asyncio.sleep(e.seconds)
        
        # Reintentar recursivamente desde el último ID seguro (-1 para no omitir el causante del corte)
        ultimo_procesado = max(mensajes.keys() or [desde_id - 1])
        if ultimo_procesado < hasta_id:
            faltantes = await recolectar_mensajes(client, chat_id, ultimo_procesado + 1, hasta_id, status_msg)
            mensajes.update(faltantes)
            
    return mensajes

def detectar_bloques(mensajes: dict, id_limite_final: int) -> list:
    bloques = []
    bloque_activo = None
    for msg_id in sorted(mensajes.keys()):
        msg = mensajes[msg_id]
        if es_mensaje_elemento(msg):
            if bloque_activo is not None:
                id_fin = msg_id - 1
                peso, num_archivos = calcular_peso_bloque(mensajes, bloque_activo["id_inicio"], id_fin)
                bloques.append({
                    "nombre": bloque_activo["nombre"],
                    "id_inicio": bloque_activo["id_inicio"],
                    "id_final": id_fin,
                    "peso_bytes": peso,
                    "num_archivos": num_archivos,
                    "informacion_completa": bloque_activo["texto_completo"],
                })
            bloque_activo = {
                "nombre": extraer_nombre(msg.message or ""),
                "id_inicio": msg_id,
                "texto_completo": (msg.message or "").strip(),
            }
    if bloque_activo is not None:
        peso, num_archivos = calcular_peso_bloque(mensajes, bloque_activo["id_inicio"], id_limite_final)
        bloques.append({
            "nombre": bloque_activo["nombre"],
            "id_inicio": bloque_activo["id_inicio"],
            "id_final": id_limite_final,
            "peso_bytes": peso,
            "num_archivos": num_archivos,
            "informacion_completa": bloque_activo["texto_completo"],
        })
    return bloques

def guardar_bloques(bloques: list, almacen_id: int) -> list:
    from database.crud.elemento_crud import ElementoCRUD
    ids_creados = []
    for bloque in bloques:
        id_inicio = bloque["id_inicio"]
        id_final = bloque["id_final"]
        nombre = bloque["nombre"][:80] if bloque["nombre"] else f"ELEM_{id_inicio}"
        peso_bytes = bloque.get("peso_bytes", 0)
        num_archivos = bloque.get("num_archivos", 0)
        informacion_completa = bloque.get("informacion_completa", "")

        if ElementoCRUD.obtener_elemento_por_rango_mensaje(id_inicio, almacen_id=almacen_id):
            continue
        if ElementoCRUD.obtener_elemento_por_nombre(nombre):
            sufijo = datetime.now(timezone.utc).strftime("%d%m%H%M%S")
            nombre = f"{nombre[:68]}_{sufijo}"

        resultado = ElementoCRUD.crear_elemento(
            nombre=nombre, id_inicio=id_inicio, id_final=id_final, creador_id=0,
            peso_bytes=peso_bytes, num_archivos=num_archivos, informacion_completa=informacion_completa,
            almacen_id=almacen_id
        )
        if resultado:
            ids_creados.append(resultado["_id"])
    return ids_creados

def encolar_publicacion(ids_elementos: list, chat_destino: int, solicitado_por: int) -> str:
    db = get_database()
    task_id = secrets.token_hex(8)
    db.publicacion_pendiente.insert_one({
        "_id": task_id, "elemento_ids": ids_elementos, "chat_destino": chat_destino,
        "solicitado_por": solicitado_por, "estado": "pendiente", "creado_en": datetime.now(timezone.utc),
    })
    return task_id

async def enviar_confirmacion(chat_id: int, task_id: str, ids_nuevos: list, total_analizados: int) -> None:
    from database.crud.elemento_crud import ElementoCRUD
    lineas = []
    for idx, elem_id in enumerate(ids_nuevos[:10], 1):
        elem = ElementoCRUD.obtener_elemento_por_id(elem_id)
        if not elem: continue
        rango = elem["id_final"] - elem["id_inicio"] + 1
        peso_str = formatear_peso(elem.get("peso_bytes", 0))
        num_archivos = elem.get("num_archivos", 0)
        extra = f" • {peso_str} • {num_archivos} arch." if peso_str and num_archivos else (f" • {peso_str}" if peso_str else "")
        lineas.append(f"{idx}. {elem['nombre'][:45]} [{elem['id_inicio']}-{elem['id_final']}] ({rango} msgs{extra})")

    resumen = "\n".join(lineas)
    if len(ids_nuevos) > 10: resumen += f"\n...y {len(ids_nuevos) - 10} más"
    
    # Mapeo de canal corrigiendo la diferencia de IDs (normalizando)
    canal_destino = CANAL_ELEMENTOS
    id_norm = normalizar_chat_id(abs(chat_id))
    for almac, dest in ALMACENES_MAP.items():
        if normalizar_chat_id(abs(almac)) == id_norm:
            canal_destino = dest
            break
            
    texto = f"✅ Indexado completado\n\n📊 Mensajes analizados: {total_analizados}\n📦 Elementos creados: {len(ids_nuevos)}\n📺 Canal destino: {canal_destino}\n\nDetalle:\n{resumen}\n\n¿Publicar todos en el canal ahora?"
    teclado = {"inline_keyboard": [[{"text": "✅ Confirmar", "callback_data": f"idxpub_confirm_{task_id}"}, {"text": "❌ Cancelar", "callback_data": f"idxpub_cancel_{task_id}"}]]}

    async with httpx.AsyncClient() as http:
        response = await http.post(
            f"{TELEGRAM_API}/sendMessage", 
            json={"chat_id": chat_id, "text": texto, "reply_markup": teclado}, 
            timeout=15
        )
        # Fuerza que el error sea arrojado si el bot no tiene permisos de envío
        response.raise_for_status()

# =========================================================
# 🚀 FUNCIÓN DE INICIO PRINCIPAL CON RECONEXIÓN AUTOMÁTICA
# =========================================================
async def iniciar_userbot() -> None:
    if not API_ID or not API_HASH or API_ID == 0:
        logger.warning("⚠️ Userbot desactivado: API_ID o API_HASH no configurados")
        return

    if not ALMACENES_MAP:
        logger.warning("⚠️ Userbot desactivado: ALMACENES_MAP está vacío")
        return

    helpers = {
        "obtener_ultimo_id_bd": obtener_ultimo_id_bd,
        "recolectar_mensajes": recolectar_mensajes,
        "detectar_bloques": detectar_bloques,
        "guardar_bloques": guardar_bloques,
        "encolar_publicacion": encolar_publicacion,
        "enviar_confirmacion": enviar_confirmacion,
        "chat_es_almacen": chat_es_almacen
    }

    reintentos = 0
    while True:
        try:
            logger.info(f"🚀 Conectando el Userbot Indexador (Intento de conexión: {reintentos + 1})...")
            client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

            # Registro de manejadores pasándole los parámetros requeridos
            register_index_handler(client, _estado_userbot, helpers)
            register_info_handler(client)

            registrar_autoliker_userbot(client, BOT_TOKEN, CANAL_ELEMENTOS, GROUP_ADMIN_ID)

            await client.start()
            
            _estado_userbot["conectado"] = True
            _estado_userbot["conectado_desde"] = datetime.now(timezone.utc)
            _estado_userbot["ultimo_error"] = None
            reintentos = 0  
            
            logger.info("✅ Userbot sincronizado con la API de Telegram.")
            await client.run_until_disconnected()

        except Exception as e:
            _estado_userbot["conectado"] = False
            reintentos += 1
            tiempo_espera = min(300, 2 ** reintentos)
            _estado_userbot["ultimo_error"] = f"[Fallo #{reintentos}] {str(e)[:150]}"
            
            logger.error(f"⚠️ Error crítico en el ciclo de ejecución del Userbot. Reintentando en {tiempo_espera}s: {e}")
            await asyncio.sleep(tiempo_espera)
        finally:
            _estado_userbot["conectado"] = False