"""Sarvam AI client. Phase 2 uses translation only; speech (STT/TTS) is added in Phase 4.

API reference (checked 2026-11-25): POST https://api.sarvam.ai/translate
  headers: api-subscription-key
  body:    input, source_language_code ("ta-IN"/"en-IN"), target_language_code, model, mode
  reply:   {"translated_text": ..., "source_language_code": ..., "request_id": ...}
The API key stays on the backend (.env). It never goes to Flutter or the ESP32.
"""

import httpx

from app.utils.retry import PermanentServiceError, TemporaryServiceError, with_retries

TRANSLATE_URL = "https://api.sarvam.ai/translate"
LANGUAGE_CODES = {"en": "en-IN", "ta": "ta-IN"}
# mayura:v1 accepts up to 1000 characters; questions are far shorter.
MAX_TRANSLATE_CHARS = 1000

# HTTP statuses worth retrying: rate limited, server errors, gateway problems.
_TEMPORARY_STATUS = {408, 429, 500, 502, 503, 504}


class SarvamClient:
    def __init__(
        self,
        api_key: str,
        translate_model: str = "mayura:v1",
        timeout_seconds: float = 15.0,
        http: httpx.Client | None = None,
        retry_delays: tuple[float, ...] | None = None,
    ):
        if not api_key:
            raise ValueError("SARVAM_API_KEY is not set in backend/.env")
        self.translate_model = translate_model
        self._http = http or httpx.Client(timeout=timeout_seconds)
        self._headers = {"api-subscription-key": api_key, "Content-Type": "application/json"}
        self._retry_kwargs = {} if retry_delays is None else {"delays": retry_delays}

    def _post(self, url: str, payload: dict) -> dict:
        try:
            response = self._http.post(url, json=payload, headers=self._headers)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise TemporaryServiceError(f"network problem: {exc}") from exc

        if response.status_code == 200:
            return response.json()

        try:
            error = response.json().get("error", {})
        except ValueError:
            error = {}
        code, message = error.get("code", ""), error.get("message", response.text[:200])
        # Running out of credits also returns 429, but waiting won't help.
        if response.status_code in _TEMPORARY_STATUS and code != "insufficient_quota_error":
            raise TemporaryServiceError(f"HTTP {response.status_code} {code}: {message}")
        raise PermanentServiceError(f"HTTP {response.status_code} {code}: {message}")

    def translate(self, text: str, source: str, target: str) -> str:
        """Translate between "ta" and "en". Raises Temporary/PermanentServiceError on failure."""
        payload = {
            "input": text[:MAX_TRANSLATE_CHARS],
            "source_language_code": LANGUAGE_CODES[source],
            "target_language_code": LANGUAGE_CODES[target],
            "model": self.translate_model,
            "mode": "formal",
        }
        body = with_retries(lambda: self._post(TRANSLATE_URL, payload), "Sarvam translate", **self._retry_kwargs)
        translated = (body.get("translated_text") or "").strip()
        if not translated:
            raise PermanentServiceError("Sarvam returned an empty translation")
        return translated
