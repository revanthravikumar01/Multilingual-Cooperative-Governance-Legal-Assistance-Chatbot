"""Client for the local CIVI speech service (speech_service/, Decision 38), plus a small audio cache.

The speech service runs on the same laptop (default http://127.0.0.1:8001) in its own Python
environment, because its GPU PyTorch build and IndicF5's dependencies conflict with this backend.
"""

import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable

import httpx

from app.utils.retry import PermanentServiceError, TemporaryServiceError, with_retries

# The service starts loading models when it starts; a 503 means "not ready yet" and is worth retrying.
_TEMPORARY_STATUS = {408, 429, 500, 502, 503, 504}
# Short retries: the kiosk user is waiting, and a stopped service won't come back in 17 s.
SPEECH_RETRY_DELAYS = (1, 3)


@dataclass
class Transcript:
    text: str
    speech_detected: bool
    seconds: float


class SpeechClient:
    def __init__(self, base_url: str, timeout_seconds: float = 180.0, http: httpx.Client | None = None,
                 retry_delays: tuple[float, ...] = SPEECH_RETRY_DELAYS):
        self.base_url = base_url.rstrip("/")
        self._http = http or httpx.Client(timeout=timeout_seconds)
        self._delays = retry_delays

    def transcribe(self, wav: bytes, language: str) -> Transcript:
        def call() -> dict:
            response = self._send("POST", "/stt", params={"language": language}, content=wav,
                                  headers={"Content-Type": "audio/wav"})
            return response.json()

        body = with_retries(call, "Speech-to-text", delays=self._delays)
        return Transcript(
            text=str(body.get("transcript") or "").strip(),
            speech_detected=bool(body.get("speech_detected", True)),
            seconds=float(body.get("seconds") or 0.0),
        )

    def synthesize(self, text: str, language: str) -> bytes:
        def call() -> bytes:
            return self._send("POST", "/tts", json={"text": text, "language": language}).content

        return with_retries(call, "Text-to-speech", delays=self._delays)

    def _send(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = self._http.request(method, self.base_url + path, **kwargs)
        except httpx.TransportError as exc:  # timeouts, network errors, dropped connections
            raise TemporaryServiceError(f"speech service not reachable: {exc}") from exc
        if response.status_code == 200:
            return response
        detail = _detail(response)
        if response.status_code in _TEMPORARY_STATUS:
            raise TemporaryServiceError(f"speech service HTTP {response.status_code}: {detail}")
        raise PermanentServiceError(f"speech service HTTP {response.status_code}: {detail}")


def _detail(response: httpx.Response) -> str:
    try:
        return str(response.json().get("detail", ""))[:300]
    except ValueError:
        return response.text[:300]


class AudioCache:
    """Keeps recently generated answer audio in memory, so Repeat Voice doesn't regenerate it.

    If two requests ask for the same audio at once (e.g. a background pre-generation and the ESP32),
    the second waits for the first instead of generating it twice.
    """

    def __init__(self, max_items: int = 48):
        self._items: OrderedDict[tuple, bytes] = OrderedDict()
        self._max_items = max_items
        self._lock = threading.Lock()
        self._key_locks: dict[tuple, threading.Lock] = {}

    def get(self, key: tuple) -> bytes | None:
        with self._lock:
            if key in self._items:
                self._items.move_to_end(key)
                return self._items[key]
        return None

    def get_or_create(self, key: tuple, create: Callable[[], bytes]) -> bytes:
        cached = self.get(key)
        if cached is not None:
            return cached
        with self._lock:
            key_lock = self._key_locks.setdefault(key, threading.Lock())
        with key_lock:
            cached = self.get(key)
            if cached is not None:
                return cached
            data = create()
            with self._lock:
                self._items[key] = data
                self._items.move_to_end(key)
                while len(self._items) > self._max_items:
                    old_key, _ = self._items.popitem(last=False)
                    self._key_locks.pop(old_key, None)
            return data
