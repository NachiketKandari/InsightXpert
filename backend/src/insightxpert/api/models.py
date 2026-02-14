from __future__ import annotations

import time
from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


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


class UserResponse(BaseModel):
    id: str
    email: str


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    chunks: list[dict] | None = None
    created_at: str


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    last_message: str | None = None


class ConversationDetail(BaseModel):
    id: str
    title: str
    messages: list[MessageResponse]
    created_at: str
    updated_at: str


class RenameRequest(BaseModel):
    title: str


class FeedbackRequest(BaseModel):
    conversation_id: str
    message_id: str
    rating: Literal["up", "down"]
    comment: str = ""
