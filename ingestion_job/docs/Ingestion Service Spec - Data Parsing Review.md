# Ingestion Service - Registry Documents -> Canonical JSON -> Neo4j Entities/Relationships

I'll answer as a world-famous Data Platform Architect (graph data + ETL) with the ACM SIGMOD "Test of Time" Award.

**TL;DR**: The current codebase in the zip already runs end-to-end in JSON mode and is structured to support MongoDB (schemas/logs) and Neo4j (graph) in prod. This document describes the service exactly as implemented (modules, env vars, endpoints, schema JSON shapes) and lists what is still needed to be production-ready per your excalidraw requirements.

---

## 1) What this service is

The Ingestion Service ingests heterogeneous registry documents (XML/JSON today), normalizes them into a canonical JSON envelope, then uses a schema registry to:

- select a register schema variant for the document
- map fields into entities (Neo4j nodes)
- create relationships between entities (Neo4j relationships)
- write traceable logs, store ingested document records, and quarantine broken/ambiguous docs

Backends are configurable:
- Schemas: JSON files (default) or MongoDB
- Logs/docs/quarantine: JSONL files (default) or MongoDB
- Graph sink: Neo4j (default) or JSON output (for local testing)

---

## 2) Repository layout (from the zip)

Root folder: `ingestion_service/`

- `app/main.py`
  - FastAPI app and HTTP routes (`/health`, `/ingest`)
- `app/config.py`
  - Settings and environment variables
- `app/canonical.py`
  - Canonicalization: XML/JSON -> canonical envelope
- `app/schema_registry.py`
  - Schema backends and schema resolution (JSON backend + optional Mongo backend)
  - JSONPath-lite evaluator used by predicates and mappings
- `app/pipeline.py`
  - End-to-end ingestion pipeline orchestration
- `app/sinks.py`
  - Output backends:
    - JSONL stores for logs/docs/quarantine
    - optional Mongo stores for logs/docs/quarantine
    - graph sinks: JSON or Neo4j
- `schemas/`
  - `entity_schemas.json`
  - `register_schemas.json`
  - `relationship_schemas.json`
- `tests/sanity_check.py`
  - End-to-end sanity test in JSON mode (no Mongo/Neo4j required)
- `out_test/`
  - Output artifacts produced by `tests/sanity_check.py`

---

## 3) Inputs

### 3.1 How the service reads input today

The service ingests by file path (local filesystem):
- API input: `file_path` string
- Implementation: `IngestionPipeline.ingest_file(file_path)` in `app/pipeline.py`

Production note: Drive/S3 integration is not implemented yet. The clean place to add it is a small Source adapter (Drive/S3/FS) that returns (bytes + metadata), called from `ingest_file`.

### 3.2 Supported formats

Implemented in `app/canonical.py`:
- JSON: parsed via `json.loads`
- XML: parsed via `xml.etree.ElementTree` and converted into nested dict/list

---

## 4) Canonical JSON envelope

All downstream steps operate on this canonical structure:

```json
{
  "meta": {
    "file_path": "...",
    "content_type": "application/json | text/xml",
    "encoding": "utf-8",
    "content_hash": "sha256:...",
    "registry_code": "...",
    "service_code": "...",
    "method_code": "...",
    "xroad_request_id": "...",
    "xroad_user_id": "..."
  },
  "data": { "... canonicalized payload ..." }
}
```

Key notes:
- `meta.registry_code` and `meta.service_code` are used for schema lookup.
- XML/SOAP canonicalization attempts to populate these from headers when possible. If missing, schema resolution may fail and the doc can be quarantined.

---

## 5) Outputs

### 5.1 Graph outputs (entities + relationships)

The pipeline produces:
- Nodes (`NodeRecord` in `app/sinks.py`): `label`, `node_id`, `properties`
- Relationships (`RelRecord` in `app/sinks.py`): `rel_type`, `from_label/from_id`, `to_label/to_id`, `properties`

Graph sink options (env var `GRAPH_SINK`):

1) `GRAPH_SINK=json`
- Writes JSONL:
  - `OUT_DIR/graph_nodes.jsonl`
  - `OUT_DIR/graph_relationships.jsonl`
- Writes a combined view:
  - `OUT_DIR/graph_snapshot.json`

2) `GRAPH_SINK=neo4j` (default)
- Uses `Neo4jGraphSink` to upsert into Neo4j.
- Current behavior:
  - Nodes: `MERGE (n:Label {id: $id}) SET n += $props`
  - Rels: `MERGE (a)-[r:TYPE]->(b) SET r += $props`

Important limitation vs your excalidraw spec:
- Today we use a single property key `id` for all labels.
- If you need entity-specific primary keys (like `person_id`) and constraints, extend `Neo4jGraphSink` to use entity schema `neo4j.primary_key` (from your future Mongo schema) and to create constraints.

### 5.2 Logs, ingested documents, quarantine

Log/doc/quarantine storage is controlled by `LOG_BACKEND`.

1) `LOG_BACKEND=json` (default)
- `OUT_DIR/logs/ingestion_logs.jsonl`
- `OUT_DIR/logs/ingested_documents.jsonl`
- `OUT_DIR/logs/quarantined_documents.jsonl`
- canonical snapshots for quarantined docs:
  - `OUT_DIR/quarantine/{doc_id}.canonical.json`

2) `LOG_BACKEND=mongo`
- Uses MongoDB collections:
  - `ingestion_logs`
  - `ingested_documents`
  - `quarantined_documents`

---
## 6) HTTP API

Implemented in `app/main.py`.

### 6.1 GET /health
Returns:
```json
{"status":"ok"}
```

### 6.2 POST /ingest
Request body:
```json
{"file_path":"/abs/or/rel/path/to/doc.xml"}
```

Response:
- a JSON dict returned by `IngestionPipeline.ingest_file()` including `doc_id`, schema resolution, counters, and statuses.

Common error behaviors:
- missing `file_path` -> HTTP 422 (FastAPI request validation)
- unexpected exception -> HTTP 500

---

## 7) Configuration (env vars)

Defined in `app/config.py` and example file `ingestion_service/.env.example`.

### 7.1 Backend toggles
- `SCHEMA_BACKEND` = `json` (default) or `mongo`
- `LOG_BACKEND` = `json` (default) or `mongo`
- `GRAPH_SINK` = `neo4j` (default) or `json`

### 7.2 Paths (JSON mode)
- `SCHEMAS_DIR` (default: `./schemas`)
- `OUT_DIR` (default: `./out`)

### 7.3 Neo4j (used when GRAPH_SINK=neo4j)
- `NEO4J_URI` (default: `bolt://localhost:7687`)
- `NEO4J_USER` (default: `neo4j`)
- `NEO4J_PASSWORD` (default: `change_me`)
- `NEO4J_DATABASE` (optional, default: `neo4j`)

### 7.4 MongoDB (used when *_BACKEND=mongo)
- `MONGO_URI` (default: `mongodb://localhost:27017`)
- `MONGO_DB` (default: `ingestion`)

### 7.5 Run identity
- `RUN_ID` (optional). If not set, a random UUID is generated per service process.

---

## 8) Current schema files (JSON backend)

Schemas are loaded by `JsonSchemaRegistry` in `app/schema_registry.py`.

### 8.1 entity_schemas.json
Path: `schemas/entity_schemas.json`

Current entities included:
- Person
- Vehicle
- CivilEvent

Each entity defines:
- `name`, `description`
- `properties[]`: each property has `name`, `required`, `change_type` (`immutable|rarely_changed|dynamic`)

Note: `change_type` is not yet enforced against existing Neo4j state in the current sink implementation.

### 8.2 register_schemas.json
Path: `schemas/register_schemas.json`

A register schema is matched by:
- `registry_code`
- optional `service_code`
- optional `method_code`

Each register schema has `variants[]`.

Variant selection uses `match_predicate` rules (implemented in `app/schema_registry.py`). Supported ops:
- `exists`
- `equals`
- `in`
- `regex`

Each variant then defines:
- optional `foreach`: iterate a list path in canonical JSON
- `mappings[]`: entity mappings

Entity mapping fields used today:
- `entity`: entity type name (must exist in entity_schemas)
- `entity_ref`: reference handle used later for relationships
- optional mapping-level `foreach`
- `fields[]`: mapping rules
  - `property`
  - either `path` (JSONPath-lite) or `const`
  - optional `transforms`: `trim`, `collapse_spaces`, `parse_vehicle_description`
  - optional `merge_dict_to_properties` (used by parse_vehicle_description)

### 8.3 relationship_schemas.json
Path: `schemas/relationship_schemas.json`

Each relationship schema defines:
- `name`
- `rel_type` (Neo4j relationship type)
- `from_ref` / `to_ref` (entity_ref handles from mapping)
- `scope`: `scope_root` or `scope_same_instance`
- optional `properties` (static)

---
## 9) Ingestion pipeline (step-by-step)

Orchestrated by `IngestionPipeline` in `app/pipeline.py`.

### Step 1 - Read document bytes
- Reads file bytes from `file_path`
- Computes `doc_id` as `sha256(file_bytes)`

### Step 2 - Convert to canonical JSON
- Calls `canonicalize_bytes(...)` from `app/canonical.py`
- Produces `{meta, data}` canonical envelope
- Computes canonical hash in `meta.content_hash`

### Step 3 - Resolve register schema variant
- Calls `schema_registry.resolve_variant(canonical_doc)`
- Uses `meta.registry_code/service_code/method_code` to fetch candidate schemas
- Evaluates variant `match_predicate`

Outcomes:
- exactly one variant selected -> continue
- no variants match -> quarantine (`schema_not_found`)
- multiple variants match -> quarantine (`variant_ambiguous`)

### Step 4 - Map to entities
- Applies variant-level `foreach` (if configured)
- For each mapping:
  - Extracts values using JSONPath-lite
  - Applies transforms
  - Creates a `NodeRecord` with deterministic `node_id`

Entity ID today:
- node_id is computed from a hash of `(entity_name + identity_signature)` for stability.
- identity_signature is built from mapped fields (best-effort) and scope. This is a practical compromise until you add explicit `identity_keys` and primary keys.

### Step 5 - Resolve relationships
- Uses `schemas/relationship_schemas.json`
- Binds endpoints by `entity_ref` within the same scope
- Writes `RelRecord`

### Step 6 - Write graph
- JSON sink writes to JSONL + snapshot
- Neo4j sink merges nodes and relationships

### Step 7 - Persist doc record + logs
- Writes ingestion logs per major step (start/end style)
- Writes `ingested_documents` record with statuses and counts

### Step 8 - Quarantine
- On parse errors / schema errors, stores:
  - a canonical snapshot (`out/quarantine/{doc_id}.canonical.json`)
  - a row in `quarantined_documents.jsonl` (or Mongo)

---

## 10) How to run and test (exact commands)

### 10.1 Run locally in JSON mode
From `ingestion_service/`:

```bash
export SCHEMA_BACKEND=json
export LOG_BACKEND=json
export GRAPH_SINK=json
export SCHEMAS_DIR=./schemas
export OUT_DIR=./out

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Ingest:

```bash
curl -X POST http://localhost:8000/ingest \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"./answer.xml"}'
```

Artifacts:
- `./out/graph_snapshot.json`
- `./out/logs/ingestion_logs.jsonl`
- `./out/logs/ingested_documents.jsonl`
- `./out/logs/quarantined_documents.jsonl`

### 10.2 End-to-end sanity check

Run:
```bash
python tests/sanity_check.py
```

It runs the pipeline with:
- `GRAPH_SINK=json`
- `SCHEMA_BACKEND=json`
- `LOG_BACKEND=json`

And validates the produced JSON graph against expectations.

---

## 11) Alignment with your MongoDB collection contracts (excalidraw)

Yes, I understand your Mongo shapes. The current implementation follows the same ideas, but differs in shape and completeness.

### What matches conceptually
- We have the same core objects: entity schemas, register schemas (with variants), relationship schemas, ingestion logs, ingested docs, quarantine.
- We already persist traceability fields (`run_id`, `doc_id`, step name, details) in the log rows.

### What differs today (important)
- entity_schemas are simplified: no `neo4j.labels`, `primary_key`, `constraints`, `identity_keys`, per-registry source weights, version/status fields.
- relationship_schemas are simplified: no `creation_rules` DSL, uniqueness keys, merge policies.
- ingestion_runs is not yet a dedicated aggregated record (run_id exists, but no run-level aggregator store).
- schema_change_requests is not implemented.

Where to implement upgrades in this codebase:
- entity schema expansion: `app/schema_registry.py` (schema models) + `app/pipeline.py` (id and merge logic) + `app/sinks.py` (Neo4j constraints + PK usage)
- relationship rules DSL: `app/pipeline.py::_build_relationships`
- ingestion_runs: add a store in `app/sinks.py` and update it from `app/pipeline.py`
- schema_change_requests: create a store in `app/sinks.py` and emit request docs when quarantining

---

## 12) Production-ready functional requirements (what is still needed)

This section is the checklist for making the service truly production-ready according to your full requirements.

### 12.1 Schema registry in MongoDB (required)
- Store `register_schemas`, `entity_schemas`, `relationship_schemas` in MongoDB.
- Add schema versioning and lifecycle: `draft | active | deprecated`.
- Add support for multiple variants per registry/service/method.
- Add caching and periodic refresh to avoid per-doc Mongo roundtrips.

### 12.2 Entity identity and deduplication (required)
- Implement `identity_keys` priority list (rnokpp, unzr, doc tuple, etc.).
- Use explicit Neo4j primary keys per entity (`neo4j.primary_key`) instead of a generic `id`.
- Create and maintain constraints/indexes from schema (`neo4j.constraints`).

### 12.3 Merge policy enforcement (required)
- For each property, enforce `change_type` rules:
  - immutable: conflict -> quarantine + alert
  - rarely_changed: keep existing, log warning
  - dynamic: take latest by source timestamp
- Requires reading existing node state from Neo4j during upsert.

### 12.4 Relationship rules and uniqueness (required)
- Implement your `creation_rules` DSL:
  - conditions (entity_exists, field_exists, equals, regex, etc.)
  - binding endpoints by entity refs and/or field matches
  - relationship properties derived from document context
- Implement uniqueness strategies and merge policies for relationships.

### 12.5 Ingestion runs aggregation (highly recommended)
- Create `ingestion_runs` collection and write one record per run.
- Aggregate counts: entities extracted/upserted, relationships created, conflicts, quarantine reasons.

### 12.6 Quarantine classification and developer actions (required)
- Classify common broken cases:
  - access_denied
  - empty response
  - corrupt xml
  - schema_not_found
  - variant_ambiguous
  - immutable_conflict
- Emit structured `next_action` in ingestion logs (severity, suggested owner, suggested text).

### 12.7 Observability (required)
- Structured logs to stdout (JSON) for platform ingestion.
- Metrics (Prometheus): processed count, quarantine rate, schema resolution time, Neo4j upsert time.
- Tracing (optional): propagate request id through steps.

### 12.8 Deployment and security (required)
- Containerization (Dockerfile) and runtime health probes.
- TLS to Mongo/Neo4j.
- PII handling: no raw payloads in logs; store hashes + short excerpts in quarantine.
- Retention policies for logs/quarantine snapshots.

---

## 13) Developer guide: adding new schemas/entities/relationships

### Add a new register schema variant
- Edit `schemas/register_schemas.json` (JSON backend) or add to Mongo (Mongo backend).
- Ensure `match_predicate` is strong enough to avoid ambiguity.
- Add `mappings` and (if needed) `foreach`.
- Add new relationships in `schemas/relationship_schemas.json` using the mapping `entity_ref` handles.

### Add a new entity
- Add to `schemas/entity_schemas.json` with properties.
- Add mappings that populate those properties.

### Add/extend transforms
- Add a transform function in `app/schema_registry.py::TRANSFORMS`.
- Use it from mapping rules.

---

## 14) Current status (honest snapshot)

Works today (verified in this environment):
- service boots with FastAPI
- JSON/XML canonicalization works for included sample files
- schema variant resolution works
- entity mapping works for Person, Vehicle, CivilEvent
- relationship linking works for included relationship schemas
- JSON-mode outputs pass `tests/sanity_check.py`

Not verifiable here but implemented:
- Mongo backends (schemas/logs/docs/quarantine)
- Neo4j sink

Biggest gap vs your excalidraw contracts:
- full entity identity and merge policy logic (needs Neo4j read-before-write)
- relationship creation_rules DSL
- ingestion_runs and schema_change_requests stores

