# NABU AI Agent (Lapathon)

This repository contains the AI platform designed to consolidate and analyze data from various registries to identify risks and potential corruption.

## Project Structure

The project is evolved into a set of specialized microservices, each handling a specific part of the data pipeline: ingestion, schema management, risk detection, and profile generation.

```text
.
├── person_graph_builder/   # Targeted AI graph investigation
├── strict_graph_builder/   # Global strict-schema graph ingestion
├── detection_service/      # AI corruption risk agent
├── profile_creator/        # Profile synthesis & PDF generation
└── schema_updater/         # Schema inference and management
```

## Services Overview

### 1. Person Graph Builder (`person_graph_builder/`)
**Targeted Investigation Service (AI-Driven)**
*   **Scope**: **Microscopic / Specific Person**.
*   **Method**: AI agents extract unstructured data, infer schemas, and resolve identities probabilistically.
*   **Use Case**: "Deep Dive" into a specific suspect where data is messy or unstructured.

### 2. Strict Graph Builder (`strict_graph_builder/`)
**Global Graph Service (Rule-Based)**
*   **Scope**: **Macroscopic / Population Scale**.
*   **Method**: High-throughput ingestion of structured registry data using strict schemas.
*   **Use Case**: Building the "Background Graph" of all people and companies to find paths and connections.

### 3. Schema Updater (`schema_updater/`)

Manages the understanding of data structures from various registries.

* **Purpose**: Automatically detects and updates the schema for registry data.
* **Trigger**: Triggered when a new register folder is created in the bucket or when the Ingest Service detects a schema change.
* **Capabilities**:
  * Parses files to generate candidates for new Entities or Relations.
  * Writes new schemas to the MongoDB Schema/Entity Registry.
  * Notifies human operators if a new entity candidate requires verification.

### 4. Detection Service (`detection_service/`)
**Corruption Investigation Agent**
*   **Purpose**: A LangGraph-based agent that orchestrates complex investigations.
*   **Workflow**:
    1.  **Family Builder**: Reconstructs family trees.
    2.  **Income Analysis**: Compares declared income vs. assets.
    3.  **Proxy Ownership**: Detects assets hidden under relatives/associates.
    4.  **Shell Companies**: Uncovers complex ownership structures.
*   **Output**: Detailed corruption risk reports in Ukrainian.

### 5. Profile Creator (`profile_creator/`)

Synthesizes scattered data into a coherent view.

* **Purpose**: Aggregates data from Neo4j and other sources to create a consolidated profile for a Person or Entity.
* **Output**: Writes consolidated profiles to the Profiles collection in MongoDB.
* **Validation**: Includes a validation layer (LLM/Human/Combined) to ensure the generated profile is accurate before final storage.

## Data Flow Summary

1. **Ingestion**: Files arrive in MinIO -> `strict_graph_builder` puts them into Neo4j "Global Graph".
2. **Schema**: If data structure changes -> `schema_updater` adapts the schema in MongoDB.
3. **Analysis**: `detection_service` scans the graph for suspicious patterns.
4. **Reporting**: `profile_creator` builds a comprehensive profile for analysts to review.
