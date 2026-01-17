import json
import os
from typing import List, Dict, Any

class SchemaManager:
    def __init__(self, schemas_dir: str):
        self.schemas_dir = schemas_dir
        self.entity_types_path = os.path.join(schemas_dir, "entity_types.json")
        self.rel_schemas_path = os.path.join(schemas_dir, "relationship_schemas.json")
        
        self.entity_types = self._load_json(self.entity_types_path).get("entity_types", [])
        self.rel_schemas = self._load_json(self.rel_schemas_path).get("relationship_schemas", [])

    def _load_json(self, path: str) -> Dict[str, Any]:
        if os.path.exists(path):
            with open(path, "r") as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return {}
        return {}

    def _save_json(self, path: str, data: Dict[str, Any]):
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def get_entity_types(self) -> List[Dict[str, Any]]:
        return self.entity_types

    def register_new_entity_type(self, entity_name: str, primary_keys: List[str], description: str = ""):
        # Check if exists
        for et in self.entity_types:
            if et["entity_name"] == entity_name:
                return # Already exists

        print(f"  [Schema] Registering new entity type: {entity_name}")
        new_type = {
            "entity_name": entity_name,
            "primary_keys": primary_keys,
            "description": description
        }
        self.entity_types.append(new_type)
        self._save_json(self.entity_types_path, {"entity_types": self.entity_types})

    def register_new_relationship_type(self, rel_type: str):
        # Check if exists
        for rt in self.rel_schemas:
            if rt.get("name") == rel_type:
                return

        print(f"  [Schema] Registering new relationship type: {rel_type}")
        new_rel = {"name": rel_type, "description": "Auto-discovered"}
        self.rel_schemas.append(new_rel)
        # Assuming structure {"relationship_schemas": [...]} 
        # But previous spec might have been different. Let's stick to this.
        self._save_json(self.rel_schemas_path, {"relationship_schemas": self.rel_schemas})
