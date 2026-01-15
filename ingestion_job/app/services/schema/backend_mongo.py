from __future__ import annotations
from typing import Dict, List, Optional, Tuple, Any

from ingestion_job.app.models.schemas import EntitySchema, EntityPropertySchema, RegisterSchema, RegisterSchemaVariant, RelationshipSchema
from ingestion_job.app.services.schema.base import BaseSchemaRegistry
from ingestion_job.app.services.schema.service import resolve_variant_impl

try:
    from pymongo import MongoClient
except ImportError:
    MongoClient = None

class MongoSchemaRegistry(BaseSchemaRegistry):
    def __init__(self, mongo_uri: str, db_name: str):
        if MongoClient is None:
            raise RuntimeError("pymongo is not installed; install pymongo to use schema_backend=mongo")
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self._entity_schemas: Dict[str, EntitySchema] = {}
        self._register_schemas: List[RegisterSchema] = []
        self._relationship_schemas: List[RelationshipSchema] = []

    def load(self) -> None:
        self._entity_schemas = {}
        for e in self.db["entity_schemas"].find({}):
            e.pop("_id", None)
            schema = EntitySchema.model_validate(e)
            self._entity_schemas[schema.entity_name] = schema

        self._register_schemas = []
        for rs in self.db["register_schemas"].find({}):
            rs.pop("_id", None)
            schema = RegisterSchema.model_validate(rs)
            self._register_schemas.append(schema)

        self._relationship_schemas = []
        for r in self.db["relationship_schemas"].find({}):
            r.pop("_id", None)
            schema = RelationshipSchema.model_validate(r)
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
