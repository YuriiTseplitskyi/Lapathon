from __future__ import annotations

import json
from typing import Any, Dict, List

from neo4j import GraphDatabase

from agent.app.core.settings import AgentConfig


class Neo4jGraphService:
    """
    Thin wrapper around the Neo4j driver to execute read-only Cypher queries.
    """

    def __init__(self, cfg: AgentConfig):
        self.cfg = cfg

    def run_query(self, query: str) -> str:
        q = (query or "").strip()
        if not q:
            return json.dumps({"error": "Empty query"}, ensure_ascii=False)

        if not self.cfg.allow_write_queries:
            blocked = ("CREATE", "MERGE", "DELETE", "SET", "DROP", "CALL", "LOAD CSV", "APOC")
            upper = q.upper()
            if any(tok in upper for tok in blocked):
                return json.dumps(
                    {
                        "error": "Write/procedure queries are disabled for this agent.",
                        "hint": "Use MATCH/RETURN (read-only) queries.",
                    },
                    ensure_ascii=False,
                )

        try:
            auth = (self.cfg.neo4j_user, self.cfg.neo4j_password)
            with GraphDatabase.driver(self.cfg.neo4j_uri, auth=auth) as driver:
                kwargs: Dict[str, Any] = {}
                if self.cfg.neo4j_database:
                    kwargs["database"] = self.cfg.neo4j_database

                with driver.session(**kwargs) as session:
                    result = session.run(q)
                    records: List[Dict[str, Any]] = [r.data() for r in result]
                    return json.dumps(records, ensure_ascii=False)
        except Exception as exc:  # pragma: no cover - defensive logging path
            return json.dumps({"error": f"Neo4j query failed: {exc}"}, ensure_ascii=False)
