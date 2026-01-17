from __future__ import annotations
from typing import Dict, Any, List, Optional

from ingestion_job.app.models.graph import NodeRecord, RelRecord
from ingestion_job.app.services.sinks.base import GraphSink

try:
    from neo4j import GraphDatabase
except ImportError:
    GraphDatabase = None

class Neo4jGraphSink(GraphSink):
    def __init__(self, uri: str, user: str, password: str, database: Optional[str] = None):
        if GraphDatabase is None:
            raise RuntimeError("neo4j driver is not installed; install neo4j to use GRAPH_SINK=neo4j")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.database = database

    def close(self) -> None:
        self.driver.close()

    def upsert_nodes(self, nodes: List[NodeRecord]) -> Dict[str, Any]:
        by_label: Dict[str, List[NodeRecord]] = {}
        for n in nodes:
            by_label.setdefault(n.label, []).append(n)

        total = 0
        with self.driver.session(database=self.database) as session:
            for label, items in by_label.items():
                cypher = f"""
                UNWIND $rows AS row
                MERGE (n:{label} {{id: row.id}})
                SET n += row.props
                """
                rows = [{"id": i.node_id, "props": i.properties} for i in items]
                session.execute_write(lambda tx: tx.run(cypher, rows=rows))
                total += len(items)
        return {"nodes_upserted": total}

    def upsert_relationships(self, rels: List[RelRecord]) -> Dict[str, Any]:
        total = 0
        with self.driver.session(database=self.database) as session:
            for r in rels:
                cypher = f"""
                MATCH (a:{r.from_label} {{id: $from_id}})
                MATCH (b:{r.to_label} {{id: $to_id}})
                MERGE (a)-[rel:{r.rel_type}]->(b)
                SET rel += $props
                """
                session.execute_write(lambda tx: tx.run(cypher, from_id=r.from_id, to_id=r.to_id, props=r.properties))
                total += 1
        return {"relationships_upserted": total}
