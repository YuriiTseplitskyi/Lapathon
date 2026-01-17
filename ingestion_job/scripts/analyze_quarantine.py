import os
import sys
from pathlib import Path
from pymongo import MongoClient
from dotenv import load_dotenv
import json

# Setup path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
load_dotenv(BASE_DIR / ".env")

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB", "lapathon-nprd") # fixed env var name from my findings

def analyze_quarantine():
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db["quarantined_documents"]
    
    count = collection.count_documents({})
    print(f"Total Quarantined Documents: {count}")

    grouped = {}
    
    docs = collection.find({})
    i = 0
    ans_count = 0
    for doc in docs:
        i += 1
        fpath = doc.get("file_path")
        
        if fpath and "answer.xml" in fpath:
             ans_count += 1
             if ans_count <= 3:
                  print(f"Debug Answer Path {ans_count}: {fpath}")
                  
        if not fpath:
             continue
        
        # Resolve path
        # Paths are relative to ../data/nabu_data
        data_dir = BASE_DIR.parent / "data" / "nabu_data"
        path_obj = data_dir / fpath
        
        content = ""
        try:
            with open(path_obj, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            # print(f"Error reading {path_obj}: {e}")
            pass

        if not content:
             content = doc.get("excerpt", "")
             
        fname = Path(fpath).name
        
        # Parse content if string likely JSON
        if isinstance(content, str) and (content.strip().startswith("{") or content.strip().startswith("[")):
            try:
                content = json.loads(content)
            except:
                pass

        # Detect type logic
        ctype = "Unknown"
        if isinstance(content, dict):
            data = content.get("data", {})
            if "Envelope" in data:
                 header = data["Envelope"].get("Header", {})
                 svc = header.get("service", {}) or header.get("Service", {})
                 code = svc.get('serviceCode') or svc.get('ServiceCode')
                 ctype = f"XML Service: {code}"
            elif "REQUESTID" in data:
                 ctype = "JSON Request (REQUESTID)"
            elif "entity" in data:
                 ctype = f"JSON Entity: {data['entity']}"
            elif "array" in data:
                 if len(data["array"]) > 0 and "courtId" in data["array"][0]:
                      ctype = "JSON Court Decision"
                 else:
                      ctype = "JSON Array (Unknown)"
            elif "root" in data and "CARS" in data["root"]:
                 ctype = "JSON MVS Cars"
            else:
                 keys = list(data.keys())
                 ctype = f"JSON Keys: {keys}"
        elif isinstance(content, str):
             if content.strip().startswith("<"):
                  if "InfoIncomeSourcesDRFO2Query" in content:
                      ctype = "XML String: DRFO Query"
                  elif "getProxyPersonsNameOrIDN" in content:
                      ctype = "XML String: Proxy Person"
                  elif "ArServiceAnswer" in content:
                      ctype = "XML String: DRACS ArService"
                  else:
                      ctype = f"XML String: {content[:80].replace(chr(10), ' ')}"
             else:
                  ctype = f"String/Raw: {content[:50]}"
        else:
             ctype = f"Unknown Type: {type(content)}"

        reason = doc.get("reason", "unknown")
        if "No matching schema variant" in reason:
             reason = "No matching schema variant"
        
        key = f"{fname} | {ctype} | {reason}"
        if key not in grouped:
            grouped[key] = {"count": 0, "sample": content}
        grouped[key]["count"] += 1
        
    print("\n--- Quarantine Analysis ---")
    for key, data in grouped.items():
        print(f"\nGroup: {key}")
        print(f"Count: {data['count']}")
        # print(f"Sample: {str(data['sample'])[:300]}")
    
    client.close()

if __name__ == "__main__":
    analyze_quarantine()
