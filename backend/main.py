"""CIVI backend entry point.

Run from the backend folder:  uvicorn main:app --host 0.0.0.0 --port 8000 --reload
This file only builds the app; the endpoints live in app/api/.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, documents, hardware, health, sessions, voice
from app.config import settings
from app.errors import register_error_handlers

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    app = FastAPI(title="CIVI API", version="0.2.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)

    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(sessions.router, prefix=API_PREFIX)
    app.include_router(sessions.kiosk_router, prefix=API_PREFIX)
    app.include_router(chat.router, prefix=API_PREFIX)
    app.include_router(documents.router, prefix=API_PREFIX)
    app.include_router(voice.router, prefix=API_PREFIX)
    app.include_router(hardware.router, prefix=API_PREFIX)
    return app


app = create_app()
