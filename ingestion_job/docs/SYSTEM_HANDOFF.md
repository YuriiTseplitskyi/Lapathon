# System Handoff Report - Ingestion Service

**Date:** 2026-01-15
**Status:** Operational (Ingestion Success Rate: ~38% of total files, ~90%+ of valid 'answer' files)

## 1. System Overview

The **Ingestion Job** is a Python-based service responsible for parsing raw XML/JSON documents, normalizing them into a canonical format, resolving them against a schema registry, and projecting them into a Neo4j graph database as Entities and Relationships.

### Architecture Data Flow

1. **Raw Ingestion**: Reads files from `data_dir` (normalized path stored as `bucket/folder/file`).
2. **Canonicalization**: Converts XML/JSON into a standardized dictionary structure (`meta` headers + `data` body).
3. **Schema Resolution**:
   * Backend: MongoDB (`register_schemas` collection).
   * Logic: Evaluates "Predicates" (JSONPath existence/equality) against content to find a matching `RegisterSchemaVariant`.
   * *Note*: Strict metadata mapping (registry code) is currently **DISABLED** to support legacy/test data with inconsistent headers.
4. **Entity Mapping**: Extracts entities (nodes) based on JSONPath mappings defined in the Schema.
5. **Relationship Building**:
   * Strategy: **Global Document Scope**.
   * Logic: Connects all entities of type `Source` to all entities of type `Target` *within the same document* if a relationship schema exists. This handles Parent-Child (e.g., Property -> Right) and Root-Child (Person -> Income) relationships robustly.

## 2. Key Components & Scripts

### `scripts/init_schemas.py`

* **Purpose**: Initializes MongoDB with Schema definitions.
* **Content**: Defines mappings for 5 Registries:
  * **RRP** (Real Property): Property, Address, OwnershipRight, Person.
  * **DRFO** (Tax): IncomeRecord, Organization (TaxAgent), Person.
  * **EDR** (Business): Organization, Address, Person (Head).
  * **EIS** (Passport): Person, Document.
  * **DZK** (Land): Property (Cadastral Number).
* **Action**: Must be run after any schema change.

### `scripts/reset_db.py`

* **Purpose**: **WIPES** all data from MongoDB (ingestion collections only) and Neo4j (all nodes and relationships).
* **Use**: Run before a full re-ingestion cycle to ensure a clean state.

### `scripts/run_batch.py`

* **Purpose**: Batches processing of all files in `data/nabu_data`.
* **Concurrency**: Single-threaded (currently).

### `app/services/pipeline.py`

* **Core Logic**: Contains `IngestionPipeline`, `_map_entities`, and `_build_relationships`.
* **Recent Change**: Implemented `Global Document Scope` strategy for relationships to fix missing links.

## 3. Current State & Metrics

**Verified Run (2026-01-15 19:14):**

* **Total Files**: 208
* **Success**: 79 (Valid Schema Matches)
* **Quarantined**: 129 (Mostly `request.xml/json` which are effectively skipped/not mapped yet, or malformed/empty files).

**Graph Verification (`check_all_labels.py`):**

* **Entities**:
  * Organization: 112
  * IncomeRecord: 105
  * Property: 18
  * Person: 8
  * Address: 7
  * Document: 4
* **Relationships**:
  * PAID_INCOME: 387
  * HAS_INCOME: 105
  * RIGHT_TO: 12
  * LOCATED_AT: 12
  * ISSUED: 6
  * HAS_DOCUMENT: 4

## 4. Known Issues & Future Work

1. **Quarantine Noise**: `request.xml` and `request.json` files are currently quarantined because no schema variant is defined for them. This is expected but clogs the logs.
   * *Fix*: Define a "Skip/Ignore" schema or filter them out in `run_batch.py`.
2. **Relationship Precision**: The "Global Document Scope" connects *all* matching types in a document. If a single document contained multiple distinct Person-Income trees (unlikely in this dataset), it would create a Cartesian product.
   * *Fix*: Implement "Scope-based" relationship building if hierarchical data becomes complex.
3. **Schema Hardcoding**: `init_schemas.py` contains hardcoded mappings. Moving these to a YAML/JSON config file would be cleaner.

## 5. How to Run (Full Cycle)

To wipe the system and re-ingest everything:

```bash
cd ingestion_job

# 1. Reset Databases
uv run python3 scripts/reset_db.py

# 2. Initialize Schemas
uv run python3 scripts/init_schemas.py

# 3. Run Ingestion Batch
uv run python3 scripts/run_batch.py

# 4. Verify Results
uv run python3 scripts/check_all_labels.py
```
