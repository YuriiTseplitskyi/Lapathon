from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from ingestion_job.app.models.schemas import EntitySchema, EntityPropertySchema, RegisterSchema, RegisterSchemaVariant, RelationshipSchema
from ingestion_job.app.services.schema.base import BaseSchemaRegistry
from ingestion_job.app.services.schema.service import resolve_variant_impl

class JsonSchemaRegistry(BaseSchemaRegistry):
    def __init__(self, schemas_dir: Path):
        self.schemas_dir = schemas_dir
        self._entity_schemas: Dict[str, EntitySchema] = {}
        self._register_schemas: List[RegisterSchema] = []
        self._relationship_schemas: List[RelationshipSchema] = []

    def load(self) -> None:
        # Load entity schemas (individual JSON files)
        self._entity_schemas = {}
        for file in self.schemas_dir.glob("*.json"):
            if file.stem.startswith("_") or file.stem in ("register_schemas", "entity_schemas", "relationship_schemas"):
                continue
            
            data = json.loads(file.read_text("utf-8"))
            
            # Check if it's an entity schema or register schema
            if "entity_name" in data:
                schema = EntitySchema.model_validate(data)
                self._entity_schemas[schema.entity_name] = schema
            elif "registry_code" in data:
                schema = RegisterSchema.model_validate(data)
                self._register_schemas.append(schema)
            elif "relationship_name" in data:
                schema = RelationshipSchema.model_validate(data)
                self._relationship_schemas.append(schema)

    @property
    def register_schemas(self) -> List[RegisterSchema]:
        return self._register_schemas

    @property
    def entity_schemas(self) -> Dict[str, EntitySchema]:
        return self._entity_schemas

    @property
    def relationship_schemas(self) -> List[RelationshipSchema]:
        return self._relationship_schemas

    def resolve_variant(self, canonical_doc: Dict[str, Any]) -> Tuple[Optional[RegisterSchemaVariant], Dict[str, Any]]:
        return resolve_variant_impl(canonical_doc, self._register_schemas)
