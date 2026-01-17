from __future__ import annotations
from typing import Dict, Any, List

from ingestion_job.app.models.graph import NodeRecord, RelRecord
from ingestion_job.app.models.mongo import IngestionLog, IngestedDocument, QuarantinedDocument, IngestionRun

class LogStore:
    def log(self, record: IngestionLog) -> None:
        raise NotImplementedError

class DocumentStore:
    def write(self, record: IngestedDocument) -> None:
        raise NotImplementedError
    
    def write_run(self, record: IngestionRun) -> None:
        raise NotImplementedError

class QuarantineStore:
    def quarantine(self, record: QuarantinedDocument) -> None:
        raise NotImplementedError

class GraphSink:
    def close(self) -> None:
        pass

    def upsert_nodes(self, nodes: List[NodeRecord]) -> Dict[str, Any]:
        raise NotImplementedError

    def upsert_relationships(self, rels: List[RelRecord]) -> Dict[str, Any]:
        raise NotImplementedError
