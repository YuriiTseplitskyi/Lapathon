
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient
from neo4j import GraphDatabase

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

# Load .env
load_dotenv(BASE_DIR / ".env")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "ingestion")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

def reset_mongo():
    print(f"Resetting MongoDB: {MONGO_DB}...")
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    
    colls = ["ingested_documents", "ingestion_logs", "quarantined_documents", "ingestion_runs", "register_schemas", "entity_schemas", "relationship_schemas"]
    for c in colls:
        count = db[c].count_documents({})
        db[c].delete_many({})
        print(f"  Deleted {count} from {c}")
    print("MongoDB reset complete.")

def reset_neo4j():
    print(f"Resetting Neo4j...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        result = session.run("MATCH (n) DETACH DELETE n")
        summary = result.consume()
        print(f"  Deleted {summary.counters.nodes_deleted} nodes and {summary.counters.relationships_deleted} relationships.")
    driver.close()
    print("Neo4j reset complete.")

if __name__ == "__main__":
    reset_mongo()
    reset_neo4j()
