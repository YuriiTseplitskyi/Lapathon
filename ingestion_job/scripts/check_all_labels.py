
import os
import sys
from neo4j import GraphDatabase
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
load_dotenv(BASE_DIR / ".env")

def check():
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")
    
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    with driver.session() as session:
        # Count by label
        res = session.run("MATCH (n) RETURN labels(n) as labels, count(n) as count ORDER BY count DESC")
        print("\n=== Node Counts by Label ===")
        for r in res:
            print(f"{r['labels']}: {r['count']}")
            
        # Count by relationship type
        res = session.run("MATCH ()-[r]->() RETURN type(r) as type, count(r) as count ORDER BY count DESC")
        print("\n=== Relationship Counts ===")
        for r in res:
            print(f"{r['type']}: {r['count']}")

    driver.close()

if __name__ == "__main__":
    check()
