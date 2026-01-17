from __future__ import annotations
from typing import Dict, Any, List

from ingestion_job.app.services.sinks.base import LogStore, DocumentStore, QuarantineStore
from ingestion_job.app.models.mongo import IngestionLog, IngestedDocument, QuarantinedDocument, IngestionRun

try:
    from pymongo import MongoClient
except ImportError:
    MongoClient = None

class MongoLogStore(LogStore):
    def __init__(self, mongo_uri: str, db_name: str):
        if MongoClient is None:
            raise RuntimeError("pymongo is not installed; install pymongo to use log_backend=mongo")
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.col = self.db["ingestion_logs"]

    def log(self, record: IngestionLog) -> None:
        self.col.insert_one(record.model_dump(mode='json'))

class MongoDocumentStore(DocumentStore):
    def __init__(self, mongo_uri: str, db_name: str):
        if MongoClient is None:
            raise RuntimeError("pymongo is not installed; install pymongo to use log_backend=mongo")
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.col_docs = self.db["ingested_documents"]
        self.col_runs = self.db["ingestion_runs"]

    def write(self, record: IngestedDocument) -> None:
        # Upsert by document_id
        self.col_docs.replace_one(
            {"document_id": record.document_id},
            record.model_dump(mode='json'),
            upsert=True
        )

    def write_run(self, record: IngestionRun) -> None:
        self.col_runs.replace_one(
            {"run_id": record.run_id},
            record.model_dump(mode='json'),
            upsert=True
        )

class MongoQuarantineStore(QuarantineStore):
    def __init__(self, mongo_uri: str, db_name: str):
        if MongoClient is None:
            raise RuntimeError("pymongo is not installed; install pymongo to use log_backend=mongo")
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.col = self.db["quarantined_documents"]

    def quarantine(self, record: QuarantinedDocument) -> None:
        # Check for existing open quarantine for this file
        if record.file_path:
            self.col.delete_many({
                "file_path": record.file_path,
                "status": "open"
            })
        self.col.insert_one(record.model_dump(mode='json'))
