# NABU AI Agent (Lapathon)

This repository contains the AI platform designed to consolidate and analyze data from various registries to identify risks and potential corruption.

## Project Structure

The project is evolved into a set of specialized microservices, each handling a specific part of the data pipeline: ingestion, schema management, risk detection, and profile generation.

```text
.
├── detection_service/  # Risk analysis and fraud detection
├── ingestion_job/      # Data ingestion into Neo4j
├── profile_creator/    # Consolidated profile generation
└── schema_updater/	# Schema inference and management
```

## Services Overview

### 1. Ingestion Job (`ingestion_job/`)

Responsible for the initial ingestion of data into the Graph Database (Neo4j).

* **Purpose**: Polls for unprocessed documents (e.g., from a MinIO bucket) and ingests nodes and relations into the Neo4j graph.
* **Trigger**: Configured to run once per day or on-demand.
* **Process**: Takes schema-parsed data and loads it into the graph.
* **Inputs**: JSON, XML, HTML, tabular, and text files.

### 2. Schema Updater (`schema_updater/`)

Manages the understanding of data structures from various registries.

* **Purpose**: Automatically detects and updates the schema for registry data.
* **Trigger**: Triggered when a new register folder is created in the bucket or when the Ingest Service detects a schema change.
* **Capabilities**:
  * Parses files to generate candidates for new Entities or Relations.
  * Writes new schemas to the MongoDB Schema/Entity Registry.
  * Notifies human operators if a new entity candidate requires verification.

### 3. Detection Service (`detection_service/`)

The core analytical engine for identifying potential issues.

* **Purpose**: Runs algorithmic searches on the graph and other data sources to find inconsistencies, hidden links, or violations.
* **Capabilities**:
  * Detects "hidden" links between entities.
  * Identifies data inconsistencies.
  * Flags positive fraud results for review.
  * **Future**: May include an "Accuracy/Time Balance" logic to decide whether to flag a potential risk (False Positive) or ignore it to save analyst time.

### 4. Profile Creator (`profile_creator/`)

Synthesizes scattered data into a coherent view.

* **Purpose**: Aggregates data from Neo4j and other sources to create a consolidated profile for a Person or Entity.
* **Output**: Writes consolidated profiles to the Profiles collection in MongoDB.
* **Validation**: Includes a validation layer (LLM/Human/Combined) to ensure the generated profile is accurate before final storage.

## Data Flow Summary

1. **Ingestion**: Files arrive in MinIO -> `ingestion_job` puts them into Neo4j.
2. **Schema**: If data structure changes -> `schema_updater` adapts the schema in MongoDB.
3. **Analysis**: `detection_service` scans the graph for suspicious patterns.
4. **Reporting**: `profile_creator` builds a comprehensive profile for analysts to review.
