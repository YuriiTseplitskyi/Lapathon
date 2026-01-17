#!/usr/bin/env python3
"""
Script to check for nodes with image references (photo_url or content_url) in Neo4j.
"""

import sys
from pathlib import Path

# Add project root to path
# scripts/check_images.py -> ingestion_job/scripts/check_images.py
# We want to add .../Lapathon to sys.path
# __file__ is .../Lapathon/ingestion_job/scripts/check_images.py
# parent -> scripts
# parent.parent -> ingestion_job
# parent.parent.parent -> Lapathon
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from neo4j import GraphDatabase
from ingestion_job.app.core.settings import Settings

from pymongo import MongoClient

def check_images():
    settings = Settings()
    
    # Neo4j Connection
    uri = settings.neo4j_uri
    user = settings.neo4j_user
    password = settings.neo4j_password
    
    # Mongo Connection
    mongo_client = MongoClient(settings.mongo_uri)
    db = mongo_client[settings.mongo_db]
    
    print(f"Connecting to Neo4j at {uri}...")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    query = """
    MATCH (n)
    WHERE n.photo_url IS NOT NULL OR n.content_url IS NOT NULL
    RETURN labels(n) as labels, n.id as id, n.photo_url as photo_url, n.content_url as content_url, n.source_doc_id as source_doc_id
    LIMIT 100
    """
    
    try:
        with driver.session(database=settings.neo4j_database) as session:
            result = session.run(query)
            records = list(result)
            
            print(f"Found {len(records)} nodes with images/content URLs:")
            for r in records:
                print("---")
                print(f"Labels: {r['labels']}")
                print(f"Node ID: {r['id']}")
                
                url = r['photo_url'] or r['content_url']
                print(f"URL: {url}")
                
                # Determine Doc ID
                doc_id = r.get('source_doc_id')
                
                # Fallback: Extract doc_id from minio URL
                # format: minio://bucket/doc_id_hash.ext
                # example: minio://person-photos/12821d11-6562-57de-bc6e-172aa1c7fda6_9701cefb.jpg
                if not doc_id and url and "minio://" in url:
                    try:
                        filename = url.split("/")[-1] # 12821d11..._hash.jpg
                        if "_" in filename:
                            possible_id = filename.split("_")[0]
                            # Simple UUID check length
                            if len(possible_id) == 36:
                                doc_id = possible_id
                    except:
                        pass
                
                print(f"Doc ID: {doc_id}")
                
                if doc_id:
                    # Query Mongo
                    doc = db.ingested_documents.find_one({"document_id": doc_id})
                    if doc:
                        print(f"Document Path: {doc.get('raw', {}).get('file_path')}")
                        print(f"Ingestion Status: {doc.get('ingestion_status')}")
                        if doc.get('canonical') and doc['canonical'].get('meta'):
                             print(f"Meta: {doc['canonical']['meta']}")
                    else:
                        print("Document not found in MongoDB")
                else:
                    print("Could not determine Document ID")

    except Exception as e:
        print(f"Error querying: {e}")
    finally:
        driver.close()

if __name__ == "__main__":
    check_images()
