"""
Userbot - Indexador automático de elementos
Usa Telethon para escanear el grupo almacén y crear elementos.
"""

import logging
import os
import re
import secrets
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

from database.base import get_database
from database.crud.elemento_crud import ElementoCRUD
from config import is_admin, is_moderator, BOT_TOKEN, CANAL_ELEMENTOS, GROUP_ADMIN_ID, ALMACENES_MAP
from automation.autoliker_userbot import registrar_autoliker_userbot

load_dotenv()

logger = logging.getLogger(__name__)

# === CONFIGURACIÓN ===
API_ID        = int(os.getenv("USERBOT_API_ID", "0"))
API_HASH      = os.getenv("USERBOT_API_HASH", "")
SESSION_NAME  = os.getenv("USERBOT_SESSION", "rg_manager")
KEYWORD       = "🎲 Géneros:"

TELEGRAM_API  = f"https://api.telegram.org/bot{BOT_TOKEN}"


# ──────────────────────────────────────────────
# ESTADO GLOBAL DEL USERBOT
# ──────────────────────────────────────────────

_estado_userbot: dict = {
    "conectado":                False,
    "conectado_desde":          None,
    "ultimo_index":             None,
    "elementos_indexados_total": 0,
    "ultimo_error":             None,
}

def get_estado_userbot() -> dict:
    return dict(_estado_userbot)

def es_staff(user_id: int) -> bool:
    return is_admin(user_id) or is_moderator(user_id)

def es_mensaje_elemento(msg) -> bool:
    tiene_foto    = isinstance(getattr(msg, "media", None), MessageMediaPhoto)
    tiene_keyword = KEYWORD in (msg.message or "")
    return tiene_foto and tiene_keyword

def extraer_nombre(texto: str) -> str:
    lineas = [l.strip() for l in (texto or "").splitlines() if l.strip()]
    return lineas[0] if lineas else ""

def obtener_ultimo_id_bd(almacen_id: int) -> int:
    """Obtiene el último ID procesado EXCLUSIVAMENTE para el almacén actual"""
    ultimo = get_database().elementos.find_one(
        {"almacen_id": almacen_id},
        sort=[("id_final", -1)],
        projection={"id_final": 1}
    )
    return ultimo["id_final"] if ultimo else 0

def calcular_peso_bloque(mensajes: dict, id_inicio: int, id_final: int) -> tuple:
    total_bytes = 0
    cantidad    = 0
    for msg_id in range(id_inicio, id_final + 1):
        msg = mensajes.get(msg_id)
        if msg is None:
            continue
        if isinstance(getattr(msg, "media", None), MessageMediaDocument):
            doc = msg.media.document
            if doc and hasattr(doc, "size") and doc.size:
                total_bytes += doc.size
                cantidad    += 1
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
    """Verifica si el chat actual es uno de los almacenes registrados en el mapa"""
    id_abs = abs(chat_id_telethon)
    id_normalizado = normalizar_chat_id(id_abs)
    
    for almacen_id in ALMACENES_MAP.keys():
        almacen_abs = abs(almacen_id)
        almacen_normalizado = normalizar_chat_id(almacen_abs)
        if id_normalizado == almacen_normalizado or id_abs == almacen_abs:
            return True
    return False

async def recolectar_mensajes(client: TelegramClient, chat_id: int, desde_id: int, hasta_id: int) -> dict:
    mensajes = {}
    async for msg in client.iter_messages(
        chat_id,
        min_id=desde_id,
        max_id=hasta_id + 1,
        reverse=True
    ):
        mensajes[msg.id] = msg
    return mensajes

def detectar_bloques(mensajes: dict, id_limite_final: int) -> list:
    bloques       = []
    bloque_activo = None

    for msg_id in sorted(mensajes.keys()):
        msg = mensajes[msg_id]

        if es_mensaje_elemento(msg):
            if bloque_activo is not None:
                id_fin             = msg_id - 1
                peso, num_archivos = calcular_peso_bloque(mensajes, bloque_activo["id_inicio"], id_fin)
                bloques.append({
                    "nombre":               bloque_activo["nombre"],
                    "id_inicio":            bloque_activo["id_inicio"],
                    "id_final":             id_fin,
                    "peso_bytes":           peso,
                    "num_archivos":         num_archivos,
                    "informacion_completa": bloque_activo["texto_completo"],
                })
            bloque_activo = {
                "nombre":        extraer_nombre(msg.message or ""),
                "id_inicio":     msg_id,
                "texto_completo": (msg.message or "").strip(),
            }

    if bloque_activo is not None:
        peso, num_archivos = calcular_peso_bloque(mensajes, bloque_activo["id_inicio"], id_limite_final)
        bloques.append({
            "nombre":               bloque_activo["nombre"],
            "id_inicio":            bloque_activo["id_inicio"],
            "id_final":             id_limite_final,
            "peso_bytes":           peso,
            "num_archivos":         num_archivos,
            "informacion_completa": bloque_activo["texto_completo"],
        })

    return bloques

def guardar_bloques(bloques: list, almacen_id: int) -> list:
    ids_creados = []

    for bloque in bloques:
        id_inicio            = bloque["id_inicio"]
        id_final             = bloque["id_final"]
        nombre               = bloque["nombre"][:80] if bloque["nombre"] else f"ELEM_{id_inicio}"
        peso_bytes           = bloque.get("peso_bytes", 0)
        num_archivos         = bloque.get("num_archivos", 0)
        informacion_completa = bloque.get("informacion_completa", "")

        # Verificamos si ya existe el bloque EXCLUSIVAMENTE en este almacén
        if ElementoCRUD.obtener_elemento_por_rango_mensaje(id_inicio, almacen_id=almacen_id):
            logger.debug(f"Bloque [{id_inicio}-{id_final}] ya en BD para el almacén {almacen_id}, omitido")
            continue

        if ElementoCRUD.obtener_elemento_por_nombre(nombre):
            sufijo = datetime.now(timezone.utc).strftime("%d%m%H%M%S")
            nombre = f"{nombre[:68]}_{sufijo}"

        resultado = ElementoCRUD.crear_elemento(
            nombre=nombre,
            id_inicio=id_inicio,
            id_final=id_final,
            creador_id=0,
            peso_bytes=peso_bytes,
            num_archivos=num_archivos,
            informacion_completa=informacion_completa,
            almacen_id=almacen_id  # Guardamos el almacén específico
        )

        if resultado:
            ids_creados.append(resultado["_id"])
        else:
            logger.error(f"❌ Error creando elemento '{nombre}' [{id_inicio}-{id_final}]")

    return ids_creados

async def indexar(client: TelegramClient, chat_id: int, comando_msg_id: int) -> tuple:
    # Ahora le pasamos el chat_id para que busque el último mensaje de ese grupo en concreto
    ultimo_id = obtener_ultimo_id_bd(almacen_id=chat_id)
    id_limite = comando_msg_id - 1

    if ultimo_id >= id_limite:
        return [], 0

    mensajes = await recolectar_mensajes(client, chat_id, desde_id=ultimo_id, hasta_id=id_limite)
    if not mensajes:
        return [], 0

    bloques    = detectar_bloques(mensajes, id_limite_final=id_limite)
    ids_nuevos = guardar_bloques(bloques, almacen_id=chat_id)
    return ids_nuevos, len(mensajes)

def encolar_publicacion(ids_elementos: list, chat_destino: int, solicitado_por: int) -> str:
    db      = get_database()
    task_id = secrets.token_hex(8)

    db.publicacion_pendiente.insert_one({
        "_id":            task_id,
        "elemento_ids":   ids_elementos,
        "chat_destino":   chat_destino,
        "solicitado_por": solicitado_por,
        "estado":         "pendiente",
        "creado_en":      datetime.now(timezone.utc),
    })

    return task_id

async def enviar_confirmacion(chat_id: int, task_id: str, ids_nuevos: list, total_analizados: int) -> None:
    lineas = []
    for idx, elem_id in enumerate(ids_nuevos[:10], 1):
        elem = ElementoCRUD.obtener_elemento_por_id(elem_id)
        if not elem:
            continue
        rango        = elem["id_final"] - elem["id_inicio"] + 1
        peso_str     = formatear_peso(elem.get("peso_bytes", 0))
        num_archivos = elem.get("num_archivos", 0)
        extra        = ""
        if peso_str and num_archivos:
            extra = f" • {peso_str} • {num_archivos} arch."
        elif peso_str:
            extra = f" • {peso_str}"
        lineas.append(f"{idx}. {elem['nombre'][:45]} [{elem['id_inicio']}-{elem['id_final']}] ({rango} msgs{extra})")

    resumen = "\n".join(lineas)
    if len(ids_nuevos) > 10:
        resumen += f"\n...y {len(ids_nuevos) - 10} más"

    canal_destino = ALMACENES_MAP.get(chat_id, CANAL_ELEMENTOS)

    texto = (
        f"✅ Indexado completado\n\n"
        f"📊 Mensajes analizados: {total_analizados}\n"
        f"📦 Elementos creados: {len(ids_nuevos)}\n"
        f"📺 Canal destino: {canal_destino}\n\n"
        f"Detalle:\n{resumen}\n\n"
        f"¿Publicar todos en el canal ahora?"
    )

    teclado = {
        "inline_keyboard": [[
            {"text": "✅ Confirmar", "callback_data": f"idxpub_confirm_{task_id}"},
            {"text": "❌ Cancelar",              "callback_data": f"idxpub_cancel_{task_id}"},
        ]]
    }

    async with httpx.AsyncClient() as http:
        resp = await http.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id":      chat_id,
                "text":         texto,
                "reply_markup": teclado,
            },
            timeout=15,
        )

    if resp.status_code != 200 or not resp.json().get("ok"):
        logger.error(f"Error enviando confirmación: {resp.text[:300]}")

async def iniciar_userbot() -> None:
    if not API_ID or not API_HASH or API_ID == 0:
        logger.warning("⚠️ Userbot desactivado: API_ID o API_HASH no configurados")
        return

    if not ALMACENES_MAP:
        logger.warning("⚠️ Userbot desactivado: ALMACENES_MAP está vacío")
        return

    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

    @client.on(events.NewMessage(pattern=re.compile(r"^/index", re.IGNORECASE)))
    async def handler_index(event):
        sender    = await event.get_sender()
        sender_id = sender.id

        if not es_staff(sender_id):
            await event.reply("❌ Solo administradores y moderadores pueden usar /index")
            return

        if not chat_es_almacen(event.chat_id):
            ids_configurados = list(ALMACENES_MAP.keys())
            await event.reply(
                f"❌ Este comando solo funciona en los grupos almacén configurados.\n\n"
                f"🛠 **Info para depurar:**\n"
                f"Tu ID actual: `{event.chat_id}`\n"
                f"IDs autorizados: `{ids_configurados}`\n\n"
                f"Verifica tu archivo de variables de entorno y reinicia el bot si tu ID no está en la lista."
            )
            return

        comando_msg_id = event.message.id

        msg_status = await event.reply("🔍 Indexando elementos...\nAnalizando mensajes del almacén, espera un momento.")

        try:
            ids_nuevos, total_analizados = await indexar(
                client=client,
                chat_id=event.chat_id,
                comando_msg_id=comando_msg_id,
            )

            if not ids_nuevos and total_analizados == 0:
                await msg_status.edit("✅ Indexado completado\n\nNo hay mensajes nuevos para indexar.\nEl almacén está al día.")
                return

            if not ids_nuevos:
                await msg_status.edit(f"✅ Indexado completado\n\n📊 Mensajes analizados: {total_analizados}\n📦 Elementos creados: 0\n\nNo se encontraron mensajes con imagen + {KEYWORD}.")
                return

            await msg_status.edit("✅ Indexado completado — preparando confirmación...")

            _estado_userbot["ultimo_index"]              = datetime.now(timezone.utc)
            _estado_userbot["elementos_indexados_total"] += len(ids_nuevos)

            task_id = encolar_publicacion(ids_elementos=ids_nuevos, chat_destino=event.chat_id, solicitado_por=sender_id)

            await enviar_confirmacion(chat_id=event.chat_id, task_id=task_id, ids_nuevos=ids_nuevos, total_analizados=total_analizados)

            await msg_status.delete()

        except Exception as e:
            logger.error(f"Error en handler_index: {e}", exc_info=True)
            _estado_userbot["ultimo_error"] = str(e)[:200]
            await msg_status.edit(f"❌ Error durante el proceso\n\n{str(e)[:300]}\n\nRevisa los logs para más detalles.")

    registrar_autoliker_userbot(client, BOT_TOKEN, CANAL_ELEMENTOS, GROUP_ADMIN_ID)

    try:
        await client.start()
        _estado_userbot["conectado"]       = True
        _estado_userbot["conectado_desde"] = datetime.now(timezone.utc)
        _estado_userbot["ultimo_error"]    = None
        logger.info("✅ Userbot conectado exitosamente")
        await client.run_until_disconnected()
    except Exception as e:
        logger.error(f"⚠️ Error en userbot: {e}")
        logger.warning("⚠️ El bot principal continuará funcionando sin el userbot")
        _estado_userbot["ultimo_error"] = str(e)[:200]
    finally:
        _estado_userbot["conectado"] = False