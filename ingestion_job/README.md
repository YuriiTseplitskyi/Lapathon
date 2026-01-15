# Ingestion Service (minimal)

This is a minimal ingestion microservice prototype.

## What it does (high-level)
- Reads raw XML/JSON files.
- Converts them into a canonical JSON envelope: `{"meta": {...}, "data": ...}`.
- Resolves a register schema variant using `schemas/register_schemas.json`.
- Maps canonical JSON into entity instances using variant mappings.
- Builds relationships using `schemas/relationship_schemas.json`.
- Writes outputs:
  - `out/graph_snapshot.json` (JSON sink)
  - `out/logs/*.jsonl` (ingestion logs, ingested documents, quarantine index)
  - `out/quarantine/*.canonical.json` (quarantined docs)

## Switching backends
Environment variables (prod defaults):
- `SCHEMA_BACKEND` = `mongo` | `json`
- `GRAPH_SINK` = `neo4j` | `json`
- `LOG_BACKEND` = `mongo` | `json`

In the sandbox tests we use `json/json/json`.

## Run sanity check
```bash
python -m ingestion_service.tests.sanity_check
```

or:

```bash
python /mnt/data/ingestion_service/tests/sanity_check.py
```

## CLI ingest
```bash
python -m app.main /path/to/file --schema-backend json --graph-sink json --log-backend json --schemas-dir ./schemas --out-dir ./out
```
