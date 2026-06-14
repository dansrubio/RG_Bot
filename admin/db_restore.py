"""
Módulo para restaurar backups de la base de datos mediante comando /db_restore
"""

import os
import shutil
import tempfile
import zipfile
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Dict, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode
from cachetools import TTLCache

from bson import json_util

from database.base import get_database
from database.manager import get_database_config
from config import is_admin

logger = logging.getLogger(__name__)

# Almacenamiento temporal de datos de restauración con expiración de 1 hora
_restore_sessions = TTLCache(maxsize=100, ttl=3600)


async def _perform_restore_async(executor_fn, *args, **kwargs):
    """Helper para ejecutar la restauración en un hilo separado"""
    return await asyncio.to_thread(executor_fn, *args, **kwargs)


def _extract_zip(zip_path: str, extract_to: str) -> str:
    """Extrae el ZIP y retorna la ruta del directorio extraído"""
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)
    return extract_to


def _validate_backup_structure(folder_path: str) -> Dict:
    """
    Valida la estructura del backup y retorna metadata

    Returns:
        dict con:
            - valid: bool
            - error: str (si valid=False)
            - metadata: dict (si existe)
            - collections: list[str] (archivos .jsonl encontrados)
    """
    result = {
        "valid": False,
        "error": "",
        "metadata": None,
        "collections": []
    }

    # Verificar que existe metadata.json
    metadata_path = os.path.join(folder_path, "metadata.json")
    if not os.path.exists(metadata_path):
        result["error"] = "No se encontró metadata.json en el backup"
        return result

    # Leer metadata
    try:
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        result["metadata"] = metadata
    except Exception as e:
        result["error"] = f"Error leyendo metadata.json: {e}"
        return result

    # Buscar archivos .jsonl (colecciones)
    collections = []
    for file in os.listdir(folder_path):
        if file.endswith('.jsonl'):
            coll_name = file[:-6]  # Remover .jsonl
            collections.append(coll_name)

    if not collections:
        result["error"] = "No se encontraron colecciones (.jsonl) en el backup"
        return result

    result["collections"] = collections
    result["valid"] = True
    return result


def _count_documents_in_jsonl(file_path: str) -> int:
    """Cuenta documentos en un archivo JSONL"""
    count = 0
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    count += 1
    except Exception as e:
        logger.error(f"Error contando documentos en {file_path}: {e}")
    return count


def _import_collection(db, coll_name: str, jsonl_path: str, mode: str = "replace") -> Dict:
    """
    Importa una colección desde archivo JSONL

    Args:
        db: Instancia de base de datos
        coll_name: Nombre de la colección
        jsonl_path: Ruta al archivo .jsonl
        mode: "replace" (reemplaza todo) o "append" (añade documentos)

    Returns:
        dict con estadísticas de importación
    """
    result = {
        "success": False,
        "documents_read": 0,
        "documents_inserted": 0,
        "documents_failed": 0,
        "error": None
    }

    try:
        collection = db[coll_name]

        # Si mode es replace, eliminar colección existente
        if mode == "replace":
            collection.drop()
            logger.info(f"Colección '{coll_name}' eliminada para reemplazo")

        # Leer e insertar documentos en lotes
        batch_size = 1000
        batch = []

        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    doc = json_util.loads(line)
                    batch.append(doc)
                    result["documents_read"] += 1

                    # Insertar batch cuando alcance el tamaño
                    if len(batch) >= batch_size:
                        try:
                            collection.insert_many(batch, ordered=False)
                            result["documents_inserted"] += len(batch)
                            batch = []
                        except Exception as batch_error:
                            logger.error(f"Error insertando batch en {coll_name}: {batch_error}")
                            result["documents_failed"] += len(batch)
                            batch = []

                except Exception as doc_error:
                    logger.error(f"Error parseando documento en {coll_name}: {doc_error}")
                    result["documents_failed"] += 1

        # Insertar batch restante
        if batch:
            try:
                collection.insert_many(batch, ordered=False)
                result["documents_inserted"] += len(batch)
            except Exception as batch_error:
                logger.error(f"Error insertando último batch en {coll_name}: {batch_error}")
                result["documents_failed"] += len(batch)

        result["success"] = True

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Error importando colección {coll_name}: {e}")

    return result


def _executor_restore(folder_path: str, collections: List[str], mode: str) -> Dict:
    """
    Función bloqueante que realiza la restauración

    Args:
        folder_path: Ruta al directorio con los archivos extraídos
        collections: Lista de colecciones a restaurar
        mode: "replace" o "append"

    Returns:
        dict con resultados de la restauración
    """
    db = get_database()
    if db is None:
        raise RuntimeError("Base de datos no inicializada")

    results = {
        "total_collections": len(collections),
        "collections_success": 0,
        "collections_failed": 0,
        "total_documents_inserted": 0,
        "total_documents_failed": 0,
        "details": {}
    }

    for coll_name in collections:
        jsonl_path = os.path.join(folder_path, f"{coll_name}.jsonl")

        if not os.path.exists(jsonl_path):
            results["collections_failed"] += 1
            results["details"][coll_name] = {
                "success": False,
                "error": "Archivo no encontrado"
            }
            continue

        coll_result = _import_collection(db, coll_name, jsonl_path, mode)

        if coll_result["success"]:
            results["collections_success"] += 1
        else:
            results["collections_failed"] += 1

        results["total_documents_inserted"] += coll_result["documents_inserted"]
        results["total_documents_failed"] += coll_result["documents_failed"]
        results["details"][coll_name] = coll_result

    return results


async def db_restore_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler del comando /db_restore
    Permite restaurar un backup respondiendo a un mensaje con archivo ZIP
    """
    user = update.effective_user
    message = update.effective_message

    if not user:
        return

    # Verificar permisos
    if not is_admin(user.id):
        await message.reply_text(
            "⛔ <b>No autorizado</b>\n\n"
            "Solo administradores pueden ejecutar este comando.",
            parse_mode=ParseMode.HTML
        )
        return

    # Verificar si es una respuesta a un mensaje con documento
    document = None

    if message.reply_to_message and message.reply_to_message.document:
        # Caso 1: Respuesta a un mensaje con archivo
        document = message.reply_to_message.document
    elif message.document:
        # Caso 2: Mensaje directo con archivo adjunto
        document = message.document

    # Si no hay documento, mostrar instrucciones
    if not document:
        await message.reply_text(
            "📤 <b>Restaurar Backup de Base de Datos</b>\n\n"
            "Para restaurar un backup, responde con <code>/db_restore</code> a un mensaje que contenga el archivo ZIP del backup.\n\n"
            "⚠️ <b>Importante:</b>\n"
            "• Solo acepta backups creados con <code>/db_backup</code>\n"
            "• La restauración puede sobrescribir datos existentes\n"
            "• Asegúrate de tener un backup actual antes de restaurar\n\n"
            "<b>Ejemplo de uso:</b>\n"
            "1. Encuentra el mensaje con el archivo ZIP del backup\n"
            "2. Responde a ese mensaje con: <code>/db_restore</code>",
            parse_mode=ParseMode.HTML
        )
        return

    # Verificar que sea un archivo ZIP
    if not document.file_name.endswith('.zip'):
        await message.reply_text(
            "❌ <b>Archivo inválido</b>\n\n"
            "Solo se aceptan archivos ZIP creados con <code>/db_backup</code>",
            parse_mode=ParseMode.HTML
        )
        return

    msg = await message.reply_text("📥 Descargando backup...")

    try:
        # Descargar archivo
        file = await document.get_file()
        temp_dir = tempfile.mkdtemp(prefix="restore_")
        zip_path = os.path.join(temp_dir, document.file_name)

        await file.download_to_drive(zip_path)
        await msg.edit_text("📦 Extrayendo backup...")

        # Extraer ZIP
        extract_dir = os.path.join(temp_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        await _perform_restore_async(_extract_zip, zip_path, extract_dir)

        # Validar estructura
        await msg.edit_text("🔍 Validando estructura del backup...")
        validation = await _perform_restore_async(_validate_backup_structure, extract_dir)

        if not validation["valid"]:
            await msg.edit_text(
                f"❌ <b>Backup inválido</b>\n\n"
                f"Error: {validation['error']}",
                parse_mode=ParseMode.HTML
            )
            _cleanup_paths(temp_dir)
            return

        # Mostrar información del backup
        metadata = validation["metadata"]
        collections = validation["collections"]

        # Contar documentos totales
        total_docs = 0
        for coll in collections:
            jsonl_path = os.path.join(extract_dir, f"{coll}.jsonl")
            total_docs += await _perform_restore_async(_count_documents_in_jsonl, jsonl_path)

        backup_info = (
            f"📊 <b>Información del Backup</b>\n\n"
            f"📅 Creado: <code>{metadata.get('created_at_utc', 'N/A')}</code>\n"
            f"🗄️ Base de datos: <code>{metadata.get('mongodb_database', 'N/A')}</code>\n"
            f"📦 Colecciones: <code>{len(collections)}</code>\n"
            f"📄 Documentos totales: <code>{total_docs:,}</code>\n\n"
            f"<b>Colecciones encontradas:</b>\n"
        )

        # Limitar lista de colecciones a 10 para no hacer mensaje muy largo
        for i, coll in enumerate(collections[:10], 1):
            jsonl_path = os.path.join(extract_dir, f"{coll}.jsonl")
            doc_count = await _perform_restore_async(_count_documents_in_jsonl, jsonl_path)
            backup_info += f"  {i}. <code>{coll}</code> ({doc_count:,} docs)\n"

        if len(collections) > 10:
            backup_info += f"  <i>...y {len(collections) - 10} más</i>\n"

        # Guardar sesión de restauración
        session_id = f"{user.id}_{datetime.utcnow().timestamp()}"
        _restore_sessions[session_id] = {
            "user_id": user.id,
            "temp_dir": temp_dir,
            "extract_dir": extract_dir,
            "collections": collections,
            "metadata": metadata,
            "timestamp": datetime.utcnow()
        }

        # Botones de confirmación
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Restaurar TODO", callback_data=f"restore_all_{session_id}"),
                InlineKeyboardButton("📋 Seleccionar", callback_data=f"restore_select_{session_id}")
            ],
            [
                InlineKeyboardButton("❌ Cancelar", callback_data=f"restore_cancel_{session_id}")
            ]
        ])

        await msg.edit_text(
            backup_info +
            "\n⚠️ <b>¿Cómo deseas restaurar?</b>\n"
            "• <b>Restaurar TODO:</b> Reemplaza todas las colecciones\n"
            "• <b>Seleccionar:</b> Elige qué colecciones restaurar\n\n"
            "⚠️ Esta acción sobrescribirá datos existentes.",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Error en db_restore_command: {e}", exc_info=True)
        await msg.edit_text(
            f"❌ <b>Error procesando backup</b>\n\n"
            f"Error: <code>{str(e)[:200]}</code>",
            parse_mode=ParseMode.HTML
        )
        try:
            _cleanup_paths(temp_dir)
        except:
            pass


async def restore_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback para manejar las acciones de restauración"""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    data = query.data

    if not is_admin(user.id):
        await query.edit_message_text("⛔ No autorizado.")
        return

    try:
        if data.startswith("restore_cancel_"):
            session_id = data.replace("restore_cancel_", "")
            session = _restore_sessions.get(session_id)

            if session:
                _cleanup_paths(session.get("temp_dir"))
                del _restore_sessions[session_id]

            await query.edit_message_text(
                "❌ <b>Restauración cancelada</b>\n\n"
                "El backup no fue restaurado.",
                parse_mode=ParseMode.HTML
            )

        elif data.startswith("restore_all_"):
            session_id = data.replace("restore_all_", "")
            session = _restore_sessions.get(session_id)

            if not session or session["user_id"] != user.id:
                await query.edit_message_text("❌ Sesión inválida o expirada.")
                return

            await query.edit_message_text(
                "⏳ <b>Restaurando backup completo...</b>\n\n"
                "Esto puede tardar varios minutos.\n"
                "No cierres el bot ni interrumpas el proceso.",
                parse_mode=ParseMode.HTML
            )

            # Realizar restauración
            results = await _perform_restore_async(
                _executor_restore,
                session["extract_dir"],
                session["collections"],
                "replace"
            )

            # Limpiar
            _cleanup_paths(session.get("temp_dir"))
            del _restore_sessions[session_id]

            # Mostrar resultados
            result_text = (
                f"✅ <b>Restauración completada</b>\n\n"
                f"📊 <b>Resumen:</b>\n"
                f"• Colecciones procesadas: <code>{results['total_collections']}</code>\n"
                f"• Exitosas: <code>{results['collections_success']}</code>\n"
                f"• Fallidas: <code>{results['collections_failed']}</code>\n"
                f"• Documentos insertados: <code>{results['total_documents_inserted']:,}</code>\n"
                f"• Documentos fallidos: <code>{results['total_documents_failed']:,}</code>\n"
            )

            await query.edit_message_text(result_text, parse_mode=ParseMode.HTML)

        elif data.startswith("restore_select_"):
            await query.edit_message_text(
                "🚧 <b>Función en desarrollo</b>\n\n"
                "La selección individual de colecciones estará disponible pronto.\n"
                "Por ahora, usa 'Restaurar TODO' para restaurar el backup completo.",
                parse_mode=ParseMode.HTML
            )

    except Exception as e:
        logger.error(f"Error en restore_callback: {e}", exc_info=True)
        await query.edit_message_text(
            f"❌ <b>Error durante la restauración</b>\n\n"
            f"Error: <code>{str(e)[:200]}</code>",
            parse_mode=ParseMode.HTML
        )


def _cleanup_paths(*paths):
    """Limpia directorios y archivos temporales"""
    for p in paths:
        try:
            if os.path.isdir(p):
                shutil.rmtree(p)
            elif os.path.isfile(p):
                os.remove(p)
        except Exception as e:
            logger.warning(f"Error limpiando {p}: {e}")


async def cleanup_expired_sessions():
    """Limpia sesiones de restauración expiradas (más de 1 hora)"""
    from datetime import timedelta

    now = datetime.utcnow()
    expired = []

    for session_id, session in _restore_sessions.items():
        if now - session["timestamp"] > timedelta(hours=1):
            expired.append(session_id)
            _cleanup_paths(session.get("temp_dir"))

    for session_id in expired:
        del _restore_sessions[session_id]

    if expired:
        logger.info(f"Limpiadas {len(expired)} sesiones de restauración expiradas")


async def _job_cleanup(context: ContextTypes.DEFAULT_TYPE):
    """Wrapper para ejecutar cleanup_expired_sessions() en el job queue"""
    await cleanup_expired_sessions()


def register_db_restore_handler(application: Application):
    """Registra el handler /db_restore en la aplicación"""
    application.add_handler(CommandHandler("db_restore", db_restore_command))
    application.add_handler(CallbackQueryHandler(restore_callback, pattern="^restore_(all|select|cancel)_"))

    # Programar limpieza de sesiones expiradas cada 30 minutos
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(
            _job_cleanup,
            interval=1800,  # 30 minutos
            first=60  # Primera ejecución después de 1 minuto
        )