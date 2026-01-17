from typing import Dict, Any, List
from ..config import Config

try:
    from neo4j import GraphDatabase
except ImportError:
    GraphDatabase = None

class Neo4jStore:
    def __init__(self, uri, username, password):
        if not GraphDatabase:
            raise ImportError("neo4j package not found")
            
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        
    def close(self):
        if self.driver:
            self.driver.close()

    def clear_database(self):
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
            print("Database cleared.")

    def upsert_node(self, label: str, properties: Dict[str, Any]):
        node_id = properties.get("id") or properties.get("code") or properties.get("rnokpp")
        if not node_id:
            return

        query = f"""
        MERGE (n:{label} {{id: $id}})
        SET n += $props
        """
        # Ensure id is in props for SET += (though redundant if MERGE worked)
        properties["id"] = str(node_id)
        
        with self.driver.session() as session:
            session.run(query, id=str(node_id), props=self._sanitize_props(properties))

    def upsert_relationship(self, rel: Dict[str, Any]):
        # rel: {type, from_label, from_id, to_label, to_id, properties}
        
        from_label = rel.get("from_label")
        from_id = rel.get("from_id")
        to_label = rel.get("to_label")
        to_id = rel.get("to_id")
        rel_type = rel.get("type", "RELATED_TO")
        props = rel.get("properties", {})
        
        if not (from_label and from_id and to_label and to_id):
            return

        query = f"""
        MATCH (a:{from_label} {{id: $from_id}})
        MATCH (b:{to_label} {{id: $to_id}})
        MERGE (a)-[r:{rel_type}]->(b)
        SET r += $props
        """
        
        with self.driver.session() as session:
            session.run(query, from_id=str(from_id), to_id=str(to_id), props=self._sanitize_props(props))

    def _sanitize_props(self, props: Dict[str, Any]) -> Dict[str, Any]:
        """
        Converts nested dicts/lists to JSON strings because Neo4j 
        doesn't support complex types as properties.
        """
        import json
        sanitized = {}
        for k, v in props.items():
            if isinstance(v, (dict, list)):
                try:
                    sanitized[k] = json.dumps(v, ensure_ascii=False)
                except (TypeError, ValueError):
                    # Fallback if not serializable
                    sanitized[k] = str(v)
            else:
                sanitized[k] = v
        return sanitized
