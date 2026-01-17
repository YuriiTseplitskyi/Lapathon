import os
import json
import argparse
from typing import Dict, Any

from .config import Config
from .storage.neo4j_store import Neo4jStore

def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r") as f:
        return json.load(f)

def run_import(clear: bool, run_id: str = None):
    config = Config()
    
    if run_id:
        # Check for resolved_graph first
        resolved_path = os.path.join(config.BASE_DIR, "outputs", run_id, "resolved_graph")
        if os.path.exists(resolved_path):
             config.OUTPUT_DIR = resolved_path
             print(f"Importing RESOLVED Graph from: {run_id} ({config.OUTPUT_DIR})")
        else:
             config.OUTPUT_DIR = os.path.join(config.BASE_DIR, "outputs", run_id, "output")
             print(f"Importing RAW Graph from: {run_id} ({config.OUTPUT_DIR})")
    
    # Initialize Neo4j Store
    try:
        store = Neo4jStore(config.NEO4J_URI, config.NEO4J_USERNAME, config.NEO4J_PASSWORD)
    except Exception as e:
        print(f"Failed to connect to Neo4j: {e}")
        return

    if clear:
        print("Clearing Neo4j database...")
        store.clear_database()

    # Load Index
    index_path = os.path.join(config.OUTPUT_DIR, "index.json")
    if not os.path.exists(index_path):
        print(f"Index file not found at {index_path}. Run extraction first.")
        return

    print(f"Loading index from {index_path}...")
    index = load_json(index_path)
    
    entities = index.get("entities", {})
    relationships = index.get("relationships", [])
    
    print(f"Found {len(entities)} entities and {len(relationships)} relationships.")

    # Import Entities
    print("Importing entities...")
    count = 0
    for uid, meta in entities.items():
        rel_path = meta.get("path") # relative or absolute?
        # json_store implementation used absolute path usually, or we should check
        
        # In json_store.py: file_path = os.path.join(label_dir, f"{node_id}.json")
        # index["entities"][node_id] = {"label": label, "path": file_path}
        # Assuming file_path was absolute or relative to CWD? 
        # Ideally it should be relative to output dir if we want portability, but let's assume it works as written.
        
        if not os.path.exists(rel_path):
             print(f"Warning: Entity file missing: {rel_path}")
             continue
             
        data = load_json(rel_path)
        label = data.get("_label")
        props = {k: v for k, v in data.items() if not k.startswith("_")}
        
        # Ensure ID present
        if "id" not in props:
             props["id"] = uid
             
        store.upsert_node(label, props)
        count += 1
        if count % 100 == 0:
            print(f"  Imported {count} entities...")
            
    print(f"Finished importing {count} entities.")

    # Import Relationships
    print("Importing relationships...")
    count = 0
    for rel in relationships:
        store.upsert_relationship(rel)
        count += 1
        if count % 100 == 0:
             print(f"  Imported {count} relationships...")
             
    print(f"Finished importing {count} relationships.")
    store.close()

def main():
    parser = argparse.ArgumentParser(description="Import JSON Graph to Neo4j")
    parser.add_argument("--clear", action="store_true", help="Clear Neo4j database before importing")
    parser.add_argument("--run-id", help="Import from specific Run ID")
    args = parser.parse_args()
    
    run_import(clear=args.clear, run_id=args.run_id)

if __name__ == "__main__":
    main()
