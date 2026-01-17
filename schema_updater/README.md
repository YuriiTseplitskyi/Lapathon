# Schema Updater Agent

## Overview
The **Schema Updater Agent** is a specialized service responsible for maintaining, validating, and evolving the data schemas used across the platform.

It ensures that the data ingested from various registries aligns with the expected definitions, and provides mechanisms to update these definitions when new data formats are encountered.

## Key Components

*   **Registry Manager**: Manages the lifecycle of registry schemas (e.g., entity types, field definitions).
*   **Validator**: Checks if incoming data complies with the active schemas.
*   **Alignment Service**: Provides APIs (`/api/v1/align`) to check or enforce alignment between data and schema.

## Setup

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Configuration**:
    Copy `.env.example` to `.env`:
    ```bash
    cp .env.example .env
    ```
    *   Set `API_KEY` for LLM access (used for schema inference).
    *   Set `MONGO_URI` for schema storage.

## Usage

Start the service:
```bash
python main.py
```

The service runs on port 8000 by default.

## API

*   `POST /api/v1/align`: Endpoint to trigger schema alignment or validation processes.
