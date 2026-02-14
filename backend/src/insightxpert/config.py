from __future__ import annotations

from enum import Enum

from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(str, Enum):
    OLLAMA = "ollama"
    GEMINI = "gemini"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env.local", env_file_encoding="utf-8")

    # LLM
    llm_provider: LLMProvider = LLMProvider.GEMINI
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    ollama_model: str = "llama3.1"
    ollama_base_url: str = "http://localhost:11434"

    # Database
    database_url: str = "sqlite:///./insightxpert.db"

    # ChromaDB
    chroma_persist_dir: str = "./chroma_data"

    # Agent
    max_agent_iterations: int = 10
    sql_row_limit: int = 1000
    sql_timeout_seconds: int = 30

    # CORS
    cors_origins: str = "http://localhost:3000"

    # Auth
    secret_key: str = "CHANGE-ME-in-production-use-a-random-secret-key-here"
    access_token_expire_minutes: int = 1440

    # Logging
    log_level: str = "DEBUG"

    # Observability (Day 2+)
    obs_database_path: str = "./obs.db"

    @property
    def db_type(self) -> str:
        url = self.database_url.lower()
        if url.startswith("sqlite"):
            return "sqlite"
        if "postgresql" in url or "postgres" in url:
            return "postgresql"
        if "mysql" in url:
            return "mysql"
        return "unknown"
