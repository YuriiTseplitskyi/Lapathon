from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # App Config
    APP_NAME: str = "Corruption Profile Creator"
    VERSION: str = "1.0.0"
    
    # Neo4j Config
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"

    # Report Config
    FONT_FILENAME: str = "DejaVuSans.ttf"

    class Config:
        env_file = ".env"

settings = Settings()