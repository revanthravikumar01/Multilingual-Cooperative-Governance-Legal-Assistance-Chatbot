"""Kiosk button presses and ESP32 status, passed from the ESP32 to the Flutter app (Phase 7).

The ESP32 reports each button press (Decision 34: it talks to the backend directly). The Flutter app
polls GET /kiosks/{kiosk_id}/events?after=<seq> and reacts as if the matching key had been pressed.
Events are kept in memory per kiosk (the newest 100); nothing is stored on disk.
"""

import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

MAX_EVENTS_PER_KIOSK = 100


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class KioskEvent:
    seq: int
    button: str | None  # language | confirm | back | repeat | mic | accessibility
    status: str | None  # ESP32 audio state: recording | processing | speaking | idle
    created_at: datetime


class HardwareEventService:
    def __init__(self, clock: Callable[[], datetime] = _utc_now):
        self._clock = clock
        self._lock = threading.Lock()
        self._events: dict[str, deque[KioskEvent]] = {}
        self._next_seq: dict[str, int] = {}

    def add(self, kiosk_id: str, button: str | None = None, status: str | None = None) -> KioskEvent:
        with self._lock:
            seq = self._next_seq.get(kiosk_id, 1)
            self._next_seq[kiosk_id] = seq + 1
            event = KioskEvent(seq=seq, button=button, status=status, created_at=self._clock())
            self._events.setdefault(kiosk_id, deque(maxlen=MAX_EVENTS_PER_KIOSK)).append(event)
            return event

    def latest_seq(self, kiosk_id: str) -> int:
        with self._lock:
            return self._next_seq.get(kiosk_id, 1) - 1

    def after(self, kiosk_id: str, after_seq: int) -> list[KioskEvent]:
        with self._lock:
            return [e for e in self._events.get(kiosk_id, ()) if e.seq > after_seq]
