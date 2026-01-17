# Profile Creator Service

## Overview
The **Profile Creator** is a FastAPI-based microservice designed to generate comprehensive, human-readable profiles (dossiers) for entities within the Knowledge Graph.

It queries the Neo4j database to aggregate all known information, relationships, and context about a specific person or company, and renders this into a standardized format (PDF).

## Features
*   **Profile Aggregation**: Fetches deep graph data for a given entity ID.
*   **PDF Generation**: Uses `fpdf2` to create professional reports.
*   **REST API**: Exposes endpoints to trigger profile creation on-demand.

## Tech Stack
*   **Framework**: FastAPI
*   **Database**: Neo4j (via driver)
*   **PDF Engine**: fpdf2
*   **Runtime**: Python 3.12+

## Installation

```bash
pip install -r requirements.txt
```

## Setup
Copy the example environment file and configure your credentials:

```bash
cp .env.example .env
```

## Usage

Start the API server:

```bash
python main.py
```

The service will be available at `http://localhost:8000`.
API Documentation (Swagger UI) is available at `http://localhost:8000/docs`.

## Key Endpoints

*   `GET /api/v1/profiles/{entity_id}`: Generates a profile for the specified entity.