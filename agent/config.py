from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


LANGSMITH_API_KEY_DEFAULT = os.getenv("LANGSMITH_API_KEY", "")
LANGSMITH_TRACING_DEFAULT = os.getenv("LANGSMITH_TRACING", "true")


def configure_langsmith_env(
    api_key: Optional[str] = None,
    tracing: Optional[str] = None,
) -> None:
    """
    Ensure LangSmith tracing environment variables are present with sensible defaults.
    """
    os.environ.setdefault("LANGSMITH_API_KEY", api_key or LANGSMITH_API_KEY_DEFAULT)
    os.environ.setdefault("LANGSMITH_TRACING", tracing or LANGSMITH_TRACING_DEFAULT)


@dataclass(frozen=True)
class AgentConfig:
    model_name: str
    base_url: str
    lapa_api_key: str
    temperature: float = 0.0
    
    openai_model_name: Optional[str] = None
    openai_api_key: Optional[str] = None

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    neo4j_database: Optional[str] = None

    allow_write_queries: bool = False

    @classmethod
    def from_env(cls) -> "AgentConfig":
        """
        Build the agent configuration from environment variables so the service can be
        configured without changing code.
        """
        return cls(
            model_name=os.getenv("MODEL_NAME", "lapa-function-calling"),
            base_url=os.getenv("BASE_URL", ""),
            lapa_api_key=os.getenv("API_KEY", ""),
            temperature=float(os.getenv("MODEL_TEMPERATURE", "0") or 0),
            openai_model_name=os.getenv("OPENAI_MODEL_NAME") or None,
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
            neo4j_password=os.getenv("NEO4J_PASSWORD", "password"),
            neo4j_database=os.getenv("NEO4J_DATABASE") or None,
            allow_write_queries=os.getenv("ALLOW_WRITE_QUERIES", "").lower()
            in {"1", "true", "yes"},
        )
