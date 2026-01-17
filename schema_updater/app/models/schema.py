from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, ConfigDict


class FieldDefinition(BaseModel):
    name: str = Field(validation_alias="system_name")
    description: str
    type: str
    is_required: bool = True

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True
    )

class Entity(BaseModel):
    entity_name: str
    properties: List[FieldDefinition]

class AlignmentRequest(BaseModel):
    document: Any 
    registry: List[Entity]

class ProposedField(BaseModel):
    original_name: str
    system_name: str
    description: str
    type: str
    nullable: bool = True

class MappingResponse(BaseModel):
    identified_entity: str
    mappings: dict[str, str]
    proposed_fields: list[ProposedField]
    usage: dict = None
    registry_code: str

class UsageStats(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class Target(BaseModel):
    entity: str
    property: str
    entity_ref: Optional[str] = None
    transform: Optional[Any] = None

class Scope(BaseModel):
    foreach: str

class Source(BaseModel):
    json_path: str

class MappingEntry(BaseModel):
    mapping_id: str
    scope: Scope
    source: Source
    targets: List[Target]

class PredicateItem(BaseModel):
    type: str = "json_equals"
    path: str
    value: Any

class MatchPredicate(BaseModel):
    all: List[PredicateItem]

class Variant(BaseModel):
    variant_id: str
    match_predicate: MatchPredicate
    mappings: List[MappingEntry]

class RegistryConfig(BaseModel):
    registry_code: str


class Target(BaseModel):
    entity: str
    property: str
    entity_ref: Optional[str] = None
    transform: Optional[Any] = None

class Source(BaseModel):
    json_path: str

class Scope(BaseModel):
    foreach: str

class MappingEntry(BaseModel):
    mapping_id: str
    scope: Scope
    source: Source
    targets: List[Target]

class PredicateItem(BaseModel):
    type: str = "json_equals"
    path: str
    value: Any

class MatchPredicate(BaseModel):
    all: List[PredicateItem]

class Variant(BaseModel):
    variant_id: str
    match_predicate: MatchPredicate
    mappings: List[MappingEntry]

class RegistryConfig(BaseModel):
    registry_code: str
    # name: str
    variants: List[Variant]
