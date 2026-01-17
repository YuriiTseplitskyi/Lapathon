import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

current_file_path = Path(__file__).resolve()

PROJECT_ROOT = current_file_path.parent.parent.parent.parent

class Settings(BaseSettings):
    API_KEY: str
    BASE_URL: str
    MODEL_NAME: str

    model_config = SettingsConfigDict(
        env_file=os.path.join(PROJECT_ROOT, ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    MONGO_URI: str
    DATABASE_NAME: str
    
    COLLECTION_CHECKPOINTS: str
    
    COLLECTION_DOCUMENTS: str

    COLLECTION_ENTITIES: str
    
    CANONICAL_FIELD: str
    REGISTRY_CODE_FIELD: str

settings = Settings()