"""POST /chat: typed questions from Flutter."""

from fastapi import APIRouter, Depends

from app.dependencies import get_answer_service, get_session_service
from app.models.chat_models import ChatRequest, ChatResponse
from app.services.answer_service import AnswerService
from app.services.session_service import SessionService

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    service: SessionService = Depends(get_session_service),
    answers: AnswerService = Depends(get_answer_service),
) -> ChatResponse:
    # 1. Find the session (checking its language), or start a new one.
    if request.session_id:
        session = service.touch(request.session_id, request.language)
    else:
        session = service.create(language=request.language)

    # 2. Read history BEFORE adding the new question, so it holds only earlier turns.
    history = service.recent_history(session.session_id)
    user_msg = service.add_message(session.session_id, "user", request.message, "text")

    # 3. Answer from the knowledge base with Gemini (or a placeholder if no Gemini key is set).
    #    If this fails, the error reaches Flutter and the question stays in the history without an answer.
    result = answers.answer(request.message, request.language, history)

    assistant_msg = service.add_message(
        session.session_id,
        "assistant",
        result.answer,
        "text",
        status=result.status,
        citations=result.citations,
        spoken_summary=result.spoken_summary,
    )

    return ChatResponse(
        session_id=session.session_id,
        answer=result.answer,
        status=result.status,
        citations=result.citations,
        spoken_summary=result.spoken_summary,
        user_message_seq=user_msg.seq,
        assistant_message_seq=assistant_msg.seq,
        placeholder=result.placeholder,
    )
