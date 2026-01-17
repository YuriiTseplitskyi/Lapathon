import json
import os
from datetime import datetime
from pathlib import Path
from app.models.schema import Entity, MappingResponse
import json
from pathlib import Path
from app.models.schema import Entity

import json
import shutil
from pathlib import Path
from app.models.schema import Entity

class RegistryManager:
    def __init__(self, base_path: str = "registry_storage"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_version_number(self) -> int:
        """Визначає номер наступної версії на основі існуючих папок v1, v2..."""
        versions = [int(d.name[1:]) for d in self.base_path.glob("v*") if d.is_dir() and d.name[1:].isdigit()]
        return max(versions) if versions else 0

    def get_latest_registry(self) -> list[Entity]:
        """Завантажує схему з останньої папки vX"""
        last_ver = self._get_version_number()
        if last_ver == 0:
            return []
        
        schema_path = self.base_path / f"v{last_ver}" / "schema.json"
        if not schema_path.exists():
            return []

        with open(schema_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return [Entity(**e) for e in data]

    def save_version(self, registry_data: list[Entity], cross_reference: dict) -> str:
        """Зберігає схему та мапінг у нову директорію vX"""
        new_ver = self._get_version_number() + 1
        version_dir = self.base_path / f"v{new_ver}"
        version_dir.mkdir(parents=True, exist_ok=True)

        schema_path = version_dir / "schema.json"
        with open(schema_path, "w", encoding="utf-8") as f:
            json.dump([e.model_dump() for e in registry_data], f, indent=2, ensure_ascii=False)

        mapping_path = version_dir / "mapping_meta.json"
        with open(mapping_path, "w", encoding="utf-8") as f:
            json.dump(cross_reference, f, indent=2, ensure_ascii=False)

        return str(version_dir)