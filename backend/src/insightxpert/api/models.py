from __future__ import annotations

import time
from typing import Literal

from pydantic import BaseModel, Field, field_validator


_LEGACY_MODE_MAP = {
    "auto": "agentic",
    "statistician": "agentic",
    "advanced": "agentic",
    "analyst": "basic",
}


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    agent_mode: Literal["basic", "agentic", "deep"] = "agentic"
    skip_clarification: bool = False

    @field_validator("agent_mode", mode="before")
    @classmethod
    def _map_legacy_modes(cls, v: str) -> str:
        return _LEGACY_MODE_MAP.get(v, v)


class ChatChunk(BaseModel):
    type: str  # "status", "sql", "tool_call", "tool_result", "answer", "error"
    data: dict | None = None
    content: str | None = None
    sql: str | None = None
    tool_name: str | None = None
    args: dict | None = None
    conversation_id: str = ""
    timestamp: float = Field(default_factory=time.time)


class TrainRequest(BaseModel):
    type: str  # "qa_pair", "ddl", "documentation"
    content: str
    metadata: dict = Field(default_factory=dict)


class TrainResponse(BaseModel):
    status: str = "ok"
    id: str = ""


class RagDeleteResponse(BaseModel):
    status: str = "ok"
    deleted: dict[str, int] = {}


class SchemaResponse(BaseModel):
    ddl: str
    tables: list[str]


class ProviderModels(BaseModel):
    provider: str
    models: list[str]


class ConfigResponse(BaseModel):
    current_provider: str
    current_model: str
    providers: list[ProviderModels]


class SwitchModelRequest(BaseModel):
    provider: str
    model: str


class SwitchModelResponse(BaseModel):
    provider: str
    model: str


class SqlExecuteRequest(BaseModel):
    sql: str


class SqlExecuteResponse(BaseModel):
    columns: list[str]
    rows: list[dict]
    row_count: int
    execution_time_ms: float


# --- Auth models ---------------------------------------------------------


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    is_admin: bool = False
    token: str | None = None


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    chunks: list[dict] | None = None
    feedback: bool | None = None
    feedback_comment: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    generation_time_ms: int | None = None
    created_at: str


class ConversationSummary(BaseModel):
    id: str
    title: str
    is_starred: bool = False
    created_at: str
    updated_at: str
    last_message: str | None = None


class ConversationDetail(BaseModel):
    id: str
    title: str
    is_starred: bool = False
    messages: list[MessageResponse]
    created_at: str
    updated_at: str


class RenameRequest(BaseModel):
    title: str


class SearchMatchMessage(BaseModel):
    role: str
    snippet: str
    created_at: str


class SearchResultItem(BaseModel):
    id: str
    title: str
    updated_at: str
    title_match: bool = False
    matching_messages: list[SearchMatchMessage] = []


class FeedbackRequest(BaseModel):
    message_id: str
    feedback: bool | None  # True = thumbs up, False = thumbs down, None = clear
    comment: str | None = None


# --- Ollama models -------------------------------------------------------


class OllamaPullRequest(BaseModel):
    model: str = Field(description="Model name to pull, e.g. 'ministral:3b' or 'llama3.2:1b'")


class OllamaModelInfo(BaseModel):
    model: str
    size_mb: float | None = None
    parameter_size: str | None = None
    quantization: str | None = None
    family: str | None = None


class OllamaModelsResponse(BaseModel):
    models: list[OllamaModelInfo]


# --- Error / request models ------------------------------------------------


class ErrorResponse(BaseModel):
    error: str
    detail: str
    status_code: int


class StarRequest(BaseModel):
    starred: bool = True


class ChatAnswerResponse(BaseModel):
    answer: str
    conversation_id: str
    sql: list[str] = []
