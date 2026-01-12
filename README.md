# NABU AI Agent (Lapathon)

This repository contains the AI platform designed to consolidate and analyze data from various registries to identify risks and potential corruption.

## Project Structure

The project is organized to separate the core agent logic (which may evolve into a microservice) from experimental code and one-off maintenance scripts.

```text
.
├── agent/                  # Main Application Code (The "Brain")
│   ├── app/
│   │   ├── api/            # External interfaces (FastAPI/REST)
│   │   ├── core/           # Infrastructure & Configuration
│   │   │   └── settings.py # Application Settings
│   │   ├── models/         # Data Structures (Pydantic/Dataclasses)
│   │   ├── services/       # Business Logic & Capabilities
│   │   │   └── graph/      # Neo4j Graph Service Package
│   │   ├── tools/          # Agent Tools (Functions exposed to LLM)
│   │   └── ui/             # Developer UI (Google Mesop)
│   └── tests/              # Automated Unit & Integration Tests
├── experiments/            # Research & Prototyping
└── scripts/                # One-time Operational Scripts
```

## Directory Responsibilities

### `agent/`
Encapsulates the production-ready code.
-   **`api/`**: Entry points for external systems to interact with the agent.
-   **`core/`**: Foundational code that doesn't change often (database connections, authentication, global configuration).
-   **`models/`**: Shared type definitions used across the app to ensure data consistency.
-   **`services/`**: The "workhorses". Contains the actual logic for processing data, calculating risks, and determining graph connections. This code is imported by both `api` and `scripts`.
-   **`tools/`**: Specific abstractions that allow the LLM to interact with the `services`.
-   **`ui/`**: A lightweight frontend (using Google Mesop) for rapid testing and debugging of the agent's responses.

### `experiments/`
A sandbox for data exploration using Jupyter files. Code here is not production-critical and serves as a laboratory for testing new hypotheses or exploring the raw data structure.

### `scripts/`
Contains standalone scripts for operational tasks, such as the initial bulk data ingestion (`nabu_data`), database migrations, or manual re-indexing jobs. These scripts leverage the logic in `agent/app/services` to avoid code duplication.
