# Scripts Reference Guide

## Essential Scripts (5)

### 1. `reset_db.py`
**Purpose**: Wipe all data from MongoDB and Neo4j  
**⚠️ DESTRUCTIVE**: Deletes all ingested data, schemas, and graph

```bash
uv run python3 scripts/reset_db.py
```

**What it does**:
- Deletes MongoDB collections: `ingested_documents`, `quarantined_documents`, `ingestion_logs`, `ingestion_runs`, `register_schemas`, `entity_schemas`, `relationship_schemas`
- Deletes all Neo4j nodes and relationships via `MATCH (n) DETACH DELETE n`

**When to use**:
- Before schema changes to ensure clean state
- To fix corrupted data
- For full system reset

---

### 2. `init_schemas.py`
**Purpose**: Deploy schema definitions to MongoDB  
**Size**: 1000+ lines (defines entire data model)

```bash
uv run python3 scripts/init_schemas.py
```

**What it does**:
- Creates 20 entity schemas (Person, Organization, Property, Vehicle, etc.)
- Creates 15 relationship schemas (HAS_INCOME, OWNS_VEHICLE, etc.)
- Creates 11 registry schemas with 25+ variants
- Uses helper function `m()` for concise mapping definitions

**Key Registries**:
- **RRP** (Real Property): 2 variants
- **DRFO** (Tax/Income): 1 variant
- **EIS** (Passports): 1 variant (with Person/Document split)
- **ERD** (Power of Attorney): 2 variants (Answer + Vehicle/RealEstate filtering)
- **REQUEST** (Traceability): 10 variants (DRACS, DRFO, DZK, ERD, RRP, SR, Arkan, QS, JSON, XML)

**When to modify**:
- Adding new registries
- Fixing extraction paths
- Adding predicates or filters

**After modification**: Always run `reset_db.py` first to avoid schema conflicts

---

### 3. `run_batch.py`
**Purpose**: Execute batch ingestion pipeline  
**Concurrency**: Parallel processing (5 workers by default)

```bash
uv run python3 scripts/run_batch.py [--data-dir /path/to/data]
```

**What it does**:
1. Scans `data/nabu_data/` for XML/JSON files
2. Spawns worker processes (each initializes own pipeline)
3. For each file:
   - Read → Canonicalize → Resolve Schema → Map Entities → Build Relationships → Write to Neo4j
4. Logs results to MongoDB (`ingestion_logs`)
5. Reports success/quarantine counts

**Current Performance**:
- ~1.2 files/second
- ~2-3 minutes for 207 files
- Memory: ~200MB peak

**Monitoring**:
```bash
# Watch progress
tail -f run_batch.log

# Check quarantine in real-time
watch -n 5 'mongo --eval "db.quarantined_documents.count()"'
```

---

### 4. `debug.py` ⭐ NEW
**Purpose**: Consolidated debugging tool (replaces 6+ scripts)

#### Commands

**1. Debug Full Ingestion**
```bash
uv run python3 scripts/debug.py debug-file "path/to/file.xml"
```
Runs complete ingestion pipeline for a single file and shows:
- Canonicalization output
- Schema matching result
- Entity extraction
- Relationship creation
- Final Neo4j writes

**2. Show Canonical JSON**
```bash
uv run python3 scripts/debug.py canonicalize "path/to/file.xml"
```
Outputs normalized JSON structure (useful for debugging predicates)

**3. Test Predicate**
```bash
uv run python3 scripts/debug.py test-predicate \
  '{"type": "json_exists", "path": "$.data.Envelope.Body.Person"}' \
  "path/to/file.xml"
```
Tests if a predicate matches a file (returns `Matched: True/False` + score)

**4. Find File for Document ID**
```bash
uv run python3 scripts/debug.py find-doc "abc123-def456-..."
```
Looks up file path from MongoDB by document ID

**5. List Quarantine**
```bash
uv run python3 scripts/debug.py list-quarantine
```
Shows recent quarantined files with reasons

---

### 5. `verify.py` ⭐ NEW
**Purpose**: Consolidated verification suite (replaces 6+ scripts)

#### Commands

**Run All Checks**
```bash
uv run python3 scripts/verify.py --all
```

**Individual Checks**:

```bash
# Ingestion statistics
uv run python3 scripts/verify.py --stats
# Output: Success rate, quarantine breakdown by registry

# Neo4j label counts
uv run python3 scripts/verify.py --labels
# Output: Node counts per label, relationship counts per type

# Quarantine analysis
uv run python3 scripts/verify.py --quarantine
# Output: Breakdown by reason + filename (schema_not_found, parse_error)

# EIS structure validation
uv run python3 scripts/verify.py --eis
# Output: Verifies Person/Document split, HAS_DOCUMENT relationships

# Relationship integrity
uv run python3 scripts/verify.py --relationships
# Output: Counts for CourtDecision->Person, Request->Person, etc.

# Identity key coverage
uv run python3 scripts/verify.py --identity
# Output: DOCSCOPED vs GLOBAL ID ratio per entity
```

**Use cases**:
- **After full ingestion**: `--all` to validate results
- **Debugging quarantine**: `--quarantine` + `scripts/debug.py debug-file`
- **Schema changes**: `--relationships` to ensure no broken links
- **Deduplication analysis**: `--identity` to find high DOCSCOPED counts

---

## Removed Scripts (39)

**Debug Tools** (consolidated into `debug.py`):
- `debug_ingest_single.py`
- `debug_canonical.py`
- `debug_match.py`
- `debug_predicate.py`
- `debug_quarantine.py`
- `debug_answer_structure.py`
- `debug_request_json_parsing.py`
- `debug_request_parsing.py`
- `find_doc_path.py`

**Verification Tools** (consolidated into `verify.py`):
- `check_all_labels.py`
- `check_eis_structure.py`
- `check_erd_labels.py`
- `check_log.py`
- `check_metrics.py`
- `check_mongo_requests.py`
- `check_photo_cleanup.py`
- `check_relationships.py`
- `check_results.py`
- `verify_global_labels.py`
- `verify_neo4j.py`
- `verify_asset_types.py`
- `verify_request_details.py`
- `verify_requests.py`
- `verify_transform_data.py`

**Analysis Tools** (one-off investigations):
- `analyze_data_coverage.py`
- `analyze_persons.py`
- `analyze_quarantine.py`
- `analyze_quarantine_v2.py`

**Test Scripts** (should be in `tests/`):
- `test_minio.py`
- `test_mongo.py`
- `test_predicate.py`
- `test_schema_filter.py`
- `test_transform_unit.py`

**Cleanup/Legacy**:
- `cleanup_bad_vehicles.py` (one-time fix)
- `inspect_junk.py` (one-time investigation)
- `inspect_mongo.py` (replaced by verify.py)
- `inspect_neo4j_quality.py` (replaced by verify.py)
- `extract_image_from_json.py` (experimental)
- `neo4j_load_from_csv.py` (legacy loader)
- `new_nabu_to_csv_2.py` (legacy exporter)

---

## Workflow Examples

### Fresh Start
```bash
cd ingestion_job

# 1. Wipe everything
uv run python3 scripts/reset_db.py

# 2. Deploy schemas
uv run python3 scripts/init_schemas.py

# 3. Ingest all data
uv run python3 scripts/run_batch.py

# 4. Verify results
uv run python3 scripts/verify.py --all
```

### Debugging Quarantine
```bash
# 1. Check quarantine breakdown
uv run python3 scripts/verify.py --quarantine

# 2. Debug a specific file
uv run python3 scripts/debug.py debug-file "path/from/quarantine"

# 3. Test canonical output
uv run python3 scripts/debug.py canonicalize "path/from/quarantine"

# 4. Fix schema in init_schemas.py

# 5. Re-run
uv run python3 scripts/reset_db.py
uv run python3 scripts/init_schemas.py
uv run python3 scripts/run_batch.py
```

### Schema Development
```bash
# 1. Inspect sample file
cat data/nabu_data/path/to/sample.xml | head -n 50

# 2. Test canonical output
uv run python3 scripts/debug.py canonicalize "data/nabu_data/path/to/sample.xml"

# 3. Design predicate + mappings

# 4. Test predicate
uv run python3 scripts/debug.py test-predicate \
  '{"type":"json_exists","path":"$.data.MyElement"}' \
  "data/nabu_data/path/to/sample.xml"

# 5. Add to init_schemas.py

# 6. Deploy + test
uv run python3 scripts/reset_db.py
uv run python3 scripts/init_schemas.py
uv run python3 scripts/debug.py debug-file "data/nabu_data/path/to/sample.xml"
```

---

## Legacy Script (`init_mongo_schemas.py`)

**Status**: Kept for reference  
**Purpose**: Early prototype schema initializer  
**⚠️ DO NOT USE**: Replaced by `init_schemas.py`

---

**For detailed technical documentation, see [docs/TECHNICAL_DOCUMENTATION.md](../docs/TECHNICAL_DOCUMENTATION.md)**
