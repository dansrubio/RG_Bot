"""
Configuración central de la base de datos MongoDB
Compatible con MongoDB Atlas y MongoDB local
Soporta tanto pymongo sincrónico como motor (async)
"""

import logging
from pymongo import MongoClient, ASCENDING, DESCENDING, TEXT
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError, OperationFailure
from contextlib import contextmanager
from typing import Optional

try:
    from motor.motor_asyncio import AsyncIOMotorClient
    MOTOR_AVAILABLE = True
except ImportError:
    MOTOR_AVAILABLE = False
    AsyncIOMotorClient = None

client: Optional[MongoClient] = None
db = None
async_client: Optional[AsyncIOMotorClient] = None
async_db = None


def init_database(mongodb_uri: str, database_name: str) -> bool:
    """Inicializa la conexión a MongoDB (compatible con Atlas y local)"""
    global client, db
    try:
        es_atlas = mongodb_uri.startswith('mongodb+srv://') or 'mongodb.net' in mongodb_uri

        if es_atlas:
            client = MongoClient(
                mongodb_uri,
                serverSelectionTimeoutMS=15000,
                connectTimeoutMS=20000,
                socketTimeoutMS=20000,
                retryWrites=True,
                w='majority',
                maxPoolSize=50,
                minPoolSize=10
            )
        else:
            client = MongoClient(
                mongodb_uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
                socketTimeoutMS=10000,
                maxPoolSize=20
            )

        client.admin.command('ping')  # Verificar conexión activa
        db = client[database_name]
        return True

    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        logging.error(f"⛔ Error conectando a MongoDB: {e}")
        logging.error("💡 Verifica URI, IP autorizada, credenciales y servicio activo")
        return False
    except Exception as e:
        logging.error(f"⛔ Error inesperado inicializando MongoDB: {e}")
        return False


def _deduplicate_elemento_solicitudes() -> int:
    """
    Elimina duplicados en elemento_solicitudes basado en (elemento_id, user_id).
    Mantiene el documento más antiguo por timestamp.
    """
    if db is None:
        raise RuntimeError("Base de datos no inicializada")

    coll = db.elemento_solicitudes
    try:
        pipeline = [
            {"$group": {
                "_id":   {"elemento_id": "$elemento_id", "user_id": "$user_id"},
                "count": {"$sum": 1},
                "ids":   {"$push": "$_id"}
            }},
            {"$match": {"count": {"$gt": 1}}}
        ]

        duplicates    = list(coll.aggregate(pipeline))
        total_deleted = 0

        if not duplicates:
            logging.debug("✅ No se encontraron duplicados en elemento_solicitudes")
            return 0

        logging.info(f"⚠️ {len(duplicates)} claves duplicadas detectadas en elemento_solicitudes")

        for dup in duplicates:
            ids  = dup.get("ids", [])
            docs = list(coll.find({"_id": {"$in": ids}}).sort("timestamp", 1))  # Ordenar por antigüedad
            ids_to_delete = [d["_id"] for d in docs[1:]]  # Mantener el primero (más antiguo)
            if ids_to_delete:
                res = coll.delete_many({"_id": {"$in": ids_to_delete}})
                total_deleted += res.deleted_count

        logging.info(f"🧹 {total_deleted} documentos duplicados eliminados")
        return total_deleted

    except Exception as e:
        logging.error(f"⛔ Error deduplicando elemento_solicitudes: {e}")
        return 0


def create_indexes():
    """
    Crea índices optimizados para las colecciones activas.
    Nota: la colección giveaways fue eliminada del sistema.
    """
    try:
        if db is None:
            raise RuntimeError("Base de datos no inicializada")

        # ── Usuarios (schema simplificado: _id, username, name, solicitudes) ──
        db.usuarios.create_index([("username",    ASCENDING)])
        db.usuarios.create_index([("solicitudes", DESCENDING)])  # Para top de usuarios
        logging.debug("✓ Índices de usuarios creados")

        # ── Elementos ────────────────────────────────────────────────────────
        try:
            db.elementos.create_index([("token",  ASCENDING)], unique=True)
            db.elementos.create_index([("nombre", ASCENDING)], unique=True)
            db.elementos.create_index([("id_inicio",      ASCENDING)])
            db.elementos.create_index([("id_final",       ASCENDING)])
            db.elementos.create_index([("fecha_creacion", DESCENDING)])
            db.elementos.create_index([("solicitudes",    DESCENDING)])  # Para top de elementos
            logging.debug("✓ Índices de elementos creados")
        except OperationFailure as e:
            logging.warning(f"⚠️ Algunos índices de elementos ya existían: {e}")

        # ── Índice de texto para búsqueda completa ───────────────────────────
        # Permite búsquedas en nombre e informacion_completa simultáneamente
        try:
            db.elementos.create_index([
                ("nombre",               TEXT),
                ("informacion_completa", TEXT)
            ], name="elementos_texto_idx", default_language="spanish")
            logging.debug("✓ Índice de texto completo creado")
        except OperationFailure as e:
            logging.warning(f"⚠️ Índice de texto ya existía o falló: {e}")

        # ── Elemento solicitudes ─────────────────────────────────────────────
        _deduplicate_elemento_solicitudes()  # Limpiar antes de crear índice único

        try:
            db.elemento_solicitudes.create_index([
                ("elemento_id", ASCENDING),
                ("user_id",     ASCENDING)
            ], unique=True)
            db.elemento_solicitudes.create_index([("timestamp", DESCENDING)])
            logging.debug("✓ Índices de solicitudes creados")
        except OperationFailure as e:
            logging.warning(f"⚠️ Falló índice único de solicitudes, reintentando: {e}")
            _deduplicate_elemento_solicitudes()
            try:
                db.elemento_solicitudes.create_index([
                    ("elemento_id", ASCENDING),
                    ("user_id",     ASCENDING)
                ], unique=True)
                logging.info("✅ Índice único creado tras segunda limpieza")
            except OperationFailure as e2:
                logging.error(f"❌ No se pudo crear índice único: {e2}")

        return True

    except OperationFailure as e:
        logging.error(f"⛔ Error creando índices (OperationFailure): {e}")
        return False
    except Exception as e:
        logging.error(f"⛔ Error creando índices: {e}")
        return False


def get_database():
    """Retorna la instancia activa de la base de datos"""
    if db is None:
        raise RuntimeError("Base de datos no inicializada. Ejecuta init_database() primero")
    return db


@contextmanager
def get_collection(collection_name: str):
    """Context manager para operaciones con colecciones específicas"""
    if db is None:
        raise RuntimeError("Base de datos no inicializada")
    try:
        yield db[collection_name]
    except Exception as e:
        logging.error(f"⛔ Error en colección '{collection_name}': {e}")
        raise


def close_database():
    """Cierra la conexión a MongoDB de forma segura"""
    global client, db
    try:
        if client:
            client.close()
            client = None
            db     = None
            logging.info("🔒 Conexión a MongoDB cerrada correctamente")
    except Exception as e:
        logging.error(f"⚠️ Error cerrando conexión: {e}")


def verificar_conexion() -> bool:
    """Verifica si la conexión a MongoDB está activa"""
    try:
        if client is None:
            return False
        client.admin.command('ping')
        return True
    except Exception:
        return False


def obtener_info_servidor() -> dict:
    """Obtiene información técnica del servidor MongoDB"""
    try:
        if client is None:
            return {"error": "Cliente no inicializado"}

        info   = client.server_info()
        status = client.admin.command("serverStatus")

        return {
            "version":               info.get("version", "Desconocida"),
            "conexiones_actuales":   status.get("connections", {}).get("current", 0),
            "conexiones_disponibles": status.get("connections", {}).get("available", 0),
            "uptime_segundos":       status.get("uptime", 0),
            "tipo": "Atlas" if "mongodb.net" in str(client.address) else "Local"
        }
    except Exception as e:
        logging.error(f"Error obteniendo info del servidor: {e}")
        return {"error": str(e)}


def obtener_estadisticas_db() -> dict:
    """Obtiene estadísticas generales de la base de datos activa"""
    try:
        if db is None:
            return {"error": "Base de datos no inicializada"}

        stats = db.command("dbStats")
        return {
            "nombre":             db.name,
            "colecciones":        stats.get("collections", 0),
            "documentos":         stats.get("objects", 0),
            "tamaño_datos_mb":    round(stats.get("dataSize", 0) / (1024 * 1024), 2),
            "tamaño_storage_mb":  round(stats.get("storageSize", 0) / (1024 * 1024), 2),
            "indices":            stats.get("indexes", 0),
            "tamaño_indices_mb":  round(stats.get("indexSize", 0) / (1024 * 1024), 2)
        }
    except Exception as e:
        logging.error(f"Error obteniendo estadísticas de BD: {e}")
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# ──── FUNCIONES ASYNC (Motor) ────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

def init_async_database(mongodb_uri: str, database_name: str) -> bool:
    """
    Inicializa la conexión async a MongoDB usando motor.
    Se puede llamar junto con init_database() para tener ambas conexiones disponibles.
    """
    global async_client, async_db
    
    if not MOTOR_AVAILABLE:
        logging.warning("⚠️ Motor no está instalado. Instala con: pip install motor")
        return False
    
    try:
        async_client = AsyncIOMotorClient(mongodb_uri)
        async_db = async_client[database_name]
        return True
    except Exception as e:
        logging.error(f"⛔ Error inicializando motor: {e}")
        return False


def get_async_database():
    """
    Retorna la instancia async de la base de datos (motor).
    Úsalo en funciones async para operaciones con MongoDB.
    """
    if async_db is None:
        raise RuntimeError("Base de datos async no inicializada. Ejecuta init_async_database() primero")
    return async_db


async def close_async_database():
    """Cierra la conexión async a MongoDB de forma segura"""
    global async_client, async_db
    try:
        if async_client:
            async_client.close()
            async_client = None
            async_db = None
            logging.info("🔒 Conexión async a MongoDB cerrada correctamente")
    except Exception as e:
        logging.error(f"⚠️ Error cerrando conexión async: {e}")