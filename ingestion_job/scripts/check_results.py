
import os
import logging
from pymongo import MongoClient
from neo4j import GraphDatabase
from dotenv import load_dotenv
from pathlib import Path
import json

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

def load_env():
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH)

def check_results():
    load_env()
    
    # 1. MongoDB Check
    mongo_uri = os.getenv("MONGO_URI")
    db_name = os.getenv("MONGO_DB")
    client = MongoClient(mongo_uri)
    db = client[db_name]
    
    logger.info("=== MongoDB: ingested_documents (answer.xml) ===")
    docs = list(db.ingested_documents.find({"raw.file_path": {"$regex": "answer.xml"}}).sort("discovered_at", -1).limit(5))
    logger.info(f"Found {len(docs)} processed documents (showing max 5):")
    for d in docs:
        summary = d.get("neo4j_write_summary", {})
        logger.info(f"DocID: {d.get('document_id')}")
        logger.info(f"  Schema: {d.get('classification')}")
        logger.info(f"  Write Summary: {summary}")
    
    # 2. Neo4j Check
    neo4j_uri = os.getenv("NEO4J_URI")
    neo4j_user = os.getenv("NEO4J_USER")
    neo4j_pass = os.getenv("NEO4J_PASSWORD")
    
    logger.info("\n=== Neo4j: Data Check ===")
    try:
        driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))
        with driver.session() as session:
            # Count Persons
            count_res = session.run("MATCH (n:Person) RETURN count(n) as c")
            count = count_res.single()["c"]
            logger.info(f"Total Person nodes: {count}")
            
            # Show some Persons
            res = session.run("MATCH (n:Person) RETURN n.full_name, n.rnokpp, n.last_name LIMIT 5")
            logger.info("Sample Persons:")
            for record in res:
                logger.info(f"  - {record['n.full_name']} (RNOKPP: {record['n.rnokpp']}) [Last: {record['n.last_name']}]")
        driver.close()
    except Exception as e:
        logger.error(f"Neo4j connection failed: {e}")

if __name__ == "__main__":
    check_results()
