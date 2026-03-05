from __future__ import annotations

import logging
from enum import Enum

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_logger = logging.getLogger("insightxpert.config")


class LLMProvider(str, Enum):
    OLLAMA = "ollama"
    GEMINI = "gemini"
    VERTEX_AI = "vertex_ai"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env.local", env_file_encoding="utf-8", extra="ignore")

    # LLM
    llm_provider: LLMProvider = LLMProvider.GEMINI
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    ollama_model: str = "llama3.1"
    ollama_base_url: str = "http://localhost:11434"

    # Vertex AI (for Model Garden models like GLM-5)
    gcp_project_id: str = ""
    vertex_ai_region: str = "global"
    vertex_ai_model: str = "zai-org/glm-5-maas"

    # PostgreSQL (primary runtime DB)
    database_url: str = "postgresql://insightxpert:insightxpert@localhost:5432/insightxpert"

    @field_validator("database_url", mode="before")
    @classmethod
    def _default_database_url(cls, v: str) -> str:
        """Treat empty DATABASE_URL env var as unset (use default)."""
        return v if v else "postgresql://insightxpert:insightxpert@localhost:5432/insightxpert"

    # ChromaDB
    chroma_persist_dir: str = "./chroma_data"

    # Agent
    max_agent_iterations: int = Field(default=25, gt=0)
    max_quant_analyst_iterations: int = Field(default=15, gt=0)
    max_orchestrator_tasks: int = Field(default=10, gt=0)
    python_exec_timeout_seconds: int = Field(default=10, gt=0)
    sql_row_limit: int = Field(default=10000, gt=0)
    sql_timeout_seconds: int = Field(default=30, gt=0)

    # CORS
    cors_origins: str = "http://localhost:3000,https://insightxpert.vercel.app,https://insightxpert-ai.web.app"

    # Auth
    secret_key: str = "CHANGE-ME-in-production-use-a-random-secret-key-here"
    access_token_expire_minutes: int = Field(default=1440, gt=0)
    admin_seed_email: str = "admin@insightxpert.ai"
    admin_seed_password: str = "admin123"

    # Startup / runtime tuning
    rag_bootstrap_timeout_seconds: int = Field(default=120, gt=0)
    conversation_ttl_seconds: int = Field(default=7200, gt=0)

    # Stats context injection
    enable_stats_context: bool = True  # Set ENABLE_STATS_CONTEXT=false to disable

    # Encryption (required for external database connections feature)
    encryption_key: str = ""

    # Voice / Speech-to-text (Deepgram)
    deepgram_api_key: str = ""

    # Logging
    log_level: str = "INFO"

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, v: str) -> str:
        v = v.upper()
        if v not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"log_level must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL; got {v!r}")
        return v

    @model_validator(mode="after")
    def _check_runtime_config(self) -> Settings:
        if "CHANGE-ME" in self.secret_key or len(self.secret_key) < 32:
            _logger.warning("secret_key is insecure — set a random string of 32+ characters for production")
        if self.admin_seed_password in {"changeme", "admin123", ""} or len(self.admin_seed_password) < 8:
            _logger.warning("admin_seed_password is insecure — set ADMIN_SEED_PASSWORD to a strong password for production")
        if self.llm_provider == LLMProvider.GEMINI and not self.gemini_api_key:
            _logger.warning("llm_provider is 'gemini' but gemini_api_key is empty")
        if self.llm_provider == LLMProvider.VERTEX_AI and not self.gcp_project_id:
            _logger.warning("llm_provider is 'vertex_ai' but gcp_project_id is empty — set GCP_PROJECT_ID")
        return self
