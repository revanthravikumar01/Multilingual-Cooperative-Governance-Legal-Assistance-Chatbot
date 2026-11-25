"""Temporary, in-memory conversation sessions (Decisions 11, 12, 16 and 31).

- Each session has a random ID, a fixed language and a short message history.
- A session expires after `ttl_minutes` without a chat or voice request.
- Nothing is saved to disk: restarting the backend clears all sessions.
"""

import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

from app.errors import LanguageMismatch, SessionNotFound


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class StoredMessage:
    seq: int
    role: str  # "user" or "assistant"
    text: str
    source: str  # "text" or "voice"
    created_at: datetime
    status: str | None = None
    citations: list[dict] = field(default_factory=list)
    spoken_summary: str | None = None


@dataclass
class Session:
    session_id: str
    language: str
    kiosk_id: str | None
    created_at: datetime
    last_active: datetime
    messages: list[StoredMessage] = field(default_factory=list)
    next_seq: int = 1


class SessionService:
    def __init__(
        self,
        ttl_minutes: int = 30,
        max_messages: int = 40,
        clock: Callable[[], datetime] = _utc_now,
    ):
        self._ttl = timedelta(minutes=ttl_minutes)
        self._max_messages = max_messages
        self._clock = clock  # Tests pass a fake clock to check expiry.
        self._sessions: dict[str, Session] = {}
        self._kiosk_sessions: dict[str, str] = {}  # kiosk_id -> active session_id
        self._lock = threading.Lock()  # FastAPI may handle requests on several threads.

    # ---------- helpers ----------

    def expires_at(self, session: Session) -> datetime:
        return session.last_active + self._ttl

    def _is_expired(self, session: Session, now: datetime) -> bool:
        return now >= self.expires_at(session)

    def _remove(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session and session.kiosk_id and self._kiosk_sessions.get(session.kiosk_id) == session_id:
            del self._kiosk_sessions[session.kiosk_id]

    def _purge_expired(self, now: datetime) -> None:
        expired = [sid for sid, s in self._sessions.items() if self._is_expired(s, now)]
        for sid in expired:
            self._remove(sid)

    def _get_live(self, session_id: str) -> Session:
        now = self._clock()
        self._purge_expired(now)
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionNotFound()
        return session

    # ---------- public API ----------

    def create(self, language: str, kiosk_id: str | None = None) -> Session:
        with self._lock:
            now = self._clock()
            self._purge_expired(now)
            session = Session(
                session_id=secrets.token_hex(16),
                language=language,
                kiosk_id=kiosk_id,
                created_at=now,
                last_active=now,
            )
            self._sessions[session.session_id] = session
            if kiosk_id:
                # A kiosk has one active conversation; starting a new one replaces the old.
                old = self._kiosk_sessions.get(kiosk_id)
                if old:
                    self._remove(old)
                self._kiosk_sessions[kiosk_id] = session.session_id
            return session

    def get(self, session_id: str) -> Session:
        """Look up a session without refreshing its inactivity timer."""
        with self._lock:
            return self._get_live(session_id)

    def touch(self, session_id: str, language: str) -> Session:
        """Use a session for a new question: check language and refresh the timer."""
        with self._lock:
            session = self._get_live(session_id)
            if session.language != language:
                raise LanguageMismatch(session.language)
            session.last_active = self._clock()
            return session

    def end(self, session_id: str) -> None:
        with self._lock:
            self._remove(session_id)

    def get_for_kiosk(self, kiosk_id: str) -> Session:
        with self._lock:
            session_id = self._kiosk_sessions.get(kiosk_id)
            if session_id is None:
                raise SessionNotFound()
            return self._get_live(session_id)

    def add_message(self, session_id: str, role: str, text: str, source: str, **extra) -> StoredMessage:
        with self._lock:
            session = self._get_live(session_id)
            message = StoredMessage(
                seq=session.next_seq,
                role=role,
                text=text,
                source=source,
                created_at=self._clock(),
                **extra,
            )
            session.next_seq += 1
            session.messages.append(message)
            # Keep memory small: only the most recent messages are kept.
            if len(session.messages) > self._max_messages:
                session.messages = session.messages[-self._max_messages :]
            return message

    def messages_after(self, session_id: str, after_seq: int = 0) -> list[StoredMessage]:
        with self._lock:
            session = self._get_live(session_id)
            return [m for m in session.messages if m.seq > after_seq]

    def recent_history(self, session_id: str, limit: int = 10) -> list[StoredMessage]:
        """The last few messages, to give Gemini conversation context (Phase 3)."""
        with self._lock:
            session = self._get_live(session_id)
            return list(session.messages[-limit:])
