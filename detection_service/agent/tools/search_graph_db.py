from __future__ import annotations

from langchain_core.tools import tool

from agent.config import AgentConfig
from agent.neo4j import Neo4jGraphService


def make_search_graph_db_tool(cfg: AgentConfig):
    service = Neo4jGraphService(cfg)

    @tool("search_graph_db")
    def search_graph_db(query: str) -> str:
        """
        Query the Neo4j graph database using Cypher queries.
        Args:
            query: A Cypher query string to execute against the Neo4j database.
        Returns:
            JSON string with query results (list of records as dicts).
        """
        return service.run_query(query)

    return search_graph_db
