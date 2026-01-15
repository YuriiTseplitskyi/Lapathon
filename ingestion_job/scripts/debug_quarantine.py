from pymongo import MongoClient
import os
from dotenv import load_dotenv
import json

load_dotenv()
mongo_uri = os.getenv("MONGO_URI")
mongo_db = os.getenv("MONGO_DB")

client = MongoClient(mongo_uri)
db = client[mongo_db]

print("\n--- Quarantined 'answer' Files (First 5) ---")
# Filter for files containing 'answer' in path
query = {"file_path": {"$regex": "answer"}}
quarantined = list(db.quarantined_documents.find(query).limit(5))
print(f"Total Quarantined 'answer' files: {db.quarantined_documents.count_documents(query)}")

for q in quarantined:
    print(f"\nFile: {q.get('file_path')}")
    print(f"Error: {q.get('error_message')}")
    print("Debug Info (Candidate Scores):")
    # 'details' usually contains 'candidate_scores' if I populated it in pipeline
    # The pipeline saves debug details into 'extra' field of QuarantinedDocument
    debug_info = q.get('extra', {})
    print(json.dumps(debug_info, indent=2, default=str)) 
