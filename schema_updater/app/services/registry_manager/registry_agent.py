import os
from datetime import datetime
import certifi
from pymongo import MongoClient
from app.core.settings import settings
import shutil
from pathlib import Path
import logging
import json
from app.models.schema import Entity, RegistryConfig

logger = logging.getLogger("uvicorn.error")

class RegistryManager:
    def __init__(self, base_path: str = "registry_storage"):
        self.base_path = Path(base_path)
        self.client = MongoClient(settings.MONGO_URI, tlsCAFile=certifi.where())
        self.db = self.client[settings.DATABASE_NAME]
        self.entities_col = self.db[settings.COLLECTION_ENTITIES]

    
    def _get_next_version(self, registry_path: Path) -> int:
        """Шукає наступну версію всередині конкретної папки реєстру"""
        if not registry_path.exists():
            return 1
        versions = [int(d.name[1:]) for d in registry_path.glob("v*") if d.is_dir() and d.name[1:].isdigit()]
        return max(versions) + 1 if versions else 1

    def get_latest_registry(self) -> list[Entity]:
        """Завантажує всі сутності з MongoDB замість файлу"""
        cursor = self.entities_col.find({})
        entities = []
        for doc in cursor:
            doc.pop('_id', None)
            entities.append(Entity(**doc))
        return entities


    def save_config_version(self, config: RegistryConfig) -> str:
        """
        Зберігає декларативний мапінг у форматі зі скриншоту.
        Шлях: registry_storage/{registry_code}/v{X}/config.json
        """
        registry_path = self.base_path / config.registry_code
        registry_path.mkdir(parents=True, exist_ok=True)

        new_ver = self._get_next_version(registry_path)
        version_dir = registry_path / f"v{new_ver}"
        version_dir.mkdir(parents=True, exist_ok=True)

        config_path = version_dir / "config.json"
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(config.model_dump_json(indent=2))

        logger.info(f"✅ Конфігурацію для {config.registry_code} збережено: {config_path}")
        return str(config_path)

    def save_version(self, registry_data: list[Entity], cross_reference: dict) -> str:
        """Старий метод для збереження глобальної схеми (залишаємо для сумісності)"""
        versions = [int(d.name[1:]) for d in self.base_path.glob("v*") if d.is_dir() and d.name[1:].isdigit()]
        new_ver = (max(versions) if versions else 0) + 1
        
        version_dir = self.base_path / f"v{new_ver}"
        version_dir.mkdir(parents=True, exist_ok=True)

        with open(version_dir / "schema.json", "w", encoding="utf-8") as f:
            json.dump([e.model_dump() for e in registry_data], f, indent=2, ensure_ascii=False)

        return str(version_dir)

