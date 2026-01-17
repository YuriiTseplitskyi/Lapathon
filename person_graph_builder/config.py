import os

class Config:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DOCUMENTS_DIR = os.environ.get("DOCUMENTS_DIR", "data")
    SCHEMAS_DIR = os.environ.get("SCHEMAS_DIR", os.path.join(BASE_DIR, "schemas"))
    OUTPUT_DIR = os.environ.get("OUTPUT_DIR", os.path.join(BASE_DIR, "output"))
    LOGS_DIR = os.environ.get("LOGS_DIR", os.path.join(BASE_DIR, "logs"))
    STORE_LOGS = False
    
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    
    # Model Configurations
    MODEL_CONFIGS = {
        "extractor": {
            "model": "gpt-4.1",
            "temperature": 0.0,
            "reasoning_effort": None 
        },
        "discovery": {
            "model": "gpt-5.2",
            "temperature": 0.2,
            "reasoning_effort": None
        },
        "rule_generator": {
            "model": "gpt-5.2",
            "temperature": 0.2,
            "reasoning_effort": "medium"
        }
    }
    
    # DB
    NEO4J_URI = os.environ.get("NEO4J_URI", "")
    NEO4J_USERNAME = os.environ.get("NEO4J_USERNAME", "")
    NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")
    
    
    # Toggle Generic Mode
    STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "json") # json or neo4j
