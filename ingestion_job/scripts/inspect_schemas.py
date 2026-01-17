import os
import sys
from pathlib import Path
from pymongo import MongoClient
from dotenv import load_dotenv
import json

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
load_dotenv(BASE_DIR / ".env")

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB", "lapathon-nprd")

def inspect_schemas():
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db["register_schemas"]
    
    schemas = list(collection.find({}))
    print(f"Total Registers: {len(schemas)}")
    
    for s in schemas:
        code = s.get("registry_code")
        print(f"\nRegistry: {code}")
        for v in s.get("variants", []):
            vid = v.get("variant_id")
            pred = v.get("match_predicate")
            print(f"  Variant: {vid}")
            print(f"    Predicate: {pred}")

if __name__ == "__main__":
    inspect_schemas()
