from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CreateExternalDatabase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    connection_type: str = Field(..., pattern="^(postgresql|mysql)$")
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(..., ge=1, le=65535)
    database: str = Field(..., min_length=1, max_length=255)
    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1)


class UpdateExternalDatabase(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    connection_type: Optional[str] = Field(None, pattern="^(postgresql|mysql)$")
    host: Optional[str] = Field(None, min_length=1, max_length=255)
    port: Optional[int] = Field(None, ge=1, le=65535)
    database: Optional[str] = Field(None, min_length=1, max_length=255)
    username: Optional[str] = Field(None, min_length=1, max_length=255)
    password: Optional[str] = Field(None, min_length=1)
    is_active: Optional[bool] = None


class ExternalDatabaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    connection_type: str
    host: str
    port: int
    database: str
    username: str
    is_active: bool
    is_verified: bool
    last_verified_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class TestConnectionResponse(BaseModel):
    success: bool
    message: str
    table_count: Optional[int] = None
