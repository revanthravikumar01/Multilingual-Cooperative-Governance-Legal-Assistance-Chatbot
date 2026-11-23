import os


def allowed_origins() -> list[str]:
    """Read development CORS origins without requiring a configuration package."""
    value = os.getenv("CIVI_ALLOWED_ORIGINS", "*")
    return [origin.strip() for origin in value.split(",") if origin.strip()]
