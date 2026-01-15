# Ingestion Job Service

The **Ingestion Job** is responsible for parsing raw XML/JSON documents, normalizing them, resolving schemas, and populating the Neo4j Knowledge Graph.

> **⚠️ SYSTEM HANDOFF (2026-01-15)**
> A detailed report on the current system status, architecture, and known issues is available in **[docs/SYSTEM_HANDOFF.md](docs/SYSTEM_HANDOFF.md)**.
> Please review this document before making further changes.

## Quick Start (Full Reset & Re-ingest)

To wipe the database and ingest all data from `data/nabu_data`:

```bash
cd ingestion_job

# 1. Reset MongoDB & Neo4j (Wipes all data!)
uv run python3 scripts/reset_db.py

# 2. Initialize Schemas (Entities, Registers, Relationships)
uv run python3 scripts/init_schemas.py

# 3. Run Batch Ingestion
uv run python3 scripts/run_batch.py

# 4. Verify Results
uv run python3 scripts/check_all_labels.py
```

## Key Scripts

*   `scripts/init_schemas.py`: Defines the data model (Entities, Relationships, Registry Mappings). Run this if you change the schema.
*   `scripts/run_batch.py`: Main entry point for batch processing.
*   `scripts/check_metrics.py` / `scripts/check_all_labels.py`: Verification tools.
*   `scripts/debug_quarantine.py`: Inspects failed documents in MongoDB.

## Configuration

Environment variables stored in `.env` (root level):
*   `MONGO_URI` / `MONGO_DB`
*   `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD`
*   `data_dir`: Path to raw data (e.g., `.../Lapathon/data/nabu_data`).
