#!/usr/bin/env python3
"""
Consolidated Debug Tool for Ingestion Pipeline
Replaces: debug_ingest_single.py, debug_canonical.py, debug_match.py, 
          debug_predicate.py, debug_quarantine.py, find_doc_path.py
"""

import os
import sys
import json
import argparse
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
load_dotenv(BASE_DIR / ".env")

from ingestion_job.app.core.settings import Settings
from ingestion_job.app.services.pipeline import IngestionPipeline
from ingestion_job.app.services.schema.utils import eval_predicate

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")


def debug_file(file_path: str):
    """Debug full ingestion for a single file"""
    print(f"\\n=== Debugging File: {file_path} ===\\n")
    
    settings = Settings()
    pipeline = IngestionPipeline(settings)
    
    result = pipeline.ingest_file(file_path)
    
    print(f"Status: {result['status']}")
    if result['status'] != 'success':
        print(f"Reason: {result.get('reason')}")
        print(f"Error: {result.get('error')}")
    else:
        print(f"Document ID: {result.get('document_id')}")
        print(f"Registry: {result.get('registry_code')}")
        print(f"Variant: {result.get('variant_id')}")


def canonicalize_file(file_path: str):
    """Show canonical JSON output for a file"""
    print(f"\\n=== Canonical Output: {file_path} ===\\n")
    
    settings = Settings()
    pipeline = IngestionPipeline(settings)
    
    # Read raw
    with open(file_path, 'rb') as f:
        raw_bytes = f.read()
    
    from ingestion_job.app.models.core import RawDocument
    raw = RawDocument(
        file_path=file_path,
        content_type="application/xml" if file_path.endswith(".xml") else "application/json",
        raw_bytes=raw_bytes
    )
    
    # Canonicalize
    canonical = pipeline.canonicalizer.canonicalize(raw)
    
    print(json.dumps(canonical.data, ensure_ascii=False, indent=2))


def test_predicate(predicate_json: str, file_path: str):
    """Test a predicate against a file"""
    print(f"\\n=== Testing Predicate ===\\n")
    
    # Load predicate
    predicate = json.loads(predicate_json)
    
    # Canonicalize file
    settings = Settings()
    pipeline = IngestionPipeline(settings)
    
    with open(file_path, 'rb') as f:
        raw_bytes = f.read()
    
    from ingestion_job.app.models.core import RawDocument
    raw = RawDocument(
        file_path=file_path,
        content_type="application/xml" if file_path.endswith(".xml") else "application/json",
        raw_bytes=raw_bytes
    )
    
    canonical = pipeline.canonicalizer.canonicalize(raw)
    doc_data = {"meta": canonical.meta, "data": canonical.data}
    
    # Evaluate
    matched, score, reasons = eval_predicate(doc_data, predicate)
    
    print(f"Matched: {matched}")
    print(f"Score: {score}")
    print(f"Reasons: {reasons}")


def find_document(doc_id: str):
    """Find file path for a document ID"""
    client = MongoClient(MONGO_URI, tlsAllowInvalidCertificates=True)
    db = client[MONGO_DB]
    
    # Check ingested
    doc = db["ingested_documents"].find_one({"document_id": doc_id})
    if doc:
        print(f"\\nDocument ID: {doc_id}")
        print(f"File Path: {doc['raw']['file_path']}")
        print(f"Registry: {doc['schema']['registry_code']}")
        print(f"Variant: {doc['schema']['variant_id']}")
        print(f"Ingested: {doc['metadata']['ingested_at']}")
        return
    
    # Check quarantine
    doc = db["quarantined_documents"].find_one({"document_id": doc_id})
    if doc:
        print(f"\\nDocument ID: {doc_id}")
        print(f"File Path: {doc['file_path']}")
        print(f"Status: QUARANTINED")
        print(f"Reason: {doc['reason']}")
        print(f"Error: {doc.get('error_message')}")
        return
    
    print(f"Document ID {doc_id} not found in DB")


def list_quarantine():
    """List all quarantined documents"""
    client = MongoClient(MONGO_URI, tlsAllowInvalidCertificates=True)
    db = client[MONGO_DB]
    
    docs = list(db["quarantined_documents"].find().limit(50))
    
    print(f"\\nTotal Quarantined: {db['quarantined_documents'].count_documents({})}\\n")
    
    for doc in docs:
        print(f"{doc['file_path']}")
        print(f"  Reason: {doc['reason']}")
        print(f"  Error: {doc.get('error_message', 'N/A')}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Ingestion Pipeline Debug Tool")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # debug-file
    p1 = subparsers.add_parser("debug-file", help="Debug full ingestion for a file")
    p1.add_argument("file_path", help="Path to file")
    
    # canonicalize
    p2 = subparsers.add_parser("canonicalize", help="Show canonical JSON output")
    p2.add_argument("file_path", help="Path to file")
    
    # test-predicate
    p3 = subparsers.add_parser("test-predicate", help="Test a predicate")
    p3.add_argument("predicate", help="JSON predicate string")
    p3.add_argument("file_path", help="Path to file")
    
    # find-doc
    p4 = subparsers.add_parser("find-doc", help="Find file for document ID")
    p4.add_argument("doc_id", help="Document ID")
    
    # list-quarantine
    p5 = subparsers.add_parser("list-quarantine", help="List quarantined documents")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    if args.command == "debug-file":
        debug_file(args.file_path)
    elif args.command == "canonicalize":
        canonicalize_file(args.file_path)
    elif args.command == "test-predicate":
        test_predicate(args.predicate, args.file_path)
    elif args.command == "find-doc":
        find_document(args.doc_id)
    elif args.command == "list-quarantine":
        list_quarantine()


if __name__ == "__main__":
    main()
