"""
Gestor de juegos enviados usando MongoDB en lugar de JSON
Reemplaza la lectura/escritura del archivo sent_games.json
"""

import logging
from typing import List
from database.base import get_database

logger = logging.getLogger(__name__)


class SentGamesManager:
    """Gestiona los juegos enviados usando MongoDB"""
    
    COLLECTION_NAME = 'sent_games'
    
    @staticmethod
    def _get_collection():
        """Obtiene la colección de juegos enviados"""
        db = get_database()
        return db[SentGamesManager.COLLECTION_NAME]
    
    @classmethod
    def add_game(cls, game_id: str) -> bool:
        """Añade un juego a la lista de enviados"""
        try:
            collection = cls._get_collection()
            result = collection.insert_one({'game_id': game_id})
            return result.inserted_id is not None
        except Exception as e:
            logger.error(f"❌ Error añadiendo juego {game_id}: {e}")
            return False
    
    @classmethod
    def add_games_bulk(cls, game_ids: List[str]) -> int:
        """Añade múltiples juegos de forma eficiente"""
        if not game_ids:
            return 0
        
        try:
            collection = cls._get_collection()
            documents = [{'game_id': gid} for gid in game_ids]
            result = collection.insert_many(documents, ordered=False)
            return len(result.inserted_ids)
        except Exception as e:
            logger.error(f"❌ Error insertando juegos en bulk: {e}")
            return 0
    
    @classmethod
    def is_sent(cls, game_id: str) -> bool:
        """Verifica si un juego ya ha sido enviado"""
        try:
            collection = cls._get_collection()
            return collection.find_one({'game_id': game_id}) is not None
        except Exception as e:
            logger.error(f"❌ Error buscando juego {game_id}: {e}")
            return False
    
    @classmethod
    def get_all_sent_games(cls) -> List[str]:
        """Obtiene lista de todos los juegos enviados"""
        try:
            collection = cls._get_collection()
            games = collection.find({}, {'game_id': 1})
            return [doc['game_id'] for doc in games]
        except Exception as e:
            logger.error(f"❌ Error obteniendo juegos enviados: {e}")
            return []
    
    @classmethod
    def get_sent_games_count(cls) -> int:
        """Obtiene el total de juegos enviados"""
        try:
            collection = cls._get_collection()
            return collection.count_documents({})
        except Exception as e:
            logger.error(f"❌ Error contando juegos: {e}")
            return 0
    
    @classmethod
    def remove_game(cls, game_id: str) -> bool:
        """Elimina un juego de la lista de enviados"""
        try:
            collection = cls._get_collection()
            result = collection.delete_one({'game_id': game_id})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"❌ Error eliminando juego {game_id}: {e}")
            return False
    
    @classmethod
    def clear_all(cls) -> int:
        """Elimina todos los registros (usar con cuidado)"""
        try:
            collection = cls._get_collection()
            result = collection.delete_many({})
            return result.deleted_count
        except Exception as e:
            logger.error(f"❌ Error limpiando colección: {e}")
            return 0
