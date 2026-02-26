"""Custom exception hierarchy for InsightXpert."""

from __future__ import annotations


class InsightXpertError(Exception):
    """Base exception for all InsightXpert errors."""

    message: str
    status_code: int
    error_code: str

    def __init__(
        self,
        message: str = "An unexpected error occurred",
        status_code: int = 500,
        error_code: str = "INTERNAL_ERROR",
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message)


class DatabaseError(InsightXpertError):
    """Generic database error."""

    def __init__(self, message: str = "A database error occurred") -> None:
        super().__init__(message=message, status_code=503, error_code="DATABASE_ERROR")


class QuerySyntaxError(InsightXpertError):
    """SQL query has a syntax error or references invalid objects."""

    def __init__(self, message: str = "SQL query syntax error") -> None:
        super().__init__(message=message, status_code=400, error_code="QUERY_SYNTAX_ERROR")


class QueryTimeoutError(InsightXpertError):
    """SQL query exceeded the allowed execution time."""

    def __init__(self, message: str = "Query execution timed out") -> None:
        super().__init__(message=message, status_code=504, error_code="QUERY_TIMEOUT")


class DatabaseConnectionError(InsightXpertError):
    """Cannot connect to the database."""

    def __init__(self, message: str = "Database connection failed") -> None:
        super().__init__(
            message=message, status_code=503, error_code="DATABASE_CONNECTION_ERROR",
        )


class ValidationError(InsightXpertError):
    """Request validation error (business-level, not Pydantic)."""

    def __init__(self, message: str = "Validation error") -> None:
        super().__init__(message=message, status_code=400, error_code="VALIDATION_ERROR")


class NotFoundError(InsightXpertError):
    """Requested resource was not found."""

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message=message, status_code=404, error_code="NOT_FOUND")


class LLMError(InsightXpertError):
    """Error communicating with the LLM provider."""

    def __init__(self, message: str = "LLM service error") -> None:
        super().__init__(message=message, status_code=502, error_code="LLM_ERROR")


class ServiceUnavailableError(InsightXpertError):
    """A required service is temporarily unavailable."""

    def __init__(self, message: str = "Service unavailable") -> None:
        super().__init__(
            message=message, status_code=503, error_code="SERVICE_UNAVAILABLE",
        )
