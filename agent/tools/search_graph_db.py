from __future__ import annotations

import json
from typing import Any, Dict, List

from neo4j import GraphDatabase

from agent.config import AgentConfig

from agents import function_tool

def search_graph_db(query: str, cfg: AgentConfig) -> str:
    """
    Execute a Cypher query against Neo4j and return JSON results.

    Args:
        query: Cypher query to execute against the database.
    """
    q = (query or "").strip()
    if not q:
        return json.dumps({"error": "Empty query"}, ensure_ascii=False)

    if not cfg.allow_write_queries:
        blocked = ("CREATE", "MERGE", "DELETE", "SET", "DROP", "CALL", "LOAD CSV", "APOC")
        upper = q.upper()
        if any(tok in upper for tok in blocked):
            return json.dumps(
                {
                    "error": "Write/procedure queries are disabled.",
                    "hint": "Use MATCH/RETURN (read-only) queries.",
                },
                ensure_ascii=False,
            )

    try:
        auth = (cfg.neo4j_user, cfg.neo4j_password)
        with GraphDatabase.driver(cfg.neo4j_uri, auth=auth) as driver:
            kwargs: Dict[str, Any] = {}
            if cfg.neo4j_database:
                kwargs["database"] = cfg.neo4j_database

            with driver.session(**kwargs) as session:
                result = session.run(q)
                records: List[Dict[str, Any]] = [r.data() for r in result]
                return json.dumps(records, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": f"Neo4j query failed: {exc}"}, ensure_ascii=False)

def make_query_graph_db(cfg: AgentConfig):
    """
    Create a function tool for querying the graph database with config bound.
    """

    @function_tool
    def query_graph_db(query: str) -> str:
        """
        Execute a Cypher query against the Neo4j graph database.

        Args:
            query: Cypher query to execute.
        """
        return search_graph_db(query, cfg)

    return query_graph_db