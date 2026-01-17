# Person Graph Builder

## Overview
The **Person Graph Builder** is a dynamic, AI-powered service designed to construct a comprehensive knowledge graph centered around specific persons from raw data (primarily XML). 

Unlike static ETL pipelines, this service uses Large Language Models (LLMs) to adaptively **discover schemas**, **extract complex relationships**, and **learn identity resolution rules** from the data itself.

## Core Core Concepts

1.  **Dynamic Extraction**: The system doesn't just parse XML; it interprets it. It can identify new entity types and relationships on the fly, updating its schema usage as it processes more data.
2.  **Self-Learning Resolution**: Instead of hardcoded rules (e.g., "always merge on SSN"), the `RuleGenerator` agent analyzes the extracted data to deduce the best strategies for identifying unique entities (e.g., "In this dataset, Tax ID is unique, but for people without IDs, use Name + DoB").
3.  **Graph Construction**: It builds a graph where nodes are Entities (Person, Company, Vehicle, etc.) and edges are Relationships (OWNS, FOUNDED, RELATED_TO).

## Workflow

The pipeline operates in three distinct stages, scoped by a unique `run-id`.

### 1. Ingestion & Extraction
The `main.py` entry point scans the data directory, processes files through the `Pipeline`, and stores the raw graph elements (Entities and Relationships).

**Command:**
```bash
python3 -m person_graph_builder.main --run-id <RUN_ID> --data-dir <PATH_TO_DATA> [--store-logs]
```

### 2. Rule Generation
Once the raw data is extracted, the `generate_resolution_rules.py` script samples the output. It asks an "Expert Data Architect" LLM to analyze the JSON structures and generate a `resolution_rules.json` file containing strategies for deduplication.

**Command:**
```bash
python3 -m person_graph_builder.generate_resolution_rules --run-id <RUN_ID>
```

### 3. Entity Resolution
Finally, `resolve_entities.py` applies the generated rules. It performs **Blocking** (grouping similar entities) and **Matching** (verifying identity) to merge duplicate nodes and rewire relationships, producing the final "Resolved Graph".

**Command:**
```bash
python3 -m person_graph_builder.resolve_entities --run-id <RUN_ID>
```

## Project Structure

*   **`main.py`**: Entry point for the extraction pipeline.
*   **`pipeline.py`**: Orchestrator that manages data flow, schema management, and storage.
*   **`extractor.py`**: Core logic for parsing content and extracting entites/relationships using LLMs.
*   **`discovery.py`**: A standalone tool to bootstrap the initial schema (`entity_types.json`) by analyzing valid sample files.
*   **`generate_resolution_rules.py`**: AI agent that observes data to create merging logic.
*   **`resolve_entities.py`**: The engine that executes the merge logic to creating the canonical graph.
*   **`config.py`**: Central configuration (model selection, paths, backend settings).

## Configuration

The service is configured via environment variables (loaded from `.env`) and `config.py`.

**Key Environment Variables:**
*   `OPENAI_API_KEY`: Required for LLM operations.
*   `NEO4J_URI` / `NEO4J_USERNAME` / `NEO4J_PASSWORD`: Credentials for Neo4j (if used).

**Config Options (`config.py`):**
*   `STORAGE_BACKEND`: `json` (file-based) or `neo4j`.
*   `MODEL_CONFIGS`: configuration for specific agents (e.g., temperature, model version).

## Output Structure

All artifacts for a run are stored in `outputs/<run_id>/`:

*   `output/`: The "Raw" graph. Contains `entities/`, `relationships/`, and `index.json`.
*   `schemas/`: The schemas (Entity Types, Resolution Rules) active for this run.
*   `resolved_graph/`: The final deduplicated graph.
*   `logs/`: Detailed logs of LLM requests and responses (for debugging and cost analysis).
