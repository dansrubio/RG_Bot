"""
Schemas para documentos MongoDB (estructura de datos)
"""

from datetime import datetime
from typing import Optional
import secrets
import string


class UsuarioSchema:
    """Schema simplificado — solo datos esenciales del usuario"""

    @staticmethod
    def crear(user_id: int, username: Optional[str] = None, name: Optional[str] = None) -> dict:
        """Crea un documento de usuario nuevo"""
        return {
            "_id":        user_id,   # ID de Telegram como clave primaria
            "username":   username,
            "name":       name,
            "solicitudes": 0         # Contador acumulado de solicitudes de elementos
        }


class ElementoSchema:
    """Schema para elementos del catálogo"""

    @staticmethod
    def generar_token_seguro() -> str:
        """Genera un token único y seguro de 32 caracteres"""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(32))

    @staticmethod
    def crear(
        nombre: str,
        id_inicio: int,
        id_final: int,
        creador_id: int,
        peso_bytes: int = 0,
        num_archivos: int = 0,
        almacen_id: int = 0
    ) -> dict:
        """
        Crea un documento de elemento nuevo.
        """
        return {
            "nombre":                nombre,
            "token":                 ElementoSchema.generar_token_seguro(),
            "id_inicio":             id_inicio,
            "id_final":              id_final,
            "creador_id":            creador_id,
            "almacen_id":            almacen_id,    # <-- NUEVO CAMPO
            "fecha_creacion":        datetime.utcnow(),
            "solicitudes":           0,
            "peso_bytes":            peso_bytes,    # tamaño total de los archivos del elemento
            "num_archivos":          num_archivos,  # cantidad de archivos del elemento
            "informacion_completa":  ""             # texto íntegro del post — se actualiza al indexar
        }


class ElementoSolicitudSchema:
    """Schema para solicitudes de elementos (registro por usuario único)"""

    @staticmethod
    def crear(elemento_id, user_id: int) -> dict:
        """Crea un documento de solicitud nuevo"""
        return {
            "elemento_id": elemento_id,  # Acepta cualquier tipo de _id (int, ObjectId, etc)
            "user_id":     user_id,
            "timestamp":   datetime.utcnow()
        }


class TicketSolicitudSchema:
    """Schema para tickets de solicitudes/reportes enviados por usuarios"""

    @staticmethod
    def crear(
            user_id: int,
            chat_id: int,
            message_id: int,
            categoria: str,
            texto: str,
            msg_privado_id: int = None,
            msg_admin_id: int = None
    ) -> dict:
        """Crea un documento de ticket activo"""
        return {
            "user_id":        user_id,
            "chat_id":        chat_id,
            "message_id":     message_id,
            "categoria":      categoria,
            "texto":          texto,
            "msg_privado_id": msg_privado_id,
            "msg_admin_id":   msg_admin_id,
            "estado":         "activo",
            "fecha_creacion": datetime.utcnow()
        }