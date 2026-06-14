"""
Módulo para backup manual de la base de datos mediante comando /db_backup
"""

import os
import shutil
import tempfile
import zipfile
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from bson import json_util
from bson.objectid import ObjectId

from database.base import get_database, client as mongo_client
from database.manager import get_database_config
from config import is_admin

logger = logging.getLogger(__name__)


async def _perform_backup_async(executor_fn, *args, **kwargs):
    """
    Helper para ejecutar la función de backup en un hilo separado sin bloquear el loop async.
    """
    return await asyncio.to_thread(executor_fn, *args, **kwargs)


def _export_collection_with_session(db, coll_name: str, out_file_path: str, session):
    """
    Exporta colección usando un cursor con no_cursor_timeout y sesión.
    """
    with open(out_file_path, "w", encoding="utf-8") as f:
        cursor = None
        try:
            cursor = db[coll_name].find({}, no_cursor_timeout=True, session=session).batch_size(1000)
            for doc in cursor:
                f.write(json_util.dumps(doc))
                f.write("\n")
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:
                    pass


def _export_collection_by_pagination(db, coll_name: str, out_file_path: str, page_size: int = 1000):
    """
    Exporta colección por paginación usando _id para evitar cursores de larga vida.
    Esto es más seguro cuando no se usan sesiones (evita warning y timeouts).
    """
    with open(out_file_path, "w", encoding="utf-8") as f:
        last_id: Optional[ObjectId] = None
        while True:
            query = {}
            if last_id is not None:
                query["_id"] = {"$gt": last_id}

            docs = list(db[coll_name].find(query).sort("_id", 1).limit(page_size))
            if not docs:
                break

            for doc in docs:
                f.write(json_util.dumps(doc))
                f.write("\n")

            last_id = docs[-1].get("_id")
            # Si por alguna razón last_id no se obtuvo, rompemos para evitar bucle infinito
            if last_id is None:
                break


def _create_backup_folder(db, metadata_admin_id: Optional[int] = None) -> str:
    """
    Realiza la exportación de cada colección a archivos .jsonl dentro de un folder temporal.
    Retorna la ruta del folder creado.
    Implementa dos estrategias:
      1) Si el cliente Mongo soporta sesiones, usa start_session + no_cursor_timeout (sin warning)
      2) Si no, usa paginación por _id en bloques para evitar cursores de larga vida.
    """
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    temp_dir = tempfile.mkdtemp(prefix=f"db_backup_{timestamp}_")

    # Obtener metadata de configuración (desde get_database_config)
    mongodb_uri, mongodb_database = get_database_config()

    metadata = {
        "created_at_utc": datetime.utcnow().isoformat(),
        "mongodb_uri": mongodb_uri,
        "mongodb_database": mongodb_database,
        "requested_by_admin_id": metadata_admin_id
    }
    # Guardar metadata
    try:
        with open(os.path.join(temp_dir, "metadata.json"), "w", encoding="utf-8") as meta_f:
            json.dump(metadata, meta_f, indent=2)
    except Exception as e:
        logger.warning(f"No se pudo escribir metadata.json: {e}")

    # Intentar usar session si el cliente está disponible y soporta start_session
    use_session = False
    session_obj = None
    try:
        if mongo_client is not None and hasattr(mongo_client, "start_session"):
            # start_session puede lanzar si el servidor no soporta sesiones o por configuración
            session_obj = mongo_client.start_session()
            use_session = True
            logger.debug("Usando sessions para exportar colecciones (evita warning de no_cursor_timeout).")
    except Exception as e:
        logger.warning(f"No se pudo iniciar session en mongo_client: {e}. Se usará paginación por _id.")

    try:
        for coll_name in db.list_collection_names():
            file_path = os.path.join(temp_dir, f"{coll_name}.jsonl")
            try:
                if use_session and session_obj is not None:
                    # Exportar con sesión y cursor sin timeout
                    _export_collection_with_session(db, coll_name, file_path, session=session_obj)
                else:
                    # Exportar por paginación en bloques (sin usar no_cursor_timeout)
                    _export_collection_by_pagination(db, coll_name, file_path, page_size=1000)
            except Exception as e:
                logger.error(f"Error exportando colección {coll_name}: {e}")
                # escribir un archivo con el error para diagnóstico
                try:
                    with open(file_path + ".error.txt", "w", encoding="utf-8") as ef:
                        ef.write(str(e))
                except Exception:
                    pass
    finally:
        # Cerrar session si fue creada
        try:
            if session_obj is not None:
                session_obj.end_session()
        except Exception:
            pass

    return temp_dir


def _make_zip_from_folder(folder_path: str) -> str:
    """
    Crea un zip del folder y retorna la ruta del archivo zip creado.
    """
    base_dir = os.path.dirname(folder_path)
    folder_name = os.path.basename(folder_path)
    zip_name = f"{folder_name}.zip"
    zip_path = os.path.join(base_dir, zip_name)

    # Use ZIP_DEFLATED cuando esté disponible
    compression = zipfile.ZIP_DEFLATED if hasattr(zipfile, "ZIP_DEFLATED") else zipfile.ZIP_STORED

    with zipfile.ZipFile(zip_path, "w", compression=compression) as zipf:
        for root, _, files in os.walk(folder_path):
            for file in files:
                full_path = os.path.join(root, file)
                arcname = os.path.relpath(full_path, folder_path)
                zipf.write(full_path, arcname=arcname)
    return zip_path


def _cleanup_paths(*paths):
    for p in paths:
        try:
            if os.path.isdir(p):
                shutil.rmtree(p)
            elif os.path.isfile(p):
                os.remove(p)
        except Exception:
            # no queremos que el cleanup falle el flujo principal
            pass


def _executor_backup(admin_id: int) -> str:
    """
    Función bloqueante que realiza el backup completo y retorna la ruta del ZIP creado.
    Lanza excepciones hacia arriba en caso de fallo.
    """
    # Obtener instancia de la base de datos (debe estar inicializada por manager.setup_database)
    db = get_database()
    if db is None:
        raise RuntimeError("Base de datos no inicializada")

    folder = _create_backup_folder(db, metadata_admin_id=admin_id)
    zip_path = _make_zip_from_folder(folder)

    # Opcional: dejar el zip y eliminar la carpeta temporal para ahorrar espacio
    _cleanup_paths(folder)
    return zip_path


async def db_backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler del comando /db_backup. Permite que sólo administradores ejecuten el backup.
    Envía el ZIP resultante como documento al chat privado o grupo donde se ejecutó.
    """
    user = update.effective_user
    chat = update.effective_chat
    if not user:
        return

    user_id = user.id

    # Verificar permiso
    if not is_admin(user_id):
        try:
            await update.effective_message.reply_text("⛔ No autorizado. Sólo administradores pueden ejecutar este comando.")
        except Exception:
            pass
        return

    # Informar inicio
    msg = await update.effective_message.reply_text("🔄 Iniciando backup de la base de datos. Esto puede tardar según el tamaño de la BD...")

    try:
        # Ejecutar backup en hilo separado
        zip_path = await _perform_backup_async(_executor_backup, user_id)

        # Obtener nombre de BD para la leyenda (si está disponible)
        _, mongodb_database = get_database_config()

        # Enviar el archivo resultante
        caption = f"📦 Backup de la base de datos ({datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')})\n\n" \
                  f"Base de datos: {mongodb_database}\n" \
                  f"Solicitado por: @{user.username or user_id}"

        # Telegram limita el tamaño de los archivos; si el zip es demasiado grande fallará al enviar.
        # En ese caso devolvemos un mensaje informando la ubicación en servidor (si aplica).
        try:
            with open(zip_path, "rb") as doc:
                await update.effective_message.reply_document(document=doc, filename=os.path.basename(zip_path), caption=caption)
        except Exception as send_exc:
            # Intentar notificar el error de envío y proporcionar la ruta local del ZIP (el administrador ya tiene acceso)
            await update.effective_message.reply_text(
                "⚠️ El backup se creó correctamente pero no se pudo enviar por Telegram (fichero muy grande o error de envío).\n"
                f"Ruta del backup en el servidor: {zip_path}\n\n"
                "Descárgalo directamente desde el servidor si tienes acceso, o reduce el tamaño de la BD."
            )
            raise send_exc

        # Confirmación final
        await msg.edit_text("✅ Backup completado y enviado correctamente.")
    except Exception as e:
        # Informar error
        logger.exception("Error en db_backup_command")
        try:
            await msg.edit_text(f"❌ Error creando o enviando el backup: {e}")
        except Exception:
            pass
    finally:
        # No eliminamos el zip automáticamente aquí para no perderlo si hubo fallos de envío.
        pass


def register_db_backup_handler(application: Application):
    """
    Registra el handler /db_backup en la aplicación.
    Llamar a esta función desde main.HandlerRegistrar.register_admin(...) para integrarlo.
    """
    application.add_handler(CommandHandler("db_backup", db_backup_command))