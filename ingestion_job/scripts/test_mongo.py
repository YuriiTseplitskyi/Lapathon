
import os
import pymongo
from dotenv import load_dotenv
from pathlib import Path
import logging

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_conn():
    uri = os.getenv("MONGO_URI")
    db_name = os.getenv("MONGO_DB")
    logger.info(f"Testing connection to DB: {db_name}")
    # logger.info(f"URI: {uri}") # Don't print secrets

    try:
        client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        logger.info("Ping successful!")
        
        db = client[db_name]
        logger.info(f"Collections: {db.list_collection_names()}")
    except Exception as e:
        logger.error(f"Connection failed: {e}")

if __name__ == "__main__":
    test_conn()
