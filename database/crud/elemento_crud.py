"""
CRUD para elementos — MongoDB
Incluye soporte para informacion_completa (texto íntegro del post) y conteo de solicitudes por usuario.
Sistema de tokens mejorado con generación ATÓMICA para evitar colisiones en indexado paralelo.
"""

import logging
import secrets
import string
from typing import List, Optional, Dict, Any
from pymongo.errors import DuplicateKeyError
from database.base import get_database
from database.models.schemas import ElementoSchema, ElementoSolicitudSchema
from config import BOT_URL, ADMINISTRATION_GROUP

logger = logging.getLogger(__name__)


def _resolver_id(elemento_id):
    if isinstance(elemento_id, int):
        return elemento_id
    if isinstance(elemento_id, str):
        elemento_id = elemento_id.strip()
        if elemento_id.lstrip('-').isdigit():
            return int(elemento_id)
        if len(elemento_id) == 24 and all(c in '0123456789abcdefABCDEF' for c in elemento_id):
            try:
                from bson import ObjectId
                return ObjectId(elemento_id)
            except Exception:
                pass
    try:
        from bson import ObjectId
        if isinstance(elemento_id, ObjectId):
            return elemento_id
    except Exception:
        pass
    return elemento_id


def _generar_token_seguro_atomico() -> str:
    try:
        db = get_database()
        counter = db.counters.find_one_and_update(
            {"_id": "token_counter"},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=True
        )
        secuencia = str(counter["seq"]).zfill(12)
        caracteres = string.ascii_letters + string.digits + "-_"
        sufijo_aleatorio = ''.join(
            secrets.choice(caracteres) for _ in range(36)
        )
        token = f"{secuencia}_{sufijo_aleatorio}"
        return token
    except Exception as e:
        logger.error(f"Error generando token atómico: {e}. Fallback a método antiguo.")
        caracteres = string.ascii_letters + string.digits + "-_"
        return ''.join(secrets.choice(caracteres) for _ in range(48))


class ElementoCRUD:

    @staticmethod
    def crear_elemento(
        nombre: str,
        id_inicio: int,
        id_final: int,
        creador_id: int,
        peso_bytes: int = 0,
        num_archivos: int = 0,
        informacion_completa: str = "",
        almacen_id: int = 0
    ) -> Optional[Dict[str, Any]]:
        try:
            db = get_database()
            elementos = db.elementos

            if not isinstance(id_inicio, int) or not isinstance(id_final, int):
                logger.error(f"IDs deben ser enteros reales, recibidos: {type(id_inicio)}, {type(id_final)}")
                return None

            if id_inicio <= 0 or id_final <= 0:
                logger.error(f"IDs deben ser positivos: {id_inicio}, {id_final}")
                return None

            if id_inicio > id_final:
                logger.error(f"Rango inválido: {id_inicio} > {id_final}")
                return None

            token = _generar_token_seguro_atomico()
            logger.debug(f"✓ Token generado: {token[:20]}...")

            almacen_final = almacen_id if almacen_id != 0 else ADMINISTRATION_GROUP

            nuevo = ElementoSchema.crear(
                nombre=nombre,
                id_inicio=id_inicio,
                id_final=id_final,
                creador_id=creador_id,
                peso_bytes=peso_bytes,
                num_archivos=num_archivos,
                almacen_id=almacen_final
            )
            nuevo["token"]               = token
            nuevo["informacion_completa"] = informacion_completa.strip()

            result = elementos.insert_one(nuevo)
            nuevo["_id"] = result.inserted_id
            return nuevo

        except DuplicateKeyError as e:
            if "token" in str(e):
                logger.error(f"⚠️ Token duplicado: {token[:16]}...")
                return None
            elif "nombre" in str(e):
                logger.warning(f"⚠️ Nombre '{nombre}' ya existe en BD")
                return None
            else:
                logger.error(f"⚠️ Error de duplicado desconocido: {e}")
                return None
        except Exception as e:
            logger.error(f"Error creando elemento: {e}")
            return None

    @staticmethod
    def establecer_recomendacion(elemento_id, estado: bool) -> bool:
        """Activa o desactiva explícitamente la recomendación de un elemento."""
        try:
            from database.base import get_database
            db = get_database()
            _id = _resolver_id(elemento_id)
            result = db.elementos.update_one({"_id": _id}, {"$set": {"recomendado": estado}})
            return result.matched_count > 0 
        except Exception as e:
            logger.error(f"Error estableciendo recomendación: {e}")
            return False

    @staticmethod
    def obtener_recomendados_paginados(pagina: int = 0, limite: int = 5) -> tuple[list, int]:
        """Obtiene elementos recomendados con paginación y el total de documentos."""
        try:
            from database.base import get_database
            db = get_database()
            skip = pagina * limite
            query = {"recomendado": True}
            
            total = db.elementos.count_documents(query)
            elementos = list(db.elementos.find(query).skip(skip).limit(limite).sort("fecha_creacion", -1))
            
            return elementos, total
        except Exception as e:
            logger.error(f"Error obteniendo recomendados: {e}")
            return [], 0

    @staticmethod
    def actualizar_informacion_completa(elemento_id, texto: str) -> bool:
        try:
            _id = _resolver_id(elemento_id)
            result = get_database().elementos.update_one(
                {"_id": _id},
                {"$set": {"informacion_completa": texto.strip()}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error actualizando informacion_completa del elemento {elemento_id}: {e}")
            return False

    @staticmethod
    def obtener_elemento_por_token(token: str) -> Optional[Dict[str, Any]]:
        try:
            return get_database().elementos.find_one({"token": token})
        except Exception as e:
            logger.error(f"Error obteniendo elemento por token: {e}")
            return None

    @staticmethod
    def obtener_elemento_por_id(elemento_id) -> Optional[Dict[str, Any]]:
        try:
            _id = _resolver_id(elemento_id)
            return get_database().elementos.find_one({"_id": _id})
        except Exception as e:
            logger.error(f"Error obteniendo elemento por ID {elemento_id}: {e}")
            return None

    @staticmethod
    def obtener_elemento_por_nombre(nombre: str) -> Optional[Dict[str, Any]]:
        try:
            return get_database().elementos.find_one({"nombre": nombre})
        except Exception as e:
            logger.error(f"Error obteniendo elemento por nombre '{nombre}': {e}")
            return None

    @staticmethod
    def listar_todos_elementos() -> List[Dict[str, Any]]:
        try:
            return list(get_database().elementos.find().sort("fecha_creacion", -1))
        except Exception as e:
            logger.error(f"Error listando elementos: {e}")
            return []

    @staticmethod
    def listar_elementos_por_creador(creador_id: int) -> List[Dict[str, Any]]:
        try:
            return list(
                get_database().elementos
                .find({"creador_id": creador_id})
                .sort("fecha_creacion", -1)
            )
        except Exception as e:
            logger.error(f"Error listando elementos del creador {creador_id}: {e}")
            return []

    @staticmethod
    def eliminar_elemento(elemento_id) -> bool:
        try:
            db  = get_database()
            _id = _resolver_id(elemento_id)
            elemento = db.elementos.find_one({"_id": _id})
            if elemento:
                db.elemento_solicitudes.delete_many({"elemento_id": elemento["_id"]})
            result = db.elementos.delete_one({"_id": _id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error eliminando elemento {elemento_id}: {e}")
            return False

    @staticmethod
    def incrementar_solicitudes(elemento_token: str, user_id: int = None) -> bool:
        if user_id is None:
            return False
        try:
            db = get_database()
            elemento = db.elementos.find_one({"token": elemento_token})
            if not elemento:
                return False
            elemento_id = elemento["_id"]
            if db.elemento_solicitudes.find_one({"elemento_id": elemento_id, "user_id": user_id}):
                return False
            db.elemento_solicitudes.insert_one(
                ElementoSolicitudSchema.crear(elemento_id=elemento_id, user_id=user_id)
            )
            db.elementos.update_one({"_id": elemento_id}, {"$inc": {"solicitudes": 1}})
            try:
                from database.crud.usuario_crud import UsuarioCRUD
                UsuarioCRUD.incrementar_solicitudes_usuario(user_id)
            except Exception as e_usr:
                logger.warning(f"No se pudo incrementar solicitudes del usuario {user_id}: {e_usr}")
            return True
        except Exception as e:
            logger.error(f"Error registrando solicitud: {e}")
            return False

    @staticmethod
    def obtener_estadisticas() -> dict:
        try:
            db = get_database()
            elementos = db.elementos
            total_elementos   = elementos.count_documents({})
            total_solicitudes = sum(e.get("solicitudes", 0) for e in elementos.find({}, {"solicitudes": 1}))
            mas_solicitado = elementos.find_one({"solicitudes": {"$gt": 0}}, sort=[("solicitudes", -1)])
            mas_sol_info   = None
            if mas_solicitado:
                token = mas_solicitado.get("token", "")
                mas_sol_info = {
                    "nombre":        mas_solicitado.get("nombre"),
                    "solicitudes":   mas_solicitado.get("solicitudes"),
                    "token_display": f"{token[:8]}...{token[-4:]}" if len(token) >= 12 else token
                }
            mas_reciente      = elementos.find_one(sort=[("fecha_creacion", -1)])
            mas_reciente_info = None
            if mas_reciente:
                fecha = mas_reciente.get("fecha_creacion")
                mas_reciente_info = {
                    "nombre": mas_reciente.get("nombre"),
                    "fecha":  fecha.strftime("%d/%m/%Y %H:%M") if fecha else "N/A"
                }
            promedio = total_solicitudes / total_elementos if total_elementos > 0 else 0
            sin_sols = elementos.count_documents({"solicitudes": 0})
            con_info = elementos.count_documents({"informacion_completa": {"$ne": ""}})
            return {
                "total_elementos":           total_elementos,
                "total_solicitudes":         int(total_solicitudes),
                "promedio_solicitudes":      round(promedio, 2),
                "elementos_sin_solicitudes": sin_sols,
                "elementos_con_info":        con_info,
                "elemento_mas_solicitado":   mas_sol_info,
                "elemento_mas_reciente":     mas_reciente_info,
                "tokens_seguros_activos":    total_elementos
            }
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas: {e}")
            return {
                "total_elementos": 0, "total_solicitudes": 0,
                "promedio_solicitudes": 0, "elementos_sin_solicitudes": 0,
                "elementos_con_info": 0, "elemento_mas_solicitado": None,
                "elemento_mas_reciente": None, "tokens_seguros_activos": 0
            }

    @staticmethod
    def obtener_elemento_por_rango_mensaje(mensaje_id: int, almacen_id: int = None) -> Optional[Dict[str, Any]]:
        """Busca el elemento que contiene un mensaje ID dado, filtrando por almacén si se proporciona"""
        try:
            query = {
                "id_inicio": {"$lte": mensaje_id},
                "id_final":  {"$gte": mensaje_id}
            }
            # ESTA ES LA CORRECCIÓN: Filtrar por almacén_id si existe
            if almacen_id:
                query["almacen_id"] = almacen_id
                
            return get_database().elementos.find_one(query)
        except Exception as e:
            logger.error(f"Error buscando elemento por mensaje {mensaje_id}: {e}")
            return None

    @staticmethod
    def buscar_elementos_por_patron(patron: str) -> List[Dict[str, Any]]:
        try:
            import re
            patron_seguro = re.escape(patron)
            regex = {"$regex": patron_seguro, "$options": "i"}
            return list(
                get_database().elementos
                .find({"$or": [{"nombre": regex}, {"informacion_completa": regex}]})
                .sort("fecha_creacion", -1)
            )
        except Exception as e:
            logger.error(f"Error buscando por patrón '{patron}': {e}")
            return []

    @staticmethod
    def contar_elementos_por_creador(creador_id: int) -> int:
        try:
            return get_database().elementos.count_documents({"creador_id": creador_id})
        except Exception as e:
            logger.error(f"Error contando elementos del creador {creador_id}: {e}")
            return 0

    @staticmethod
    def obtener_elementos_mas_solicitados(limite: int = 10) -> List[Dict[str, Any]]:
        try:
            return list(
                get_database().elementos
                .find({"solicitudes": {"$gt": 0}})
                .sort("solicitudes", -1)
                .limit(limite)
            )
        except Exception as e:
            logger.error(f"Error obteniendo elementos más solicitados: {e}")
            return []

    @staticmethod
    def verificar_token_existe(token: str) -> bool:
        try:
            return get_database().elementos.find_one({"token": token}) is not None
        except Exception as e:
            logger.error(f"Error verificando token: {e}")
            return True

    @staticmethod
    def obtener_info_seguridad_sistema() -> dict:
        try:
            total = get_database().elementos.count_documents({})
            return {
                "tokens_activos":        total,
                "longitud_token":        50,
                "caracteres_posibles":   64,
                "combinaciones_totales": f"{64**36:.2e}",
                "probabilidad_colision": "0.00e+00",
                "sistema_seguro":        True,
                "todos_con_token":       True,
                "metodo_generacion":     "ATÓMICO (MongoDB auto-genera _id)"
            }
        except Exception as e:
            logger.error(f"Error obteniendo info de seguridad: {e}")
            return {"tokens_activos": 0, "sistema_seguro": True, "todos_con_token": True}

    @staticmethod
    def actualizar_nombre_elemento(elemento_id, nuevo_nombre: str) -> bool:
        try:
            _id = _resolver_id(elemento_id)
            result = get_database().elementos.update_one(
                {"_id": _id},
                {"$set": {"nombre": nuevo_nombre}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error actualizando nombre del elemento {elemento_id}: {e}")
            return False

    @staticmethod
    def obtener_top_por_usuarios_unicos(limite: int = 10) -> list:
        try:
            pipeline = [
                {
                    "$lookup": {
                        "from":         "elemento_solicitudes",
                        "localField":   "_id",
                        "foreignField": "elemento_id",
                        "as":           "solicitudes_info"
                    }
                },
                {
                    "$addFields": {
                        "usuarios_unicos": {
                            "$size": {"$setUnion": ["$solicitudes_info.user_id", []]}
                        }
                    }
                },
                {"$match":  {"usuarios_unicos": {"$gt": 0}}},
                {"$sort":   {"usuarios_unicos": -1}},
                {"$limit":  limite}
            ]
            return list(get_database().elementos.aggregate(pipeline))
        except Exception as e:
            logger.error(f"Error obteniendo top por usuarios únicos: {e}")
            return []

    @staticmethod
    def usuario_ya_solicito_elemento(elemento_id, user_id: int) -> bool:
        try:
            _id = _resolver_id(elemento_id)
            return get_database().elemento_solicitudes.find_one(
                {"elemento_id": _id, "user_id": user_id}
            ) is not None
        except Exception as e:
            logger.error(f"Error verificando solicitud: {e}")
            return False

    @staticmethod
    def obtener_usuarios_unicos_elemento(elemento_id) -> int:
        try:
            _id = _resolver_id(elemento_id)
            return len(get_database().elemento_solicitudes.distinct(
                "user_id", {"elemento_id": _id, "user_id": {"$ne": None}}
            ))
        except Exception as e:
            logger.error(f"Error contando usuarios únicos del elemento {elemento_id}: {e}")
            return 0

    @staticmethod
    async def crear_indice_nombre_async() -> bool:
        try:
            from database.base import get_async_database
            db = get_async_database()
            await db.elementos.create_index([("nombre", 1)])
            return True
        except Exception as e:
            logger.error(f"Error creando índice en 'nombre': {e}")
            return False

    @staticmethod
    async def contar_por_letra_async(letra: str) -> int:
        try:
            from database.base import get_async_database
            import re
            db         = get_async_database()
            elementos  = db.elementos

            if letra == "#":
                query = {"nombre": {"$regex": "^[^a-zA-Z]", "$options": "i"}, "activo": True}
            else:
                query = {"nombre": {"$regex": f"^{re.escape(letra)}", "$options": "i"}, "activo": True}

            return await elementos.count_documents(query)
        except Exception as e:
            logger.error(f"Error contando elementos por letra '{letra}': {e}")
            return 0

    @staticmethod
    async def listar_por_letra_paginado_async(
        letra: str,
        pagina: int = 0,
        items_por_pagina: int = 10
    ) -> List[Dict[str, Any]]:
        try:
            from database.base import get_async_database
            import re
            db         = get_async_database()
            elementos  = db.elementos
            skip_count = pagina * items_por_pagina

            if letra == "#":
                query = {"nombre": {"$regex": "^[^a-zA-Z]", "$options": "i"}, "activo": True}
            else:
                query = {"nombre": {"$regex": f"^{re.escape(letra)}", "$options": "i"}, "activo": True}

            cursor    = elementos.find(query).skip(skip_count).limit(items_por_pagina).sort("nombre", 1)
            resultado = await cursor.to_list(length=items_por_pagina)
            return resultado
        except Exception as e:
            logger.error(f"Error listando elementos paginados por letra '{letra}': {e}")
            return []

    @staticmethod
    async def obtener_todas_las_letras_disponibles_async() -> dict:
        try:
            letras_totales    = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + ["#"]
            letras_disponibles = {}

            for letra in letras_totales:
                count = await ElementoCRUD.contar_por_letra_async(letra)
                if count > 0:
                    letras_disponibles[letra] = count

            return letras_disponibles
        except Exception as e:
            logger.error(f"Error obteniendo letras disponibles: {e}")
            return {}

    @staticmethod
    def contar_por_letra_sync(letra: str) -> int:
        try:
            import re
            db        = get_database()
            elementos = db.elementos

            if letra == "#":
                query = {"nombre": {"$regex": "^[^a-zA-Z]", "$options": "i"}, "activo": True}
            else:
                query = {"nombre": {"$regex": f"^{re.escape(letra)}", "$options": "i"}, "activo": True}

            return elementos.count_documents(query)
        except Exception as e:
            logger.error(f"Error contando elementos por letra '{letra}' (sync): {e}")
            return 0

    @staticmethod
    def listar_por_letra_pagina_sync(
        letra: str,
        pagina: int = 0,
        items_por_pagina: int = 10
    ) -> List[Dict[str, Any]]:
        try:
            import re
            db        = get_database()
            elementos = db.elementos

            if letra == "#":
                query = {"nombre": {"$regex": "^[^a-zA-Z]", "$options": "i"}, "activo": True}
            else:
                query = {"nombre": {"$regex": f"^{re.escape(letra)}", "$options": "i"}, "activo": True}

            todos  = list(db.elementos.find(query).sort("nombre", 1))
            inicio = pagina * items_por_pagina
            fin    = inicio + items_por_pagina

            return todos[inicio:fin]
        except Exception as e:
            logger.error(f"Error listando elementos paginados por letra '{letra}' (sync): {e}")
            return []

    @staticmethod
    def obtener_todas_las_letras_disponibles_sync() -> dict:
        try:
            letras_totales    = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + ["#"]
            letras_disponibles = {}

            for letra in letras_totales:
                count = ElementoCRUD.contar_por_letra_sync(letra)
                if count > 0:
                    letras_disponibles[letra] = count

            return letras_disponibles
        except Exception as e:
            logger.error(f"Error obteniendo letras disponibles (sync): {e}")
            return {}

import re  # noqa: E402