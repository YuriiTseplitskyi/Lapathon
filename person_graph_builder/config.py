import os

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

# Load .env file explicitly
_base_dir = os.path.dirname(os.path.abspath(__file__))
if load_dotenv:
    env_path = os.path.join(_base_dir, ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)

class Config:
    BASE_DIR = _base_dir
    DOCUMENTS_DIR = os.environ.get("DOCUMENTS_DIR", "data")
    SCHEMAS_DIR = os.environ.get("SCHEMAS_DIR", os.path.join(BASE_DIR, "schemas"))
    OUTPUT_DIR = os.environ.get("OUTPUT_DIR", os.path.join(BASE_DIR, "output"))
    LOGS_DIR = os.environ.get("LOGS_DIR", os.path.join(BASE_DIR, "logs"))
    STORE_LOGS = False
    
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    
    # Model Configurations
    MODEL_CONFIGS = {
        "extractor": {
            "model": "lapa-function-calling",
            "temperature": 0.0,
            "reasoning_effort": None,
            "base_url": "https://api.lapathoniia.top/" # Optional: Custom API URL (e.g. for local models)
        },
        "discovery": {
            "model": "gpt-5.2",
            "temperature": 0.2,
            "reasoning_effort": None,
            "base_url": None # Optional: Custom API URL (e.g. for local models)
        },
        "rule_generator": {
            "model": "gpt-5.2",
            "temperature": 0.2,
            "reasoning_effort": "medium",
            "base_url": None # Optional: Custom API URL (e.g. for local models)
        }
    }
    
    # DB
    NEO4J_URI = os.environ.get("NEO4J_URI", "")
    NEO4J_USERNAME = os.environ.get("NEO4J_USERNAME", "")
    NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")
    
    
    # Toggle Generic Mode
    STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "json") # json or neo4j
