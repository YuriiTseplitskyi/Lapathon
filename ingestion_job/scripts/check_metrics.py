
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
load_dotenv(BASE_DIR / ".env")

from pymongo import MongoClient

def check_metrics():
    uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    client = MongoClient(uri)
    db = client["ingestion"]
    
    # Get last run
    last_run = db.ingestion_runs.find_one(sort=[("started_at", -1)])
    if not last_run:
        print("No ingestion runs found.")
        return

    print(f"Run ID: {last_run.get('run_id')}")
    print(f"Status: {last_run.get('status')}")
    print(f"Metrics: {last_run.get('metrics')}")
    
    # Check skipped/quarantined details
    processed = db.ingested_documents.count_documents({"run_id": last_run['run_id'], "ingestion_status": "processed"})
    quarantined = db.ingested_documents.count_documents({"run_id": last_run['run_id'], "ingestion_status": "quarantined"})
    pending = db.ingested_documents.count_documents({"run_id": last_run['run_id'], "ingestion_status": "pending"})
    
    print(f"Processed: {processed}")
    print(f"Quarantined: {quarantined}")
    print(f"Pending: {pending}")

    # Show some errors
    print("\n--- Sample Failures ---")
    failures = db.ingested_documents.find(
        {"run_id": last_run['run_id'], "ingestion_status": {"$in": ["failed", "quarantined"]}}
    ).limit(5)
    
    for f in failures:
        print(f"Doc: {f.get('raw', {}).get('file_path')}")
        print(f"Status: {f.get('ingestion_status')}")
        if 'details' in f.get('failure', {}):
            print(f"Details: {f['failure']['details']}")
        print(f"Run ID: {f.get('run_id')}")

    # Aggregated Stats
    print("\n--- Neo4j Write Stats ---")
    pipeline = [
        {"$match": {"run_id": last_run['run_id']}},
        {"$group": {
            "_id": None,
            "nodes_created": {"$sum": "$neo4j_write_summary.nodes_created"},
            "nodes_updated": {"$sum": "$neo4j_write_summary.nodes_updated"},
            "rels_created": {"$sum": "$neo4j_write_summary.rels_created"},
            "rels_updated": {"$sum": "$neo4j_write_summary.rels_updated"}
        }}
    ]
    stats = list(db.ingested_documents.aggregate(pipeline))
    if stats:
        print(stats[0])
    
if __name__ == "__main__":
    check_metrics()
