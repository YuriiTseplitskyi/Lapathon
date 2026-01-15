from __future__ import annotations

import re
import uuid
import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Set

from ingestion_job.app.core.settings import Settings
from ingestion_job.app.models.documents import RawDocument, CanonicalDocument
from ingestion_job.app.models.graph import EntityInstance, NodeRecord, RelRecord
from ingestion_job.app.models.schemas import RegisterSchemaVariant, RegisterSchema, RelationshipSchema, VariantMapping
from ingestion_job.app.models.mongo import (
    IngestionLog, IngestedDocument, IngestionRun, QuarantinedDocument, 
    RawContent, CanonicalContent, DocumentClassification, SchemaRef,
    FailureInfo, Neo4jWriteSummary, RunMetrics, InputInfo, SchemaResolutionInfo,
    LineageInfo
)

# Services
from ingestion_job.app.services.canonical.service import CanonicalizerService, read_raw_document
from ingestion_job.app.services.schema.service import resolve_variant_impl
from ingestion_job.app.services.schema.base import BaseSchemaRegistry
from ingestion_job.app.services.schema.backend_json import JsonSchemaRegistry
from ingestion_job.app.services.schema.backend_mongo import MongoSchemaRegistry
from ingestion_job.app.services.schema.utils import jp_values, jp_first, eval_predicate

from ingestion_job.app.services.sinks.base import LogStore, DocumentStore, QuarantineStore, GraphSink
from ingestion_job.app.services.sinks.factory import create_sinks

def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def stable_norm(s: str) -> str:
    s = normalize_ws(s or "")
    s = s.lower()
    s = re.sub(r"[^a-z0-9а-яіїєґ]+", "_", s, flags=re.IGNORECASE)
    s = re.sub(r"_+", "_", s).strip("_")
    return s

def apply_transforms(val: Any, transforms: List[str]) -> Any:
    v = val
    for t in transforms:
        if v is None:
            return None
        if t == "trim":
            if isinstance(v, str): v = v.strip()
        elif t == "collapse_spaces":
            if isinstance(v, str): v = normalize_ws(v)
        elif t == "upper":
            if isinstance(v, str): v = v.upper()
        elif t == "lower":
            if isinstance(v, str): v = v.lower()
        elif t == "to_int":
            try: v = int(str(v))
            except Exception: v = None
    return v

class IngestionPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.ensure_out_dirs()
        self.run_id = settings.run_id or str(uuid.uuid4())

        self.canonicalizer = CanonicalizerService()

        # Schema Registry
        if settings.schema_backend == "mongo":
            self.schema_registry: BaseSchemaRegistry = MongoSchemaRegistry(settings.mongo_uri, settings.mongo_db)
        else:
            self.schema_registry = JsonSchemaRegistry(settings.schemas_dir)
        self.schema_registry.load()

        # Sinks
        self.logs, self.docs, self.quarantine, self.graph = create_sinks(settings)
        
        # Initialize Run Record
        self.run_record = IngestionRun(run_id=self.run_id, status="running")
        self.docs.write_run(self.run_record)

    def close(self) -> None:
        self.run_record.finished_at = datetime.utcnow()
        self.run_record.status = "success"  # or derive from failures
        self.docs.write_run(self.run_record)
        self.graph.close()

    def _log(self, step: str, message: str, status: str = "success", doc_id: Optional[str] = None, details: Dict[str, Any] = None):
        log_entry = IngestionLog(
            run_id=self.run_id,
            document_id=doc_id,
            step=step,
            status=status, # type: ignore
            message=message,
            details=details or {}
        )
        self.logs.log(log_entry)


    def ingest_file(self, file_path: str) -> Dict[str, Any]:
        # Step 1: Read Documents
        self._log("read_document", f"Reading raw file: {file_path}", status="success")
        try:
            raw_doc_obj = read_raw_document(file_path)
            doc_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, file_path + self.run_id))
            
            raw_content = RawContent(
                file_path=file_path,
                content_type=raw_doc_obj.content_type,
                content_hash=raw_doc_obj.content_hash,
                encoding=raw_doc_obj.encoding
            )
            
            ingested_doc = IngestedDocument(
                document_id=doc_id,
                run_id=self.run_id,
                raw=raw_content,
                ingestion_status="pending"
            )
            self.docs.write(ingested_doc)
            self._log("read_document", "Raw document created", doc_id=doc_id)
            
        except Exception as e:
            self._log("read_document", f"Failed to read file: {e}", status="error", details={"file_path": file_path, "error": str(e)})
            return {"status": "error", "error": str(e)}

        # Step 2: Canonicalize
        self._log("canonicalize", "Starting canonicalization", doc_id=doc_id)
        canonical_obj = self.canonicalizer.canonicalize(raw_doc_obj)
        
        ingested_doc.canonical = CanonicalContent(
            hash=canonical_obj.canonical_hash
            # document_ref left empty for now as we don't store separate blob ref
        )
        
        if canonical_obj.parse_error:
            return self._handle_quarantine(ingested_doc, "parse_error", canonical_obj.parse_error, {"raw": raw_doc_obj.file_path})
            
        ingested_doc.ingestion_status = "processed" # Interim
        self.docs.write(ingested_doc)

        canonical_dict = {"meta": canonical_obj.meta, "data": canonical_obj.data}

        # Step 3 & 4: Resolve Registry Schema & Variant Selection
        self._log("resolve_schema", "Resolving schema variant", doc_id=doc_id)
        
        # Use real resolver from Schema Registry
        variant, debug = self.schema_registry.resolve_variant(canonical_dict)
        
        if not variant:
             return self._handle_quarantine(ingested_doc, "schema_not_found", "No matching schema variant found", debug)

        # Update Doc with classification
        # We need to find which RegisterSchema this variant belongs to
        parent_schema = self._find_parent_schema(variant.variant_id)
        if parent_schema:
            ingested_doc.classification = DocumentClassification(
                registry_code=parent_schema.registry_code,
                service_code=parent_schema.service_code,
                method_code=parent_schema.method_code
            )
            ingested_doc.schema_ref = SchemaRef(
                register_schema_id=self._dummy_oid(parent_schema.registry_code), # Mock ID
                variant_id=variant.variant_id
            )
        
        self.docs.write(ingested_doc)
        self._log("resolve_schema", f"Selected variant: {variant.variant_id}", doc_id=doc_id)

        # Step 5: Map to Entities
        self._log("map_entities", "Mapping to graph entities", doc_id=doc_id)
        
        entities = self._map_entities(doc_id, canonical_dict, variant)
        if entities is None: # Error case
             return self._handle_quarantine(ingested_doc, "mapping_error", "Failed to map entities", {})

        # Merge Policy Check (Immutable)
        # TODO: Lookup existing nodes in Neo4j to check for immutable conflicts
        # For now, we assume strict upsert
        
        nodes = [NodeRecord(
            label=e.label, node_id=e.node_id or "", properties=e.properties, 
            source_doc=doc_id, scope_root=e.scope_root, entity_ref=e.entity_ref
        ) for e in entities]
        
        write_summary = self.graph.upsert_nodes(nodes)
        ingested_doc.neo4j_write_summary.nodes_created = write_summary.get("nodes_upserted", 0)
        
        # Update Run Metrics
        self.run_record.metrics.entities_extracted += len(entities)
        self.run_record.metrics.entities_upserted += write_summary.get("nodes_upserted", 0)

        # Step 6: Resolve Relationships
        self._log("resolve_relationships", "Resolving relationships", doc_id=doc_id)
        rels = self._build_relationships(doc_id, entities)
        
        if rels:
            rel_summary = self.graph.upsert_relationships(rels)
            ingested_doc.neo4j_write_summary.rels_created = rel_summary.get("relationships_created", 0)
            self.run_record.metrics.relationships_created += rel_summary.get("relationships_created", 0)
        
        # Step 7: Finalize
        ingested_doc.ingestion_status = "processed"
        self.docs.write(ingested_doc)
        self.docs.write_run(self.run_record)
        
        return {"status": "success", "doc_id": doc_id}

    def _handle_quarantine(self, doc: IngestedDocument, category: str, message: str, details: Dict[str, Any]) -> Dict[str, Any]:
        doc.ingestion_status = "quarantined"
        doc.parse_status = "parse_error" if category == "parse_error" else "ok"
        doc.failure = FailureInfo(category=category, message=message, details=details) # type: ignore
        self.docs.write(doc)
        
        q_doc = QuarantinedDocument(
            document_id=doc.document_id,
            content_hash=doc.raw.content_hash,
            reason=category,
            extra=details
        )
        self.quarantine.quarantine(q_doc)
        
        self.run_record.status = "warning"
        self.docs.write_run(self.run_record)
        
        self._log("quarantine", message, status="error", doc_id=doc.document_id, details=details)
        return {"status": "quarantined", "reason": message}

    def resolver_dummy_logic(self, content: Dict[str, Any]) -> Tuple[Optional[RegisterSchemaVariant], Dict[str, Any]]:
        # Deprecated: usage replaced by self.schema_registry.resolve_variant
        return None, {}

    def _find_parent_schema(self, variant_id: str) -> Optional[RegisterSchema]:
        for reg in self.schema_registry.register_schemas:
            for v in reg.variants:
                if v.variant_id == variant_id:
                    return reg
        return None

    def _dummy_oid(self, seed: str) -> str:
        return hashlib.md5(seed.encode()).hexdigest()[:24]
    
    def _map_entities(self, doc_id: str, canonical_doc: Dict[str, Any], variant: RegisterSchemaVariant) -> Optional[List[EntityInstance]]:
        instances: List[EntityInstance] = []
        
        for m in variant.mappings:
            # Resolving Scope
            foreach_path = m.scope.get("foreach")
            root_items = []
            if foreach_path:
                items = jp_values(canonical_doc, foreach_path)
                # If jsonpath returns nothing, but it's a dict passed, try root wrapping?
                # Actually default behavior of jsonpath_ng might matter differently.
                # Assuming jp_values handles it.
                if items is None: items = []
                if not isinstance(items, list):
                    items = [items]
                root_items = items
            else:
                root_items = [canonical_doc]
            
            # For each item in scope
            for idx, item in enumerate(root_items):
                scope_root = f"{doc_id}:{m.mapping_id or 'map'}:{idx}"
                
                # Targets
                for t in m.targets:
                    val = None
                    if "json_path" in m.source:
                        val = jp_first(item, m.source["json_path"])
                    
                    label = t.entity
                    prop = t.property
                    entity_ref = t.entity_ref or label
                    
                    # Construct/Find existing instance in buffer
                    # We scope instances by (scope_root, entity_ref) to allow multiple mappings to contribute to the same entity
                    inst_key = f"{scope_root}:{entity_ref}"
                    inst = next((i for i in instances if i.scope_id == inst_key), None)
                    if not inst:
                        inst = EntityInstance(
                            label=label,
                            entity_ref=entity_ref,
                            scope_root=scope_root,
                            scope_id=inst_key,
                            properties={}
                        )
                        instances.append(inst)
                    
                    if val is not None:
                        inst.properties[prop] = val
                    inst.properties["source_doc_id"] = doc_id

        # Post Process IDs
        for inst in instances:
            self._finalize_entity_id(inst, doc_id)
            
        return instances

    def _finalize_entity_id(self, inst: EntityInstance, doc_id: str) -> None:
        es = self.schema_registry.entity_schemas.get(inst.label)
        
        if not es:
             # Fallback
             inst.node_id = f"DOCSCOPED:{doc_id}:{inst.scope_id}"
             return
             
        # Check Identity Keys
        matched_kv = []
        for key_def in es.identity_keys:
             # Check 'when' - naive implementation for "exists"
             req_fields = key_def.when.get("exists", [])
             if all(inst.properties.get(f) is not None for f in req_fields):
                 # Use these properties
                 parts = [str(inst.properties.get(p)) for p in key_def.properties]
                 matched_kv = parts
                 break # priority order
        
        if matched_kv:
             # Deterministic ID based on identity key
             raw_id = "|".join(matched_kv)
             inst.node_id = hashlib.sha256(raw_id.encode()).hexdigest()
        else:
             # Fallback to doc-scoped ID
             inst.node_id = f"DOCSCOPED:{doc_id}:{inst.scope_id}"

    def _build_relationships(self, doc_id: str, entities: List[EntityInstance]) -> List[RelRecord]:
        rels: List[RelRecord] = []
        
        for rs in self.schema_registry.relationship_schemas:
             for rule in rs.creation_rules:
                 # Check 'when' conditions (e.g. entity_exists)
                 # Simplified logic: match entities in SAME SCOPE
                 
                 from_ref = rule.bind.from_.entity_ref  # Note: using 'from_' alias
                 to_ref = rule.bind.to.entity_ref
                 
                 # Group by scope_root
                 by_scope = {}
                 for e in entities:
                     by_scope.setdefault(e.scope_root, []).append(e)
                     
                 for scope_root, scope_entities in by_scope.items():
                     from_nodes = [e for e in scope_entities if e.entity_ref == from_ref]
                     to_nodes = [e for e in scope_entities if e.entity_ref == to_ref]
                     
                     for fn in from_nodes:
                         for tn in to_nodes:
                             # Create Rel
                             props = {"source_doc": doc_id}
                             # Apply properties from rule
                             for p in rule.properties:
                                 if p.value is not None:
                                     props[p.name] = p.value
                                 # value_from support could be added here
                             
                             rels.append(RelRecord(
                                 rel_type=rs.neo4j.type,
                                 from_label=fn.label,
                                 from_id=fn.node_id,
                                 to_label=tn.label,
                                 to_id=tn.node_id,
                                 properties=props,
                                 source_doc=doc_id,
                                 scope_root=scope_root,
                                 name=rs.relationship_name
                             ))
        return rels
