"""
CRUD simplificado para usuarios — MongoDB
Campos: _id (user_id), username, name, solicitudes
"""

import logging
from typing import Optional, Dict, Any
from database.base import get_database
from database.models.schemas import UsuarioSchema


class UsuarioCRUD:

    @staticmethod
    def crear_o_actualizar_usuario(
        user_id: int,
        username: str = None,
        name: str = None
    ) -> Optional[Dict[str, Any]]:
        """Crea el usuario si no existe; actualiza username/name si cambiaron"""
        try:
            db = get_database()
            usuarios = db.usuarios
            username_clean = username.lstrip('@') if username else None

            usuario_existente = usuarios.find_one({"_id": user_id})

            if usuario_existente:
                cambios = {}  # Solo actualiza los campos que llegaron
                if username_clean is not None:
                    cambios["username"] = username_clean
                if name is not None:
                    cambios["name"] = name

                if cambios:
                    usuarios.update_one({"_id": user_id}, {"$set": cambios})

                return usuarios.find_one({"_id": user_id})

            nuevo = UsuarioSchema.crear(  # Insertar usuario nuevo
                user_id=user_id,
                username=username_clean,
                name=name
            )
            usuarios.insert_one(nuevo)
            return nuevo

        except Exception as e:
            logging.error(f"Error crear/actualizar usuario: {e}")
            return None

    @staticmethod
    def obtener_usuario(user_id: int) -> Optional[Dict[str, Any]]:
        """Obtiene un usuario por su ID de Telegram"""
        try:
            return get_database().usuarios.find_one({"_id": user_id})
        except Exception as e:
            logging.error(f"Error obteniendo usuario {user_id}: {e}")
            return None

    @staticmethod
    def obtener_usuario_por_username(username: str) -> Optional[Dict[str, Any]]:
        """Obtiene un usuario por su username (con o sin @)"""
        try:
            username_clean = username.lstrip('@')
            return get_database().usuarios.find_one({"username": username_clean})
        except Exception as e:
            logging.error(f"Error obteniendo usuario por username '{username}': {e}")
            return None

    @staticmethod
    def incrementar_solicitudes_usuario(user_id: int) -> bool:
        """Suma 1 al contador de solicitudes del usuario (llamado desde ElementoCRUD)"""
        try:
            result = get_database().usuarios.update_one(
                {"_id": user_id},
                {"$inc": {"solicitudes": 1}}
            )
            return result.modified_count > 0
        except Exception as e:
            logging.error(f"Error incrementando solicitudes del usuario {user_id}: {e}")
            return False

    @staticmethod
    def obtener_top_usuarios(limite: int = 10) -> list:
        """Retorna los usuarios con más solicitudes acumuladas"""
        try:
            return list(
                get_database().usuarios
                .find({"solicitudes": {"$gt": 0}})
                .sort("solicitudes", -1)
                .limit(limite)
            )
        except Exception as e:
            logging.error(f"Error obteniendo top usuarios: {e}")
            return []