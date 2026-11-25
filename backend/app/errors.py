"""One error format for the whole API: {"error": {"code": ..., "message": ...}}.

See API_CONTRACT.md -> "Error format".
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """Raise this from any endpoint or service to send a clean error response."""

    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class SessionNotFound(ApiError):
    def __init__(self) -> None:
        super().__init__(404, "session_not_found", "Session not found or expired. Start a new session.")


class LanguageMismatch(ApiError):
    def __init__(self, session_language: str) -> None:
        super().__init__(
            409,
            "language_mismatch",
            f"This session uses language '{session_language}'. Start a new session to change language.",
        )


def _error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_error_body(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Turn FastAPI's detailed validation list into one readable sentence.
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(part) for part in first.get("loc", []) if part != "body")
        reason = first.get("msg", "Invalid request")
        message = f"{field}: {reason}" if field else reason
        return JSONResponse(status_code=400, content=_error_body("invalid_request", message))
