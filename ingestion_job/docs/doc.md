# Ingestion Service — Schema-Driven Document → Entity Graph Pipeline (MongoDB + Neo4j)

## What this service is
The Ingestion Service is a schema-driven microservice that consumes heterogeneous “registry” documents (XML/JSON/CSV from external registries), converts them into a canonical JSON representation, resolves the correct schema variant from a registry schema store, extracts and normalizes real-world **Entities** (Person, Vehicle, CivilEvent, etc.), deduplicates and consolidates them, and writes the resulting **nodes + relationships** to Neo4j (or to JSON output for testing).  

The service also produces complete **data lineage** and step-level tracing in MongoDB, quarantines ambiguous/corrupt documents without breaking the pipeline, and generates schema-change requests when the available schemas are insufficient.

This document defines all functional and non-functional requirements for a production-ready implementation.

---

## Goals and non-goals

### Goals
- Convert messy registry documents into a **normalized, deduplicated, connected entity graph**.
- Support multiple schema variants per registry/service/method (because real-world document structures drift).
- Provide **explainable ingestion**: per-step logs, lineage, metrics, decisions, and deterministic replays.
- Be resilient: never crash the whole pipeline due to one broken/unknown document; quarantine instead.
- Enforce data correctness via merge/immutability policies and conflict handling.

### Non-goals (for the ingestion service itself)
- Not responsible for advanced corruption scoring / ML inference (can be downstream consumers/agents).
- Not responsible for crawling/collecting data from registries (assumed upstream or separate collector).
- Not a full BI/reporting layer.

---

## Inputs

### Supported input sources
- File system (FS)
- Object storage (S3-compatible)
- Drive-like source (through upstream fetcher or mounted folder)

### Supported document formats
- JSON
- XML (including SOAP envelopes such as X-Road)
- CSV (optional; can be added later)

### What a “document” is
A document is a single file payload containing:
- raw bytes (or raw string)
- metadata (file path / source system / timestamps / content type)
- optionally registry hints (registry_code, service_code, method_code)

### Required input metadata (minimum)
- `file_path` (unique identity for a file within a batch)
- `source_system` (fs|s3|drive|other)
- `content_type` (e.g., application/json, text/xml)
- `encoding` (best-effort; default utf-8)
- `discovered_at` timestamp

### Optional input metadata (strongly recommended)
- upstream `document_id` UUID (if collector already assigns)
- source retrieval timestamp
- upstream correlation id / batch id

---

## Outputs

### Primary output (production)
- Neo4j graph:
  - Entity nodes (Person, Vehicle, CivilEvent, …)
  - Relationship edges (OWNS_VEHICLE, HAS_CIVIL_EVENT, PARENT_OF, …)
  - Node/edge properties normalized and validated

### Secondary outputs (always)
- MongoDB records:
  - ingested documents index + status
  - step-by-step ingestion logs with lineage
  - ingestion run summary
  - quarantined documents
  - schema change requests (when schemas missing/ambiguous/conflicting)

### Testing output mode (for local/dev without DBs)
- JSON graph snapshot:
  - nodes list
  - relationships list
  - per-node stable ids and properties
- JSONL logs and quarantine snapshots to a local folder

---

## High-level architecture

### Components
1) **Document Reader**
   - Loads raw payload + metadata from FS/S3/Drive.
   - Computes `content_hash` (sha256 of raw bytes).
   - Persists minimal raw metadata to Mongo.

2) **Canonicalizer**
   - Converts raw JSON/XML/CSV to a canonical JSON envelope:
     - `meta`: registry/service/method classification, parse info, hashes
     - `data`: the parsed data tree
   - Computes `canonical_hash` (sha256 of canonical json string).
   - Must preserve raw content references for audit.

3) **Schema Resolver**
   - Queries MongoDB `register_schemas` by classification fields:
     - `registry_code`, `service_code` (optional), `method_code` (optional)
   - Scores candidate variants using `match_predicate`.
   - Selects exactly one variant or quarantines.

4) **Entity Extractor**
   - Applies mappings from selected schema variant.
   - Produces entity instances (with `entity_ref` labels for linking within document scope).
   - Normalizes values and enforces types.

5) **Entity Resolver / Upserter**
   - Uses `entity_schemas.identity_keys` to deduplicate and find existing nodes.
   - Applies merge policy:
     - immutable conflicts -> quarantine and alert
     - rarely_changed -> warning + keep existing (or source-priority override)
     - dynamic -> latest by source timestamp or weighted priority
   - Writes to Neo4j with deterministic keys.

6) **Relationship Builder**
   - Applies `relationship_schemas.creation_rules` to bind endpoints.
   - Enforces uniqueness keys and merge policy.
   - Writes to Neo4j.

7) **Observability + Lineage**
   - Writes step logs to `ingestion_logs`.
   - Writes per-document status to `ingested_documents`.
   - Writes per-run summary to `ingestion_runs`.
   - Writes quarantine records to `quarantined_documents`.

8) **Schema Change Request Generator**
   - When schema missing/ambiguous or new fields appear:
     - produces `schema_change_requests` referencing evidence documents and proposed change templates.

---

## Canonical JSON contract

### Canonical envelope shape
- `meta`:
  - `document_id` (uuid)
  - `file_path`
  - `source_system`
  - `content_type`
  - `encoding`
  - `content_hash` (sha256)
  - `canonical_hash` (sha256)
  - `parse_status`: ok|parse_error|unsupported|corrupt
  - `registry_code` (best-effort)
  - `service_code` (best-effort)
  - `method_code` (best-effort)
  - `source_timestamp` (if present)
  - `parser_version`
- `data`:
  - parsed content tree (json object)

### Requirements for canonicalization
- Must not lose information needed for audit:
  - store references or excerpts of the raw payload
- Must be resilient:
  - parse errors must not crash pipeline; set `meta.parse_status` and quarantine if needed
- Must capture SOAP header fields where present (X-Road):
  - registry/service/method identifiers
  - request metadata if useful (xroad id, user id, etc.)

---

## MongoDB data model (production contract)

The following collections must exist and match the agreed contract. The service should support MongoDB as the default backend and allow JSON-file backend for local/dev.

### `entity_schemas`
Stores entity definitions used for identity resolution, property typing, normalization, and merge behavior.

Functional requirements:
- Define Neo4j labels and constraints/indexes.
- Define `identity_keys` priorities with `when.exists` conditions.
- Define per-property:
  - type (string|int|date|bool|…)
  - required flag
  - change_type: immutable|rarely_changed|dynamic
  - normalization pipeline
- Define merge policies:
  - default merge strategy
  - behavior on conflicts by change_type
- Support versioning and lifecycle:
  - version integer
  - status: active|draft|deprecated
  - timestamps

### `register_schemas`
Defines how to classify and map documents for a particular registry/service/method and schema variant.

Functional requirements:
- Must be selectable by:
  - `registry_code` (required)
  - `service_code` (optional; may be missing in some docs)
  - `method_code` (optional)
- Must support multiple `variants` per (registry_code, service_code).
- Each variant must include:
  - `variant_id`
  - `match_predicate` (rules to identify the variant)
  - `mappings` (how to extract entities and properties)
  - optional constraints and error explanations

### `relationship_schemas`
Defines how to create relationships between entities (nodes).

Functional requirements:
- Must define neo4j relationship type, direction, endpoint labels.
- Must include `creation_rules`:
  - `when` conditions (entity exists, property exists, equals, regex, etc.)
  - `bind` rules (which entity_ref or identity to use for from/to)
  - relationship properties (static values, derived from context/document)
- Must include uniqueness strategy and keys
- Must include merge policy for relationship updates
- Support versioning and lifecycle statuses

### `ingested_documents`
Stores per-document state and outcomes.

Functional requirements:
- Track raw + canonical metadata and hashes.
- Store classification fields discovered.
- Store schema reference (schema_id + variant_id).
- Track parse and ingestion statuses.
- Store failure category/message/details if failed/quarantined.
- Store Neo4j write summary (nodes/relationships created/updated).
- Keep `run_id` linkage and last_updated timestamp.

### `ingestion_runs`
Stores batch-level summary.

Functional requirements:
- Unique `run_id` (uuid).
- Trigger type (file_drop|manual_replay|scheduler).
- Start/end timestamps and final status.
- Input references (document_id and raw/canonical hashes).
- Schema resolution summary.
- Aggregated metrics:
  - entities extracted/upserted
  - relationships created/updated
  - conflicts
  - quarantined count
- `next_action` summary for operations.

### `ingestion_logs`
Step-level event log (lineage + trace).

Functional requirements:
- Every pipeline step writes `start` and `end` events.
- Must include:
  - run_id, document_id, timestamp
  - step name, stage (start|end), status
  - message + structured details
  - lineage input/output refs
  - next_action object with severity and suggested owner

### `quarantined_documents`
Documents that require human attention.

Functional requirements:
- document_id + content hash
- reason category (variant_ambiguous, schema_not_found, parse_error, immutable_conflict, access_denied, …)
- excerpt or canonical snapshot reference
- created_at timestamp
- status: open|resolved|ignored
- owner field for triage

### `schema_change_requests`
Tracks proposed schema changes based on evidence.

Functional requirements:
- request_id uuid
- registry/service/method identifiers
- proposed changes (add variant, new mapping, new entity property)
- evidence references (document ids, hashes)
- approval lifecycle: proposed|approved|rejected|merged
- created_at timestamp

---

## Ingestion pipeline (functional requirements)

The service MUST implement the following steps reliably. Each step MUST be logged to `ingestion_logs` (start/end), and per-document state must be updated in `ingested_documents`.

### Step 1 — Read Documents
- Load raw bytes from source.
- Compute `content_hash`.
- Write raw metadata record to `ingested_documents.raw`.
- If unreadable: quarantine as `corrupt` with reason.

### Step 2 — Convert to Canonical JSON
- Parse JSON/XML/CSV into canonical envelope.
- Preserve raw references for audit.
- Compute `canonical_hash`.
- If parse error:
  - set `parse_status=parse_error`
  - quarantine with reason and excerpt
  - do not proceed to schema resolution

### Step 3 — Resolve Registry Schema
- Query register schemas by `registry_code` and optionally service/method.
- Score candidate variants using `match_predicate`.
- Log candidate list with scores.

### Step 4 — Variant Selection
- If exactly one match above threshold: select it.
- If none match: quarantine with `schema_not_found` or `no_variant_matched`.
- If multiple match:
  - if one is strictly more specific (higher score margin): select it
  - else quarantine with `variant_ambiguous` and evidence

### Step 5 — Map to Entities
- Apply mapping rules:
  - JSONPath extraction from canonical `data`
  - transform pipeline (trim, collapse spaces, date parsing, int parsing, …)
  - create entities with `entity_ref` for within-document linking
- Entity creation requirements:
  - must not create “empty” entities:
    - enforce `require_any` / `min_fields_present`
  - must validate property types
  - must record per-entity extraction metrics

### Step 6 — Entity Resolution + Upsert to Neo4j
- Identity resolution rules:
  - Use `entity_schemas.identity_keys` in priority order
  - For each key candidate:
    - if all required properties exist: attempt to match existing entity in Neo4j
- Upsert semantics:
  - If existing found: merge properties according to change_type rules
  - If new: create node with deterministic primary key
- Conflict handling:
  - immutable conflict -> quarantine and alert (or hard fail per policy)
  - rarely_changed -> warning and keep existing (unless source_priority dictates otherwise)
  - dynamic -> update using latest source timestamp or weight

### Step 7 — Resolve Relationships
- Apply `relationship_schemas.creation_rules`.
- Must support:
  - entity_ref binding (document-scoped linking)
  - binding by identity (link to already resolved nodes)
  - conditions (exists, equals, regex, numeric comparison, …)
- Must enforce uniqueness keys and relationship merge policy.

### Step 8 — Write Result Metrics
- Update `ingested_documents` with:
  - schema_ref
  - statuses
  - neo4j write summary
- Update `ingestion_runs` metrics.

### Step 9 — Fallback / Quarantine
- Any step can quarantine document with:
  - reason category
  - excerpt or canonical snapshot
  - suggested next_action and severity
- Quarantine MUST NOT stop the batch ingestion.

### Step 10 — Notifications (optional but recommended)
- For critical categories (schema_not_found, variant_ambiguous spikes, immutable_conflict, access_denied):
  - notify developers (Slack/webhook/Jira)
- Notifications must include:
  - run_id, document_id, file_path
  - error category + summary
  - a link/ref to the quarantine record

---

## Schema rules and DSL requirements

### `match_predicate` requirements
Must support common checks:
- exists(paths)
- equals(path, value)
- regex(path, pattern)
- count(path) >= N
- any/all combinators

### Mapping DSL requirements (`mappings`)
Must support:
- `foreach`: iterate list paths
- `entity_ref`: name for document-scoped linking
- `entity_name`: target entity type
- `id_strategy`:
  - by identity key hash
  - by composite fields
  - by fallback UUID (only if nothing else)
- per-property mappings:
  - source json path
  - transform pipeline
  - required/optional
- guards:
  - `require_any`: list of fields that must exist to create entity instance
  - `require_all`: strict gating if needed

### Relationship creation rules
Must support:
- referencing entity_refs from mappings
- binding endpoints from extracted entities
- conditional checks on endpoint properties
- relationship properties from:
  - context (document_id, registry_code, timestamp)
  - endpoint properties
  - constants

---

## Data correctness and safety rules

### Normalization
- All string properties should support:
  - trim
  - collapse multiple spaces
  - unicode normalization (optional)
  - consistent casing for ids (optional)
- Dates must be:
  - parsed deterministically (ISO output)
  - timezone rules defined (default UTC for logs)

### Deduplication and consolidation
- Identity resolution MUST be deterministic.
- If multiple existing candidates match (collision):
  - quarantine with `identity_collision`
  - include candidates list in logs

### Immutability enforcement
- If `change_type=immutable` differs from stored value:
  - quarantine and alert
  - do not silently overwrite

### Access-denied / corrupt document handling
- If canonicalization detects “access denied” patterns:
  - categorize as `access_denied`
  - quarantine and mark next_action appropriately

---

## API / Interfaces

### REST API (recommended)
- `GET /health`
  - returns service status and schema backend connectivity (optional)
- `POST /ingest`
  - input: `{ file_path, source_system?, run_id?, metadata? }`
  - output: `{ run_id, document_id, status, summary }`
- `POST /ingest/batch`
  - input: list of file paths or a folder prefix
  - output: run_id and batch summary link/ref

### CLI (recommended)
- `ingest file --path ...`
- `ingest batch --prefix ...`
- flags to select backends:
  - `--schema-backend mongo|json`
  - `--graph-sink neo4j|json`
  - `--log-backend mongo|json`

---

## Configuration requirements

### Required environment variables (production)
- `MONGO_URI`, `MONGO_DB`
- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`
- `SCHEMA_BACKEND=mongo`
- `GRAPH_SINK=neo4j`
- `LOG_BACKEND=mongo`

### Local/dev support
- `SCHEMA_BACKEND=json`
- `GRAPH_SINK=json`
- `LOG_BACKEND=json`
- `SCHEMAS_DIR=./schemas`
- `OUT_DIR=./out`

---

## Observability requirements

### Metrics (must-have)
- documents processed / quarantined / failed
- schema_not_found rate
- variant_ambiguous rate
- entities extracted / upserted
- relationships created / updated
- immutable_conflict count
- processing latency per step

### Tracing
- Every log event must include:
  - run_id, document_id, step, stage, ts
- Correlation id must flow from batch trigger to all logs.

### Dashboards (recommended)
- Quarantine backlog by reason
- Top failing registry/service/method combos
- Schema drift indicators (new fields frequency)
- Immutable conflict alerts (critical)

---

## Security and compliance requirements

- No secrets in logs.
- Encrypt Mongo/Neo4j connections (TLS) where possible.
- Access control:
  - service accounts for DBs
  - principle of least privilege
- Data retention:
  - retention policy for raw payloads and canonical snapshots
  - masking rules for sensitive fields (rnokpp etc.) in logs (recommended)
- Auditability:
  - ability to reproduce output from `canonical_hash` + schema version

---

## Deployment requirements

### Containerization (recommended)
- Provide Dockerfile for service
- Provide docker-compose for local dev:
  - MongoDB
  - Neo4j
  - ingestion-service

### Reliability
- Graceful shutdown
- Idempotent processing based on `content_hash` / `canonical_hash`
- Retry with backoff for transient DB failures
- Dead-letter / quarantine for persistent failures

### Scalability
- Parallel ingestion at file/batch level
- Backpressure when Neo4j or Mongo is slow
- Batch writes for Neo4j (UNWIND with chunks)

---

## Testing requirements

### Unit tests
- canonicalization for JSON/XML/parse-error cases
- predicate engine (match_predicate)
- mapping DSL transforms and require_any gating
- identity key selection logic
- merge policy conflict handling

### Integration tests (local compose)
- with real Mongo + Neo4j
- ingest sample docs and assert:
  - correct nodes created/merged
  - correct rels created/merged
  - correct logs written

### Replay tests
- given same input + same schema versions:
  - output graph should be deterministic

---

## Definition of “production ready”

A release is production-ready when:
- Mongo structures match this contract and are actually used in runtime.
- Neo4j sink is integration-tested and enforces constraints.
- Immutable conflicts are enforced (no silent corruption).
- Relationship rules support `creation_rules` with conditions + uniqueness.
- Quarantine workflow is operational (owners, statuses, alerts).
- Observability is sufficient to debug any document in minutes:
  - you can trace from file_path -> canonical_hash -> schema variant -> entity/rel writes.

---

## Glossary

- **Registry schema**: document type description for a registry/service, including multiple variants.
- **Variant**: a specific structure version of documents for the same registry/service.
- **Canonical JSON**: normalized internal representation of raw document data.
- **Entity**: node type in Neo4j (Person, Vehicle, CourtCase, …).
- **Identity key**: prioritized matching key used for deduplication and entity resolution.
- **Quarantine**: safe failure mode storing evidence for human review, without stopping ingestion.

---
