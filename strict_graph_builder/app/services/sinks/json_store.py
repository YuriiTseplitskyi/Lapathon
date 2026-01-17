from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple
from datetime import datetime

from ingestion_job.app.models.graph import NodeRecord, RelRecord
from ingestion_job.app.services.sinks.base import LogStore, DocumentStore, QuarantineStore, GraphSink
from ingestion_job.app.models.mongo import IngestionLog, IngestedDocument, QuarantinedDocument, IngestionRun

def jsonencoder(o: Any) -> Any:
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)

def jsonl_append(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, default=jsonencoder) + "\n")

class JsonLogStore(LogStore):
    def __init__(self, out_dir: Path):
        self.path = out_dir / "logs" / "ingestion_logs.jsonl"

    def log(self, record: IngestionLog) -> None:
        jsonl_append(self.path, record.model_dump(mode='json'))

class JsonDocumentStore(DocumentStore):
    def __init__(self, out_dir: Path):
        self.path = out_dir / "ingested_documents.jsonl"
        self.run_path = out_dir / "ingestion_runs.jsonl"

    def write(self, record: IngestedDocument) -> None:
        jsonl_append(self.path, record.model_dump(mode='json'))

    def write_run(self, record: IngestionRun) -> None:
        jsonl_append(self.run_path, record.model_dump(mode='json'))

class JsonQuarantineStore(QuarantineStore):
    def __init__(self, out_dir: Path):
        self.path = out_dir / "quarantine" / "quarantined.jsonl"

    def quarantine(self, record: QuarantinedDocument) -> None:
        jsonl_append(self.path, record.model_dump(mode='json'))

class JsonGraphSink(GraphSink):
    def __init__(self, out_dir: Path):
        self.path_nodes = out_dir / "graph_nodes.jsonl"
        self.path_rels = out_dir / "graph_rels.jsonl"
        self.snapshot_path = out_dir / "graph_snapshot.json"
        
        # In-memory snapshot for small scale debug
        self.nodes: List[Dict[str, Any]] = []
        self.rels: List[Dict[str, Any]] = []

    def close(self) -> None:
        # Write snapshot at end
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        self.snapshot_path.write_text(json.dumps({
            "nodes": self.nodes,
            "relationships": self.rels
        }, indent=2, default=jsonencoder), encoding="utf-8")

    def upsert_nodes(self, nodes: List[NodeRecord]) -> Dict[str, Any]:
        count = 0
        for n in nodes:
            record = {"label": n.label, "id": n.node_id, "properties": n.properties}
            jsonl_append(self.path_nodes, record)
            self.nodes.append(record)
            count += 1
        return {"nodes_upserted": count}

    def upsert_relationships(self, rels: List[RelRecord]) -> Dict[str, Any]:
        count = 0
        for r in rels:
            record = {
                "type": r.rel_type,
                "from": {"label": r.from_label, "id": r.from_id},
                "to": {"label": r.to_label, "id": r.to_id},
                "properties": r.properties
            }
            jsonl_append(self.path_rels, record)
            self.rels.append(record)
            count += 1
        return {"relationships_created": count}
