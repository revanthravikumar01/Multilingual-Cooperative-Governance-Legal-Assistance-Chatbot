from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from app.config import allowed_origins

load_dotenv()

app = FastAPI(title="CIVI API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    language: str = Field(default="en", min_length=2, max_length=10)


class ChatResponse(BaseModel):
    answer: str
    placeholder: bool = True


@app.get("/api/v1/health")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "civi-api",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/v1/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """Temporary text-chat endpoint; replace only its answer generation in later phases."""
    language_note = "Tamil" if request.language.lower().startswith("ta") else "English"
    return ChatResponse(
        answer=(
            f"[Temporary API response — {language_note}] CIVI received your question: "
            f'"{request.message}". RAG, Gemini, STT/TTS, and ESP32 integration are not enabled yet.'
        )
    )
