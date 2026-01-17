from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# -------------------------------------------------------------------------
# Common Types
# -------------------------------------------------------------------------

IngestionStatus = Literal["pending", "processed", "quarantined", "failed", "skipped"]
ParseStatus = Literal["ok", "parse_error", "corrupt", "unsupported"]
FailureCategory = Literal["schema_not_found", "variant_ambiguous", "access_denied", "immutable_conflict", "mapping_error", "parse_error", "other"]
RunStatus = Literal["running", "success", "warning", "failed", "quarantined"]


class RawContent(BaseModel):
    file_path: str
    source_system: str = "fs"
    content_type: str
    encoding: str = "utf-8"
    content_hash: str


class CanonicalContent(BaseModel):
    format: str = "canonical_json_v1"
    document_ref: Optional[str] = None  # ObjectId as hex (deprecated)
    hash: str
    meta: Optional[Dict[str, Any]] = None  # Canonical metadata (registry_code, file_extension, etc.)
    data: Optional[Any] = None  # Normalized JSON representation of document


class DocumentClassification(BaseModel):
    registry_code: str
    service_code: Optional[str] = None
    method_code: Optional[str] = None


class SchemaRef(BaseModel):
    register_schema_id: Optional[str] = None
    variant_id: Optional[str] = None


class FailureInfo(BaseModel):
    category: FailureCategory
    message: str
    details: Dict[str, Any] = {}


class Neo4jWriteSummary(BaseModel):
    nodes_created: int = 0
    nodes_updated: int = 0
    rels_created: int = 0
    rels_updated: int = 0


# -------------------------------------------------------------------------
# Collections
# -------------------------------------------------------------------------

class IngestedDocument(BaseModel):
    """
    MongoDB collection: ingested_documents
    """
    document_id: str
    
    raw: RawContent
    canonical: Optional[CanonicalContent] = None
    
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    
    classification: Optional[DocumentClassification] = None
    schema_ref: Optional[SchemaRef] = None
    
    parse_status: ParseStatus = "ok"
    ingestion_status: IngestionStatus = "pending"
    
    failure: Optional[FailureInfo] = None
    
    neo4j_write_summary: Neo4jWriteSummary = Field(default_factory=Neo4jWriteSummary)
    
    run_id: str
    last_updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(extra="ignore")


class InputInfo(BaseModel):
    document_id: str
    raw: Optional[RawContent] = None
    canonical: Optional[CanonicalContent] = None


class SchemaResolutionInfo(BaseModel):
    registry_code: Optional[str] = None
    service_code: Optional[str] = None
    method_code: Optional[str] = None
    register_schema_id: Optional[str] = None
    variant_id: Optional[str] = None


class RunMetrics(BaseModel):
    entities_extracted: int = 0
    entities_upserted: int = 0
    relationships_created: int = 0
    immutable_conflicts: int = 0


class IngestionRun(BaseModel):
    """
    MongoDB collection: ingestion_runs
    """
    run_id: str
    trigger: Literal["file_drop", "manual_replay", "scheduler"] = "manual_replay"
    
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    status: RunStatus = "running"
    
    input: Optional[InputInfo] = None
    schema_resolution: Optional[SchemaResolutionInfo] = None
    
    metrics: RunMetrics = Field(default_factory=RunMetrics)
    
    next_action: Literal["none", "define_schema", "fix_variant", "investigate_merge"] = "none"

    model_config = ConfigDict(extra="ignore")


class LineageInfo(BaseModel):
    input_ref: Dict[str, Any] = {}
    output_ref: Dict[str, Any] = {}


class IngestionLog(BaseModel):
    """
    MongoDB collection: ingestion_logs
    """
    run_id: str
    document_id: Optional[str] = None
    ts: datetime = Field(default_factory=datetime.utcnow)
    
    step: str
    stage: Literal["start", "end", "error"] = "start"
    status: Literal["success", "warning", "error", "skipped"] = "success"
    
    message: str
    details: Dict[str, Any] = {}
    
    lineage: Optional[LineageInfo] = None
    next_action: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(extra="ignore")


class QuarantinedDocument(BaseModel):
    """
    MongoDB collection: quarantined_documents
    """
    document_id: str
    file_path: Optional[str] = None
    content_hash: str
    reason: str
    excerpt: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: Literal["open", "resolved", "ignored"] = "open"
    owner: str = "data_eng"
    extra: Dict[str, Any] = {}

    model_config = ConfigDict(extra="ignore")
