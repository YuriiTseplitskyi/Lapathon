from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Any

from ingestion_job.app.models.schemas import EntitySchema, RelationshipSchema, RegisterSchemaVariant, RegisterSchema

class BaseSchemaRegistry(ABC):
    @abstractmethod
    def load(self) -> None: ...
    @property
    @abstractmethod
    def register_schemas(self) -> List[RegisterSchema]: ...

    @property
    @abstractmethod
    def entity_schemas(self) -> Dict[str, EntitySchema]: ...
    @property
    @abstractmethod
    def relationship_schemas(self) -> List[RelationshipSchema]: ...
    @abstractmethod
    def resolve_variant(self, canonical_doc: Dict[str, Any]) -> Tuple[Optional[RegisterSchemaVariant], Dict[str, Any]]: ...
