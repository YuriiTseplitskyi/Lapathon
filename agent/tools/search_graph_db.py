from __future__ import annotations

from langchain_core.tools import tool

from agent.config import AgentConfig
from agent.neo4j import Neo4jGraphService


def make_search_graph_db_tool(cfg: AgentConfig):

    service = Neo4jGraphService(cfg)

    @tool("search_graph_db")
    def search_graph_db(query: str) -> str:
        """
        Execute a Cypher query against the Neo4j graph database.

        Use this tool to retrieve data from the graph. Write READ-ONLY queries
        using MATCH ... RETURN syntax. Return only necessary fields with explicit
        aliases for clarity.

        Args:
            query: A Cypher query string to execute. Must be a read-only query
                (MATCH, RETURN, WHERE, ORDER BY, LIMIT, etc.).

        Returns:
            JSON string containing query results as a list of record dictionaries.
            Returns an empty list "[]" if no matching records are found.

        Example:
            query: "MATCH (p:Person) WHERE p.last_name = 'Smith' RETURN p.full_name AS name LIMIT 10"
        """
        return service.run_query(query)

    return search_graph_db
