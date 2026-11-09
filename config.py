"""Environment-backed application configuration."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Local development reads .env; Compose injects the same settings into the agent.
load_dotenv()


@dataclass(frozen=True)
class Settings:
    # These defaults keep the Flask app usable outside Docker.
    neo4j_http_url: str = os.getenv(
        "NEO4J_HTTP_URL", "http://localhost:7474/db/neo4j/query/v2"
    )
    neo4j_user: str = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD", "password123")
    llm_provider: str = os.getenv("LLM_PROVIDER", "openai")
    llm_model: str = os.getenv(
        "LLM_MODEL",
        {"claude": "claude-haiku-5-5", "gemini": "gemini-3.1-flash-lite"}.get(
            os.getenv("LLM_PROVIDER", "openai"), "gpt-6-luna"
        ),
    )
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_base_url: str = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    data_dir: Path = Path(os.getenv("DATA_DIR", "./data"))

settings = Settings()
