from __future__ import annotations
from typing import Tuple

from ingestion_job.app.core.settings import Settings
from ingestion_job.app.services.sinks.base import LogStore, DocumentStore, QuarantineStore, GraphSink
from ingestion_job.app.services.sinks.json_store import JsonLogStore, JsonDocumentStore, JsonQuarantineStore, JsonGraphSink
from ingestion_job.app.services.sinks.mongo_store import MongoLogStore, MongoDocumentStore, MongoQuarantineStore
from ingestion_job.app.services.sinks.neo4j_sink import Neo4jGraphSink

def create_sinks(settings: Settings) -> Tuple[LogStore, DocumentStore, QuarantineStore, GraphSink]:
    # Log/Doc/Quarantine Backends
    if settings.log_backend == "mongo":
        log_store = MongoLogStore(settings.mongo_uri, settings.mongo_db)
        doc_store = MongoDocumentStore(settings.mongo_uri, settings.mongo_db)
        quarantine_store = MongoQuarantineStore(settings.mongo_uri, settings.mongo_db)
    else:
        log_store = JsonLogStore(settings.out_dir)
        doc_store = JsonDocumentStore(settings.out_dir)
        quarantine_store = JsonQuarantineStore(settings.out_dir)

    # Graph Sink
    if settings.graph_sink == "json":
        graph_sink = JsonGraphSink(settings.out_dir)
    else:
        graph_sink = Neo4jGraphSink(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
            database=settings.neo4j_database,
        )

    return log_store, doc_store, quarantine_store, graph_sink
