#!/usr/bin/env python3
"""
Consolidated Verification Tool
Replaces: check_all_labels.py, check_eis_structure.py, check_relationships.py,
          verify_global_labels.py, analyze_quarantine_v2.py, check_metrics.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient
from neo4j import GraphDatabase

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
load_dotenv(BASE_DIR / ".env")

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")


def check_labels():
    """Verify node and relationship counts in Neo4j"""
    print("\\n=== Neo4j Label Verification ===\\n")
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session() as session:
        # Node counts
        result = session.run("MATCH (n) RETURN labels(n) as labels, count(*) as count ORDER BY count DESC")
        print("Nodes:")
        for record in result:
            labels = ":".join(record["labels"])
            print(f"  {labels}: {record['count']}")
        
        # Relationship counts
        result = session.run("MATCH ()-[r]->() RETURN type(r) as type, count(*) as count ORDER BY count DESC")
        print("\\nRelationships:")
        for record in result:
            print(f"  {record['type']}: {record['count']}")
    
    driver.close()


def check_quarantine():
    """Analyze quarantined documents"""
    print("\\n=== Quarantine Analysis ===\\n")
    
    client = MongoClient(MONGO_URI, tlsAllowInvalidCertificates=True)
    db = client[MONGO_DB]
    coll = db["quarantined_documents"]
    
    total = coll.count_documents({})
    print(f"Total Quarantined: {total}\\n")
    
    # Group by reason and filename
    pipeline = [
        {
            "$project": {
                 "reason": 1,
                 "filename": {"$arrayElemAt": [{"$split": ["$file_path", "/"]}, -1]},
                 "file_path": 1
            }
        },
        {"$group": {"_id": {"reason": "$reason", "filename": "$filename"}, "count": {"$sum": 1}, "files": {"$push": "$file_path"}}}
    ]
    
    results = list(coll.aggregate(pipeline))
    
    print("Reasons & Filenames:")
    for r in results:
        print(f"Reason: {r['_id']['reason']} | File: {r['_id']['filename']} | Count: {r['count']}")
        print(f"Sample Files: {r['files'][:3]}")
        print("-" * 20)
    
    client.close()


def check_eis_structure():
    """Verify EIS Person/Document split"""
    print("\\n=== EIS Structure Verification ===\\n")
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session() as session:
        # Check Person nodes don't have passport props
        result = session.run("""
            MATCH (p:Person)
            WHERE p.source_doc_id STARTS WITH 'EIS'
              AND (p.passport_number IS NOT NULL OR p.passport_series IS NOT NULL)
            RETURN count(p) as bad_count
        """)
        bad_count = result.single()["bad_count"]
        
        if bad_count > 0:
            print(f"❌ Found {bad_count} Person nodes with passport properties")
        else:
            print("✅ All Person nodes clean (no passport props)")
        
        # Check Document nodes exist
        result = session.run("""
            MATCH (d:Document)
            WHERE d.source_doc_id STARTS WITH 'EIS'
            RETURN count(d) as doc_count
        """)
        doc_count = result.single()["doc_count"]
        
        print(f"✅ Found {doc_count} Document nodes from EIS")
        
        # Check relationships
        result = session.run("""
            MATCH (p:Person)-[r:HAS_DOCUMENT]->(d:Document)
            WHERE p.source_doc_id STARTS WITH 'EIS'
            RETURN count(r) as rel_count
        """)
        rel_count = result.single()["rel_count"]
        
        print(f"✅ Found {rel_count} HAS_DOCUMENT relationships")
    
    driver.close()


def check_relationships():
    """Verify critical relationships exist"""
    print("\\n=== Relationship Verification ===\\n")
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session() as session:
        # Court -> Person
        result = session.run("""
            MATCH (c:CourtDecision)-[r:INVOLVES]->(p:Person)
            RETURN count(r) as rel_count
        """)
        count = result.single()["rel_count"]
        print(f"CourtDecision -> Person (INVOLVES): {count}")
        
        # Request -> Person
        result = session.run("""
            MATCH (req:Request)-[r:SEARCHED]->(p:Person)
            RETURN count(r) as rel_count
        """)
        count = result.single()["rel_count"]
        print(f"Request -> Person (SEARCHED): {count}")
        
        # Person -> Income
        result = session.run("""
            MATCH (p:Person)-[r:HAS_INCOME]->(i:IncomeRecord)
            RETURN count(r) as rel_count
        """)
        count = result.single()["rel_count"]
        print(f"Person -> IncomeRecord (HAS_INCOME): {count}")
    
    driver.close()


def check_identity():
    """Analyze identity key coverage"""
    print("\\n=== Identity Key Coverage ===\\n")
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session() as session:
        # DOCSCOPED vs global IDs
        result = session.run("""
            MATCH (n)
            RETURN 
                CASE WHEN n.id STARTS WITH 'DOCSCOPED' THEN 'DOCSCOPED' ELSE 'GLOBAL' END as id_type,
                count(*) as count
        """)
        
        for record in result:
            print(f"{record['id_type']}: {record['count']}")
        
        # Per entity
        result = session.run("""
            MATCH (n)
            RETURN 
                labels(n)[0] as label,
                CASE WHEN n.id STARTS WITH 'DOCSCOPED' THEN 'DOCSCOPED' ELSE 'GLOBAL' END as id_type,
                count(*) as count
            ORDER BY label, id_type
        """)
        
        print("\\nBy Entity:")
        for record in result:
            print(f"  {record['label']} ({record['id_type']}): {record['count']}")
    
    driver.close()


def check_ingestion_stats():
    """Show ingestion statistics"""
    print("\\n=== Ingestion Statistics ===\\n")
    
    client = MongoClient(MONGO_URI, tlsAllowInvalidCertificates=True)
    db = client[MONGO_DB]
    
    success_count = db["ingested_documents"].count_documents({})
    quarantine_count = db["quarantined_documents"].count_documents({})
    total = success_count + quarantine_count
    
    print(f"Total Files: {total}")
    print(f"Success: {success_count} ({100*success_count/total if total > 0 else 0:.1f}%)")
    print(f"Quarantined: {quarantine_count} ({100*quarantine_count/total if total > 0 else 0:.1f}%)")
    
    # Registry breakdown
    pipeline = [
        {"$group": {"_id": "$schema.registry_code", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    
    results = list(db["ingested_documents"].aggregate(pipeline))
    
    print("\\nBy Registry:")
    for r in results:
        print(f"  {r['_id']}: {r['count']}")
    
    client.close()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Ingestion Pipeline Verification Tool")
    parser.add_argument("--labels", action="store_true", help="Check Neo4j labels")
    parser.add_argument("--quarantine", action="store_true", help="Analyze quarantine")
    parser.add_argument("--eis", action="store_true", help="Verify EIS structure")
    parser.add_argument("--relationships", action="store_true", help="Check relationships")
    parser.add_argument("--identity", action="store_true", help="Analyze identity coverage")
    parser.add_argument("--stats", action="store_true", help="Show ingestion stats")
    parser.add_argument("--all", action="store_true", help="Run all checks")
    
    args = parser.parse_args()
    
    if args.all or not any([args.labels, args.quarantine, args.eis, args.relationships, args.identity, args.stats]):
        # Run all by default
        check_ingestion_stats()
        check_labels()
        check_quarantine()
        check_eis_structure()
        check_relationships()
        check_identity()
    else:
        if args.stats:
            check_ingestion_stats()
        if args.labels:
            check_labels()
        if args.quarantine:
            check_quarantine()
        if args.eis:
            check_eis_structure()
        if args.relationships:
            check_relationships()
        if args.identity:
            check_identity()


if __name__ == "__main__":
    main()
