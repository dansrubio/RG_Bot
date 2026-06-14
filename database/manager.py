"""
Gestor principal de base de datos MongoDB
Maneja tanto conexiones sincrónicas (pymongo) como asincrónicas (motor)
"""

import logging
import os
from database.base import (
    init_database,
    init_async_database,
    create_indexes,
    close_database,
    close_async_database
)

def get_database_config():
    """Obtiene la configuración de MongoDB desde variables de entorno"""
    mongodb_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    database_name = os.getenv("MONGODB_DATABASE", "rednite_bot")
    return mongodb_uri, database_name

def setup_database() -> bool:
    """
    Configura e inicializa MongoDB con ambas conexiones (sincrónica y asincrónica).
    
    - init_database: Para operaciones sincrónicas (pymongo)
    - init_async_database: Para operaciones async con paginación (motor)
    """
    try:
        mongodb_uri, database_name = get_database_config()

        if not mongodb_uri or not database_name:
            logging.error("❌ MONGODB_URI o MONGODB_DATABASE no configurado. Revisa tu .env.")
            return False

        # Inicializar conexión sincrónica
        if not init_database(mongodb_uri, database_name):
            return False

        # Inicializar conexión asincrónica (para paginación y consultas async)
        if not init_async_database(mongodb_uri, database_name):
            logging.info("⚠️ Motor no disponible - El catálogo usará fallback sincrónico")
            # No retornar False - el sistema funciona igual sin motor

        # Crear índices
        if not create_indexes():
            return False
        
        return True

    except Exception as e:
        logging.error(f"❌ Error configurando base de datos: {e}")
        return False

def shutdown_database():
    """Cierra conexiones de base de datos (sincrónica y asincrónica) de forma segura"""
    try:
        # Cerrar conexión sincrónica
        close_database()
        logging.info("🔒 Base de datos sincrónica cerrada correctamente")
        
        # Nota: close_async_database() es async y requiere await
        # Para llamarla desde aquí (contexto sincrónico), se hace en main_async
        logging.info("🔒 (Conexión async será cerrada en el shutdown del event loop)")
    except Exception as e:
        logging.error(f"❌ Error cerrando base de datos: {e}")