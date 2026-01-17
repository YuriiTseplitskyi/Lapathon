import os
import shutil
from .config import Config
from .extractor import Extractor
from .schema_manager import SchemaManager
from .storage.json_store import JSONStore
from .storage.neo4j_store import Neo4jStore

class Pipeline:
    def __init__(self, run_id: str, clear_logs=False, clear_output=False):
        self.config = Config()
        
        # Setup Run Directories
        self.run_dir = os.path.join(self.config.BASE_DIR, "outputs", run_id)
        
        # Define paths for this specific run
        self.config.OUTPUT_DIR = os.path.join(self.run_dir, "output")
        self.config.LOGS_DIR = os.path.join(self.run_dir, "logs")
        self.config.SCHEMAS_DIR = os.path.join(self.run_dir, "schemas")  # Runtime schemas
        
        # Base schemas (Template)
        base_schemas_dir = os.path.join(self.config.BASE_DIR, "schemas")
        
        # Create directories
        os.makedirs(self.config.OUTPUT_DIR, exist_ok=True)
        os.makedirs(self.config.LOGS_DIR, exist_ok=True)
        os.makedirs(self.config.SCHEMAS_DIR, exist_ok=True)
        
        # Copy base schemas to runtime (if not exists, or overwrite? User implies clean start for new run_id)
        # We copy to ensure this run has its own evolving schema
        self._setup_schemas(base_schemas_dir, self.config.SCHEMAS_DIR)

        # Cleanup logic (Operating on the RUN directories now)
        if clear_output and os.path.exists(self.config.OUTPUT_DIR):
            print(f"Clearing output directory: {self.config.OUTPUT_DIR}")
            shutil.rmtree(self.config.OUTPUT_DIR)
            os.makedirs(self.config.OUTPUT_DIR, exist_ok=True)
        
        if clear_logs and os.path.exists(self.config.LOGS_DIR):
             print(f"Clearing logs directory: {self.config.LOGS_DIR}")
             shutil.rmtree(self.config.LOGS_DIR)
             os.makedirs(self.config.LOGS_DIR, exist_ok=True)

        self.extractor = Extractor(self.config)
        self.schema_manager = SchemaManager(self.config.SCHEMAS_DIR)
        
        if self.config.STORAGE_BACKEND == "json":
            self.store = JSONStore(self.config.OUTPUT_DIR)
        elif self.config.STORAGE_BACKEND == "neo4j":
            self.store = Neo4jStore(
                self.config.NEO4J_URI,
                self.config.NEO4J_USERNAME,
                self.config.NEO4J_PASSWORD
            )
        else:
            raise ValueError(f"Unknown backend: {self.config.STORAGE_BACKEND}")

    def _setup_schemas(self, src_dir, dst_dir):
        """Copies schema files from source to destination."""
        import json
        for fname in ["entity_types.json", "relationship_schemas.json", "doc_mappings.json"]:
            src = os.path.join(src_dir, fname)
            dst = os.path.join(dst_dir, fname)
            
            if os.path.exists(src):
                # Copy file
                shutil.copy2(src, dst)
            else:
                # Create empty if missing template
                if fname == "entity_types.json":
                    content = {"entity_types": []}
                elif fname == "relationship_schemas.json":
                    content = {"relationship_schemas": []}
                else:
                    content = {}
                
                with open(dst, "w") as f:
                    json.dump(content, f, indent=2)

    def run(self, files: list):
        print(f"Starting pipeline on {len(files)} files...")
        
        for i, fpath in enumerate(files):
            print(f"[{i+1}/{len(files)}] Processing {fpath}...")
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
                
                # Use current known types for context
                current_types = self.schema_manager.get_entity_types()
                
                # Extract
                fname = f"{i:03d}_{os.path.basename(fpath)}"
                result = self.extractor.extract(content, current_types, doc_name=fname)
                
                # Handle Schema Updates (Explicit)
                updates = result.get("schema_updates", [])
                for upd in updates:
                    kind = upd.get("type")
                    if kind == "ENTITY":
                        self.schema_manager.register_new_entity_type(upd.get("name"), upd.get("pk", ["id"]))
                    elif kind == "RELATIONSHIP":
                        self.schema_manager.register_new_relationship_type(upd.get("name"))

                # Upsert
                entities = result.get("entities", [])
                relationships = result.get("relationships", [])
                
                # Auto-register entity types from actual entities (fallback if LLM didn't report schema_updates)
                for ent in entities:
                    label = ent.get("label")
                    identifying_keys = ent.get("identifying_keys", ["id"])
                    if label:
                        self.schema_manager.register_new_entity_type(label, identifying_keys)
                
                for ent in entities:
                    # Sync top-level ID to properties to ensure Store uses the intended ID
                    if ent.get("id"):
                        ent["properties"]["id"] = ent["id"]
                        
                    self.store.upsert_node(ent.get("label"), ent.get("properties", {}))
                    
                for rel in relationships:
                    rel_type = rel.get("type")
                    if rel_type:
                        self.schema_manager.register_new_relationship_type(rel_type)
                    self.store.upsert_relationship(rel)
                    
            except Exception as e:
                print(f"Error processing {fpath}: {e}")
        
        self.store.close()
        print("Pipeline complete.")
