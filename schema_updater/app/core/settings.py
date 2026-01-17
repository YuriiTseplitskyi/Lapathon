import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

current_file_path = Path(__file__).resolve()

PROJECT_ROOT = current_file_path.parent.parent.parent.parent

class Settings(BaseSettings):
    API_KEY: str
    BASE_URL: str = "http://146.59.127.106:4000"
    # MODEL_NAME: str = "lapa-function-calling"
    MODEL_NAME: str = "mamay"

    model_config = SettingsConfigDict(
        env_file=os.path.join(PROJECT_ROOT, ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()