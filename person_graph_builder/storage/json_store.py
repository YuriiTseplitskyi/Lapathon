import os
import json
from typing import Dict, Any, List

class JSONStore:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        self.entities_dir = os.path.join(output_dir, "entities")
        self.relationships_dir = os.path.join(output_dir, "relationships")
        self.index_path = os.path.join(output_dir, "index.json")
        
        os.makedirs(self.entities_dir, exist_ok=True)
        os.makedirs(self.relationships_dir, exist_ok=True)
        
        self.index = self._load_index()

    def _load_index(self) -> Dict[str, Any]:
        if os.path.exists(self.index_path):
            with open(self.index_path, "r") as f:
                return json.load(f)
        return {"entities": {}, "relationships": []} # simple index

    def _save_index(self):
        with open(self.index_path, "w") as f:
            json.dump(self.index, f, indent=2)

    def upsert_node(self, label: str, properties: Dict[str, Any]):
        node_id = properties.get("id") or properties.get("code") or properties.get("rnokpp")
        
        if not node_id:
            # Generate deterministic hash as ID
            import hashlib
            prop_str = json.dumps(properties, sort_keys=True)
            node_id = hashlib.md5(prop_str.encode("utf-8")).hexdigest()
            print(f"  [Warning] Node of type '{label}' has no ID. Generated hash: {node_id}")
            # Ensure the generated ID is saved in properties so it persists
            properties["id"] = node_id
            
        node_id = str(node_id)
        
        # Path: entities/Label/id.json
        label_dir = os.path.join(self.entities_dir, label)
        os.makedirs(label_dir, exist_ok=True)
        file_path = os.path.join(label_dir, f"{node_id}.json")
        
        existing = {}
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                existing = json.load(f)
        
        # Merge properties
        existing.update(properties)
        existing["_label"] = label
        existing["_id"] = node_id
        
        with open(file_path, "w") as f:
            json.dump(existing, f, indent=2)
            
        # Update Index
        self.index["entities"][node_id] = {"label": label, "path": file_path}
        
    def upsert_relationship(self, rel: Dict[str, Any]):
        # rel: {type, from_label, from_id, to_label, to_id, properties}
        self.index["relationships"].append(rel)
        
    def close(self):
        self._save_index()
