"""Session endpoints: start, look up, end, and poll messages."""

from fastapi import APIRouter, Depends, Query, Response

from app.dependencies import get_session_service
from app.models.session_models import (
    CreateSessionRequest,
    MessageOut,
    MessagesResponse,
    SessionResponse,
)
from app.services.session_service import Session, SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])


def to_session_response(session: Session, service: SessionService) -> SessionResponse:
    return SessionResponse(
        session_id=session.session_id,
        language=session.language,
        kiosk_id=session.kiosk_id,
        created_at=session.created_at,
        expires_at=service.expires_at(session),
    )


@router.post("", status_code=201, response_model=SessionResponse)
def create_session(
    request: CreateSessionRequest,
    service: SessionService = Depends(get_session_service),
) -> SessionResponse:
    session = service.create(language=request.language, kiosk_id=request.kiosk_id)
    return to_session_response(session, service)


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(session_id: str, service: SessionService = Depends(get_session_service)) -> SessionResponse:
    return to_session_response(service.get(session_id), service)


@router.delete("/{session_id}", status_code=204)
def end_session(session_id: str, service: SessionService = Depends(get_session_service)) -> Response:
    service.end(session_id)
    return Response(status_code=204)


@router.get("/{session_id}/messages", response_model=MessagesResponse)
def list_messages(
    session_id: str,
    after: int = Query(default=0, ge=0, description="Return only messages with seq greater than this"),
    service: SessionService = Depends(get_session_service),
) -> MessagesResponse:
    messages = service.messages_after(session_id, after)
    return MessagesResponse(
        session_id=session_id,
        messages=[
            MessageOut(
                seq=m.seq,
                role=m.role,
                text=m.text,
                source=m.source,
                status=m.status,
                citations=m.citations,
                spoken_summary=m.spoken_summary,
                created_at=m.created_at,
            )
            for m in messages
        ],
    )


kiosk_router = APIRouter(prefix="/kiosks", tags=["sessions"])


@kiosk_router.get("/{kiosk_id}/session", response_model=SessionResponse)
def get_kiosk_session(kiosk_id: str, service: SessionService = Depends(get_session_service)) -> SessionResponse:
    """The kiosk's active conversation (started by the Flutter app with this kiosk_id).

    The ESP32 calls this to know which session to send voice questions to. 404 if there is none.
    Does not refresh the session timer.
    """
    return to_session_response(service.get_for_kiosk(kiosk_id), service)
