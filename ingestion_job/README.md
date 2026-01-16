# Ingestion Job Service

**Production-Ready Data Ingestion Pipeline** for NABU Anti-Corruption Knowledge Graph

## Current Status

- **Success Rate**: 117/207 (56.5%) files successfully ingested
- **Registries**: 11 (RRP, DRFO, EDR, EIS, DZK, DRACS, ERD, COURT, MVS, IDP, REQUEST)
- **Entities**: 20 types (Person, Organization, Property, Vehicle, etc.)
- **Relationships**: 15 types (HAS_INCOME, OWNS_VEHICLE, INVOLVES, etc.)
- **Last Updated**: 2026-01-16

📖 **[Complete Technical Documentation](docs/TECHNICAL_DOCUMENTATION.md)** - Comprehensive 100+ section guide covering architecture, data flow, schemas, and operations.

---

## Quick Start

### Prerequisites
- Python 3.11+
- MongoDB connection (Aura or local)
- Neo4j Aura connection
- `.env` file configured (see below)

### Full Ingestion Cycle

```bash
cd ingestion_job

# 1. Reset Databases (⚠️ WIPES ALL DATA!)
uv run python3 scripts/reset_db.py

# 2. Initialize Schemas
uv run python3 scripts/init_schemas.py

# 3. Run Batch Ingestion
uv run python3 scripts/run_batch.py

# 4. Verify Results
uv run python3 scripts/verify.py --all
```

---

## Essential Scripts

### Production
| Script | Purpose |
|--------|---------|
| `scripts/reset_db.py` | **Wipe databases** (MongoDB + Neo4j) |
| `scripts/init_schemas.py` | **Deploy schema definitions** (entities, relationships, registries) |
| `scripts/run_batch.py` | **Execute batch ingestion** (parallel processing) |
| `scripts/debug.py` | **Debug tool** (consolidated: canonicalize, test predicates, find docs) |
| `scripts/verify.py` | **Verification suite** (consolidated: labels, relationships, quarantine, stats) |

### Debug Commands

```bash
# Debug a specific file
uv run python3 scripts/debug.py debug-file "path/to/file.xml"

# Show canonical JSON output
uv run python3 scripts/debug.py canonicalize "path/to/file.xml"

# Test a predicate
uv run python3 scripts/debug.py test-predicate '{"type": "json_exists", "path": "$.data.Person"}' "path/to/file.xml"

# Find file for document ID
uv run python3 scripts/debug.py find-doc "abc123-..."

# List quarantined documents
uv run python3 scripts/debug.py list-quarantine
```

### Verification Commands

```bash
# Run all checks
uv run python3 scripts/verify.py --all

# Specific checks
uv run python3 scripts/verify.py --labels          # Neo4j node/relationship counts
uv run python3 scripts/verify.py --quarantine      # Analyze failed documents
uv run python3 scripts/verify.py --eis             # Verify EIS Person/Document split
uv run python3 scripts/verify.py --relationships   # Check critical relationships
uv run python3 scripts/verify.py --identity        # Analyze DOCSCOPED vs global IDs
uv run python3 scripts/verify.py --stats           # Ingestion statistics
```

---

## Configuration

Create `.env` file in `ingestion_job/` directory:

```bash
# MongoDB
MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true&w=majority
MONGO_DB=lapathon-nprd

# Neo4j Aura
NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password

# Data Path (optional, defaults to ../data/nabu_data)
data_dir=/path/to/data/nabu_data
```

---

## Architecture Overview

```
Raw Files (XML/JSON)
    ↓
Canonicalizer (Normalize to standard JSON)
    ↓
Schema Resolver (Match against MongoDB schemas)
    ↓
Entity Mapper (Extract nodes via JSONPath)
    ↓
Relationship Builder (Create edges)
    ↓
Neo4j Sink (MERGE operations)
```

**Key Components**:
- **MongoDB**: Schema storage (`register_schemas`, `entity_schemas`, `relationship_schemas`)
- **Neo4j**: Knowledge graph (entities as nodes, relationships as edges)
- **Canonicalization**: Handles XML namespaces, JSON variants, query strings, log dumps
- **Schema Matching**: JSONPath predicates with regex support
- **Identity Resolution**: Priority-based deduplication (RNOKPP → name+birthdate → DOCSCOPED)
- **Relationship Strategy**: Global document scope (all-to-all within document)

---

## Project Structure

```
ingestion_job/
├── app/
│   ├── core/           # Settings, utilities
│   ├── models/         # Pydantic schemas
│   └── services/
│       ├── canonical/  # XML/JSON adapters
│       ├── schema/     # Resolver, predicates
│       ├── graph/      # Neo4j sink
│       └── pipeline.py # Main orchestration
├── scripts/
│   ├── init_schemas.py  # Schema definitions (1000+ lines)
│   ├── reset_db.py      # Database wiper
│   ├── run_batch.py     # Batch executor
│   ├── debug.py         # Consolidated debug tool
│   └── verify.py        # Consolidated verification
├── docs/
│   └── TECHNICAL_DOCUMENTATION.md  # Complete guide
├── .env                # Configuration
└── README.md           # This file
```

---

## Known Issues & Limitations

### Remaining Quarantine (90 files):
- **77 answer.xml**: Response files (not critical for request traceability)
- **13 request variants**: Unknown formats requiring investigation

### Architectural:
- **Global Document Scope**: May create over-linking in complex documents (Cartesian product)
- **DOCSCOPED IDs**: Entities without identity keys (e.g., Address) aren't deduplicated across documents
- **Hardcoded Schemas**: `init_schemas.py` should migrate to YAML/JSON config

**See [TECHNICAL_DOCUMENTATION.md](docs/TECHNICAL_DOCUMENTATION.md) Section 7** for complete issue list and mitigations.

---

## Adding a New Registry

1. **Analyze sample data** → Identify structure
2. **Define entities** (if new) in `init_schemas.py`
3. **Create mappings** using helper function `m()`
4. **Define variant** with `match_predicate`
5. **Register** in `registers` list
6. **Deploy**: Reset → Init → Batch → Verify

**See [TECHNICAL_DOCUMENTATION.md](docs/TECHNICAL_DOCUMENTATION.md) Section 6.3** for detailed guide.

---

## Performance

**Current** (207 files):
- Ingestion Time: ~2-3 minutes
- Throughput: ~1.2 files/second
- Memory: ~200MB peak

**Scaling**:
- 10K files: ~2.3 hours (parallel recommended)
- 100K files: Distributed workers required

---

## Support & Troubleshooting

**High quarantine rate?**
```bash
uv run python3 scripts/verify.py --quarantine
uv run python3 scripts/debug.py debug-file "path/to/failed.xml"
```

**Missing relationships?**
```bash
uv run python3 scripts/verify.py --relationships --verbose
```

**Duplicate nodes?**
```bash
uv run python3 scripts/verify.py --identity --entity Person
```

**For detailed troubleshooting**, see [TECHNICAL_DOCUMENTATION.md](docs/TECHNICAL_DOCUMENTATION.md) Section 8.3.

---

## License

Internal NABU tool - Not for public distribution

---

**Last Updated**: 2026-01-16 by Antigravity AI
