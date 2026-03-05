from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


# --- User-scoped database connection schemas ---


class CreateUserDatabaseConnection(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    connection_string: str = Field(..., min_length=1)

    @field_validator("connection_string")
    @classmethod
    def validate_connection_string(cls, v: str) -> str:
        if not v.startswith(("postgresql://", "postgres://")):
            raise ValueError("connection_string must start with postgresql:// or postgres://")
        return v


class UpdateUserDatabaseConnection(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    connection_string: Optional[str] = Field(None, min_length=1)
    is_active: Optional[bool] = None

    @field_validator("connection_string")
    @classmethod
    def validate_connection_string(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.startswith(("postgresql://", "postgres://")):
            raise ValueError("connection_string must start with postgresql:// or postgres://")
        return v


class UserDatabaseConnectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    username: Optional[str] = None
    is_active: bool
    is_verified: bool
    last_verified_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class SetActiveRequest(BaseModel):
    active: bool
