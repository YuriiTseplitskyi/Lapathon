from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union
from datetime import datetime
from pydantic import BaseModel, Field

# -------------------------------------------------------------------------
# Register Schema
# -------------------------------------------------------------------------

class JsonPredicate(BaseModel):
    type: Literal["json_exists", "json_equals"]
    path: str
    value: Optional[Any] = None

class MatchPredicate(BaseModel):
    all: List[JsonPredicate] = []
    none: List[JsonPredicate] = []

class MappingTarget(BaseModel):
    entity: str
    property: str
    entity_ref: Optional[str] = None

class VariantMapping(BaseModel):
    mapping_id: Optional[str] = None
    scope: Dict[str, str] = {}  # e.g. {"foreach": "$.document.birthAct[*]"}
    source: Dict[str, str] = {} # e.g. {"json_path": "$.actNumber"}
    targets: List[MappingTarget] = []
    required: bool = False
    on_missing: Literal["skip", "error", "default"] = "skip"

class VariantEmits(BaseModel):
    entities: List[str] = []
    relationships: List[str] = []

class RegisterSchemaVariant(BaseModel):
    variant_id: str
    priority: int = 100
    match_predicate: MatchPredicate
    mappings: List[VariantMapping]
    emits: VariantEmits = Field(default_factory=VariantEmits)

class CanonicalHeaderFields(BaseModel):
    registry_code: str = "$.meta.registry_code"
    service_code: str = "$.meta.service_code"
    method_code: str = "$.meta.method_code"

class SchemaMatchConfig(BaseModel):
    canonical_header_fields: CanonicalHeaderFields

class RegisterSchema(BaseModel):
    """
    MongoDB collection: register_schemas
    """
    registry_code: str
    service_code: Optional[str] = None
    method_code: Optional[str] = None
    
    source: Dict[str, Any] = {}
    status: Literal["active", "draft", "deprecated"] = "active"
    version: int = 1
    
    schema_match: SchemaMatchConfig
    variants: List[RegisterSchemaVariant]
    
    entity_schema_refs: List[str] = []
    relationship_schema_refs: List[str] = []
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# -------------------------------------------------------------------------
# Entity Schema
# -------------------------------------------------------------------------

class Neo4jEntityConfig(BaseModel):
    labels: List[str]
    primary_key: str
    constraints: List[Dict[str, str]] = []

class IdentityKey(BaseModel):
    priority: int
    when: Dict[str, Any]  # e.g. {"exists": ["rnokpp"]}
    properties: List[str]

class EntityPropertySchema(BaseModel):
    name: str
    type: str # string, date, etc.
    is_required: bool = False
    change_type: Literal["immutable", "rarely_changed", "dynamic"] = "rarely_changed"
    normalize: List[str] = []

class MergePolicy(BaseModel):
    default: str = "prefer_non_null"
    immutable_conflict: str = "quarantine_and_alert"
    rarely_changed_conflict: str = "log_warning_and_keep_existing"
    dynamic_conflict: str = "take_latest_by_source_timestamp"

class EntitySchema(BaseModel):
    """
    MongoDB collection: entity_schemas
    """
    entity_name: str
    neo4j: Neo4jEntityConfig
    
    identity_keys: List[IdentityKey]
    properties: List[EntityPropertySchema]
    
    merge_policy: MergePolicy
    
    # Simple source priority for now, can be complex in future
    source_priority: List[Dict[str, Any]] = [] 
    
    version: int = 1
    status: str = "active"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# -------------------------------------------------------------------------
# Relationship Schema
# -------------------------------------------------------------------------

class Neo4jRelConfig(BaseModel):
    type: str
    direction: Literal["out", "in"] = "out"
    from_label: str
    to_label: str

class RelEndpoints(BaseModel):
    from_entity: str
    to_entity: str

class RelCondition(BaseModel):
    type: str # entity_exists
    entity_ref: str

class RelWhen(BaseModel):
    all: List[RelCondition] = []

class RelBindRef(BaseModel):
    entity_ref: str

class RelBind(BaseModel):
    # 'from' is a reserved keyword in python
    from_: RelBindRef = Field(alias="from")
    to: RelBindRef

class RelPropertyMap(BaseModel):
    name: str
    value: Optional[Any] = None
    value_from: Optional[Dict[str, Any]] = None

class CreationRule(BaseModel):
    rule_id: str
    when: RelWhen
    bind: RelBind
    properties: List[RelPropertyMap] = []

class RelUniqueness(BaseModel):
    strategy: str = "unique_per_endpoints_and_type"
    keys: List[str] = []

class RelationshipSchema(BaseModel):
    """
    MongoDB collection: relationship_schemas
    """
    relationship_name: str
    neo4j: Neo4jRelConfig
    endpoints: RelEndpoints
    
    creation_rules: List[CreationRule]
    uniqueness: RelUniqueness
    merge_policy: Dict[str, str] = {}
    
    version: int = 1
    status: str = "active"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
