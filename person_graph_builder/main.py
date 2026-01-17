import os
import argparse
from .pipeline import Pipeline

def get_xml_files(base_dir):
    files = []
    for root, _, filenames in os.walk(base_dir):
        for f in filenames:
            if f.lower().endswith(".xml"):
                files.append(os.path.join(root, f))
    return files

def main():
    parser = argparse.ArgumentParser(description="Graph Builder Agent (Dynamic)")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--run-id", required=True, help="Unique Run ID for output isolation")
    parser.add_argument("--store-logs", action="store_true", help="Save LLM request/response logs")
    parser.add_argument("--clear-logs-dir", action="store_true", help="Clear logs directory before running")
    parser.add_argument("--clear-output-dir", action="store_true", help="Clear output directory before running")
    args = parser.parse_args()
    
    # Update Config
    # Config.DOCUMENTS_DIR = args.data_dir # Actually pipeline takes file list or uses Config? 
    # Main gets files using args.data_dir.
    
    # Set runtime config
    from .config import Config
    Config.STORE_LOGS = args.store_logs
    
    # We can handle clearing in Pipeline init or here. Pipeline seems appropriate as it owns the dirs.
    # Pass flags or let Pipeline check Config? 
    # Let's augment Pipeline to take these as init args or just rely on Config if we added flags there.
    # But Config is class properties. Let's just pass them to Pipeline init or use Config.
    
    # Since Config is static class mostly used as global state here:
    pipeline = Pipeline(
        run_id=args.run_id,
        clear_logs=args.clear_logs_dir,
        clear_output=args.clear_output_dir
    )
    
    # Gather files
    files = get_xml_files(args.data_dir)
    
    # Run Pipeline
    pipeline.run(files)

if __name__ == "__main__":
    main()
