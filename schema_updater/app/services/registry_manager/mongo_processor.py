import logging
from bson import ObjectId
from pymongo import MongoClient
from app.core.settings import settings
from app.services.registry_manager.schema_agent import SchemaAgent
from app.services.registry_manager.schema_evolver import SchemaEvolver
from app.services.registry_manager.registry_agent import RegistryManager
import certifi

logger = logging.getLogger("uvicorn.error")

def get_nested_value(data: dict, path: str):
    """
    Дозволяє діставати значення за шляхом 'key1.key2.key3'
    """
    keys = path.split('.')
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key)
            logging.info(f"data: {data}")
        else:
            return None
    return data

class MongoDiscoveryProcessor:
    def __init__(self):
        self.client = MongoClient(settings.MONGO_URI, tlsCAFile=certifi.where())
        self.db = self.client[settings.DATABASE_NAME]
        
        self.agent = SchemaAgent()
        self.evolver = SchemaEvolver()
        self.manager = RegistryManager()

    def process_by_checkpoint(self, doc_id_ref: str):
        """
        Головний ланцюжок дій: Mongo -> AI -> Evolution -> Storage
        """
        doc_data = self.db[settings.COLLECTION_DOCUMENTS].find_one({"document_id": doc_id_ref})
        
        canonical_json = get_nested_value(doc_data, settings.CANONICAL_FIELD)
    
        if canonical_json is None:
            raise ValueError(
                f"Шлях '{settings.CANONICAL_FIELD}' не знайдено в документі. "
                f"Перевірте структуру документа в MongoDB."
            )
        registry_code = get_nested_value(doc_data, settings.REGISTRY_CODE_FIELD)

        current_entities = self.manager.get_latest_registry() 

        ai_result = self.agent.analyze(canonical_json, current_entities, registry_code)

        logger.info(f"ai_result: {ai_result}")

        updated_entities, final_config = self.evolver.evolve(ai_result, current_entities)

        self.manager.save_version(updated_entities, {})

        return final_config