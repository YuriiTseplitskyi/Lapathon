from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class AgentConfig:
    
    # Common settings
    agent_type: str = "openai"
    temperature: float = 0.0
    
    # LAPA settings
    lapa_model_name: str = "lapa-function-calling"
    lapa_api_key: Optional[str] = None
    base_url: Optional[str] = None

    # OpenAI settings
    openai_model_name: Optional[str] = None
    openai_api_key: Optional[str] = None

    # Neo4j settings
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    neo4j_database: Optional[str] = None
    allow_write_queries: bool = False
    
    # LangSmith settings
    langsmith_api_key: Optional[str] = None
    langsmith_tracing: Optional[str] = None

    @classmethod
    def from_env(cls) -> "AgentConfig":
        """
        Build the agent configuration from environment variables so the service can be
        configured without changing code.
        """

        config = cls(

            # common settings
            agent_type=os.getenv("AGENT_TYPE", "lapa"),
            temperature=float(os.getenv("MODEL_TEMPERATURE", "0")),

            # lapa settings
            lapa_model_name=os.getenv("MODEL_NAME", "lapa-function-calling"),
            lapa_api_key=os.getenv("LAPA_API_KEY", None),
            base_url=os.getenv("BASE_URL", None),

            # openai settings
            openai_model_name=os.getenv("OPENAI_MODEL_NAME", "gpt-5.1"),
            openai_api_key=os.getenv("OPENAI_API_KEY", None),

            # neo4j settings
            neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
            neo4j_password=os.getenv("NEO4J_PASSWORD", "password"),
            neo4j_database=os.getenv("NEO4J_DATABASE", "neo4j"),
            allow_write_queries=os.getenv("ALLOW_WRITE_QUERIES", "false").lower() in ("1", "true", "yes", "on"),

            # langsmith settings
            langsmith_api_key=os.getenv("LANGSMITH_API_KEY", None),
            langsmith_tracing=os.getenv("LANGSMITH_TRACING", "true"),

        )
        config.configure_langsmith_env()
        return config

    def configure_langsmith_env(self) -> None:
        """
        Set LangSmith environment variables from the config values.
        """
        if self.langsmith_api_key:
            os.environ["LANGSMITH_API_KEY"] = self.langsmith_api_key
        if self.langsmith_tracing:
            os.environ["LANGSMITH_TRACING"] = self.langsmith_tracing
