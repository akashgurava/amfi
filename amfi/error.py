from collections.abc import Sequence
from typing import Any


class AppError(Exception):
    """Base exception for the application."""

    pass


class AppConfigError(AppError):
    """Exception raised when there's an error with the application configuration."""

    def __init__(self, name: str, expected: str, value: Any) -> None:
        super().__init__(
            f"INVALID_CONFIG. VAR: {name}. Expected: {expected}. Got: {value}"
        )


class HttpClientNotInitializedError(AppError):
    """Exception raised when the HTTP client is not initialized."""

    def __init__(self) -> None:
        super().__init__("HTTP client is not initialized")


class RequestExecutionError(RuntimeError):
    """Raised for HTTP/network errors where retry is allowed."""


class DatabaseError(AppError):
    """Raised for database errors."""


class DatabaseExecutionError(DatabaseError):
    def __init__(
        self,
        *,
        operation: str,
        sql: str,
        params: Sequence[Any] | None,
        cause: Exception,
    ) -> None:
        sql_preview = " ".join(sql.split())[:180]
        params_preview = repr(list(params))[:300] if params is not None else "[]"
        message = (
            f"Database operation failed during {operation}. "
            f"sql={sql_preview!r}, params={params_preview}, error={cause}"
        )
        super().__init__(message)


class DataValidationError(AppError):
    """Raised for data validation errors."""

    def __init__(self, sql: str, failed_rows: list[tuple[Any, ...]]) -> None:
        """Initialize the exception with SQL and failed rows."""
        failed = "\n".join(str(row) for row in failed_rows)
        message = f"Data validation failed. SQL: {sql}. Failed rows:\n{failed}"
        super().__init__(message)
