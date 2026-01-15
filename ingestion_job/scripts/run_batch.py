
import os
import sys
import logging
from pathlib import Path
from typing import List

from dotenv import load_dotenv

# Ensure we can import from ingestion_job
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))

from ingestion_job.app.core.settings import Settings
from ingestion_job.app.services.pipeline import IngestionPipeline

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

def load_env():
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH)
        logger.info(f"Loaded .env from {ENV_PATH}")

def find_files(data_dir: Path) -> List[Path]:
    files = []
    # Only target answer.xml/json or request.xml/json as appropriate?
    # Based on find_by_name output earlier: `890-ТМ-Д/В-2025-1615-034-TR7/answer.xml`
    # The EDR schema I created expects Envelope...SubjectDetail2ExtResponse...
    # This looks like `answer.xml`. 
    # Let's process `answer.xml` and `answer.json` for now.
    
    for ext in ["**/*.xml", "**/*.json"]:
        for p in data_dir.glob(ext):
            if p.is_file():
                # Simple filter: check if filename contains "answer" to match my hypothesis, or just try all?
                # The prompt said "Input: Raw files from drive / S3 / FS."
                # "Input: Raw files" implies we should try to ingest what we find.
                # However, to avoid noise from random non-data files (like .DS_Store is ignored by glob), let's just ingest everything and let the pipeline quarantine what it doesn't understand.
                files.append(p)
    return files

def process_one_file(file_path_str: str, settings_dict: dict):
    # Re-init settings and pipeline in worker process
    # settings_dict comes from main process
    try:
        from ingestion_job.app.core.settings import Settings
        from ingestion_job.app.services.pipeline import IngestionPipeline
        
        s = Settings(**settings_dict)
        # Ensure fresh sinks
        p = IngestionPipeline(s)
        try:
            return p.ingest_file(file_path_str)
        finally:
            p.close()
    except Exception as e:
        import traceback
        return {"status": "error", "error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()}


def run_batch(data_dir_str: str):
    load_env()
    
    data_dir = Path(data_dir_str).resolve()
    if not data_dir.exists():
        logger.error(f"Data directory not found: {data_dir}")
        return

    settings = Settings(data_dir=data_dir)
    # Force mongo/neo4j backend for this test run as per request "TEst it on real loading in neoj4 and mongo db"
    settings.schema_backend = "mongo"
    settings.graph_sink = "neo4j"
    settings.log_backend = "mongo"
    
    pipeline = IngestionPipeline(settings)
    # Propagate run_id to settings so workers use the same ID
    settings.run_id = pipeline.run_id
    
    files = find_files(data_dir)
    logger.info(f"Found {len(files)} files to ingest in {data_dir}")
    
    success_count = 0
    fail_count = 0
    
    # Serial execution for debugging/safety on DB writes? 
    # User requested parallel.
    # We need to be careful with MongoDB/Neo4j connections in forked processes.
    # Best practice: Initialize Pipeline INSIDE the worker.
    
    settings_dict = settings.model_dump() if hasattr(settings, 'model_dump') else settings.dict()
    
    # Prepare args
    # Limit parallelism to avoid blowing up DB connection limits
    max_workers = 10 
    
    import concurrent.futures
    
    logger.info(f"Starting parallel ingestion with {max_workers} workers (Run ID: {pipeline.run_id})...")
    
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        # We need a helper function that can be picked. Local functions can't be pickled.
        # But we can import it if it's in the module.
        # Actually run_batch.py is a script. We should define `process_one_file` at top level.
        # But for replace_file_content... let's assume we can add it or use a trick.
        # The trick: we rewrite the whole file or huge chunk.
        
        # Mapping properties
        futures = {executor.submit(process_one_file, str(p), settings_dict): p for p in files}
        
        for future in concurrent.futures.as_completed(futures):
            fpath = futures[future]
            try:
                result = future.result()
                status = result.get("status")
                if status == "success":
                    success_count += 1
                    logger.info(f"[{success_count+fail_count}/{len(files)}] SUCCESS {fpath.name}")
                else:
                    fail_count += 1
                    err_msg = result.get("error") or result.get("reason")
                    logger.warning(f"[{success_count+fail_count}/{len(files)}] {status.upper()} {fpath.name}: {err_msg}")
                    if "traceback" in result:
                         logger.debug(f"Traceback for {fpath.name}:\n{result['traceback']}")
            except Exception as e:
                fail_count += 1
                logger.error(f"  -> EXCEPTION {fpath.name}: {e}")

    logger.info("Batch ingestion finished.")
    logger.info(f"Total: {len(files)}, Success: {success_count}, Failed/Quarantined: {fail_count}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="../data/nabu_data", help="Path to data directory")
    args = parser.parse_args()
    
    # Adjust default relative path to be correct relative to CWD when running
    # If running from ingestion_job: ../data/nabu_data is correct if nabu_data is in Lapathon/data/nabu_data
    # Wait, list_dir showed `Lapathon/data/nabu_data`.
    # And we act as if we are in `Lapathon/ingestion_job`.
    # So `../data/nabu_data` refers to `Lapathon/data/nabu_data`. That works.
    
    run_batch(args.data_dir)
