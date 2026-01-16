from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

SchemaBackend = Literal["mongo", "json"]
GraphSinkType = Literal["neo4j", "json"]
LogBackend = Literal["mongo", "json"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Backends
    schema_backend: SchemaBackend = "mongo"
    log_backend: LogBackend = "mongo"
    graph_sink: GraphSinkType = "neo4j"

    # Paths
    # defaulted to relative paths from this file if not set in env
    schemas_dir: Path = Path(__file__).resolve().parents[2] / "data" / "schemas"
    out_dir: Path = Path(__file__).resolve().parents[2] / "data" / "out"
    data_dir: Optional[Path] = None

    # Mongo
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "ingestion"

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    neo4j_database: Optional[str] = None

    # Run metadata
    run_id: str = ""

    # Validation
    validate_immutable: bool = True

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False
    minio_bucket_court: str = "court-documents"
    minio_bucket_photos: str = "person-photos"

    def ensure_out_dirs(self) -> None:
        # Only create directories if using JSON backends
        if "json" in (self.log_backend, self.graph_sink, self.schema_backend):
            self.out_dir.mkdir(parents=True, exist_ok=True)
            (self.out_dir / "quarantine").mkdir(parents=True, exist_ok=True)
            (self.out_dir / "logs").mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    return Settings()
