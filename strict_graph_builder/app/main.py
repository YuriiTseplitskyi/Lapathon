from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ingestion_job.app.core.settings import Settings, get_settings
from ingestion_job.app.services.pipeline import IngestionPipeline


app = FastAPI(title="Ingestion Service", version="0.1.0")


class IngestRequest(BaseModel):
    file_path: str


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok"}


@app.post("/ingest")
def ingest(req: IngestRequest) -> Dict[str, Any]:
    settings = get_settings()
    pipeline = IngestionPipeline(settings)
    try:
        res = pipeline.ingest_file(req.file_path)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        pipeline.close()


def cli() -> None:
    parser = argparse.ArgumentParser(description="Ingestion Service CLI")
    parser.add_argument("file", help="Path to file to ingest")
    parser.add_argument("--schema-backend", choices=["json", "mongo"], default=os.getenv("SCHEMA_BACKEND", "json"))
    parser.add_argument("--graph-sink", choices=["json", "neo4j"], default=os.getenv("GRAPH_SINK", "json"))
    parser.add_argument("--log-backend", choices=["json", "mongo"], default=os.getenv("LOG_BACKEND", "json"))
    parser.add_argument("--schemas-dir", default=os.getenv("SCHEMAS_DIR"))
    parser.add_argument("--out-dir", default=os.getenv("OUT_DIR"))
    args = parser.parse_args()

    settings = Settings()
    settings.schema_backend = args.schema_backend
    settings.graph_sink = args.graph_sink
    settings.log_backend = args.log_backend
    if args.schemas_dir:
        settings.schemas_dir = Path(args.schemas_dir)
    if args.out_dir:
        settings.out_dir = Path(args.out_dir)

    pipeline = IngestionPipeline(settings)
    try:
        result = pipeline.ingest_file(args.file)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        pipeline.close()


if __name__ == "__main__":
    cli()
