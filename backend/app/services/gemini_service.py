"""Google Gemini client (Interactions API, called with plain httpx).

API reference (checked 2026-11-26, https://aistudio.google.com/docs):
  POST https://generativelanguage.googleapis.com/v1beta/interactions
  headers: x-goog-api-key, Content-Type: application/json, Api-Revision
  body:    model, input (list of steps), system_instruction (string), store,
           generation_config {thinking_level, max_output_tokens},
           response_format {type: "text", mime_type: "application/json", schema}
  reply:   {id, status, steps: [{type: "model_output", content: [{type: "text", text}]}, ...], usage}
  errors:  {"error": {"code": "rate_limit_exceeded", "message": ...}} with the HTTP status

`store` is False: Google does not keep the conversation on its side; the backend sends the
recent history itself on every call (Decision 11). The API key stays on the backend (.env).
"""

import json
import logging

import httpx

from app.utils.retry import PermanentServiceError, TemporaryServiceError, with_retries

INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
log = logging.getLogger("civi.gemini")

_TEMPORARY_STATUS = {408, 429, 500, 502, 503, 504}

_TRANSLATE_INSTRUCTION = (
    "Translate the user's question about co-operative societies in India from Tamil (it may mix "
    "English words) into one clear English question. Keep the meaning exactly; do not answer it and "
    "do not add facts. Use standard legal terms, e.g. கூட்டுறவுச் சங்கம் = co-operative society, "
    "உறுப்பினர் = member, பொதுக்குழு = general body, தணிக்கை = audit, பதிவாளர் = Registrar. "
    'Reply as JSON: {"english": "..."}.'
)
# 429 codes that waiting a few seconds cannot fix (daily quota, no credits).
_NOT_WORTH_RETRYING = {"quota_exceeded", "payment_required"}


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float = 60.0,
        thinking_level: str = "low",
        max_output_tokens: int = 4096,
        api_revision: str = "2026-05-20",
        http: httpx.Client | None = None,
        retry_delays: tuple[float, ...] | None = None,
    ):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set in backend/.env")
        self.model = model
        self.thinking_level = thinking_level
        self.max_output_tokens = max_output_tokens
        self._http = http or httpx.Client(timeout=timeout_seconds)
        self._headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
        if api_revision:
            self._headers["Api-Revision"] = api_revision
        self._retry_kwargs = {} if retry_delays is None else {"delays": retry_delays}

    def generate_json(
        self,
        system_instruction: str,
        turns: list[tuple[str, str]],
        schema: dict,
        thinking_level: str | None = None,
        retry_delays: tuple[float, ...] | None = None,
    ) -> dict:
        """Ask Gemini for one JSON object matching `schema`.

        `turns` is the conversation, oldest first: ("user" | "model", text). The last turn is the
        current question. `thinking_level` / `retry_delays` override the defaults for quick calls.
        Raises TemporaryServiceError / PermanentServiceError on failure.
        """
        payload = {
            "model": self.model,
            "input": [
                {
                    "type": "user_input" if role == "user" else "model_output",
                    "content": [{"type": "text", "text": text}],
                }
                for role, text in turns
            ],
            "system_instruction": system_instruction,
            "store": False,
            "generation_config": {
                "thinking_level": thinking_level or self.thinking_level,
                "max_output_tokens": self.max_output_tokens,
            },
            "response_format": {"type": "text", "mime_type": "application/json", "schema": schema},
        }
        retry_kwargs = self._retry_kwargs if retry_delays is None else {"delays": retry_delays}
        body = with_retries(lambda: self._post(payload), "Gemini", **retry_kwargs)
        return _parse_json_reply(body)

    def translate_question(self, text: str) -> str:
        """Tamil question -> English search query, so it matches the English Acts better.

        A quick call (minimal thinking, one short retry). If it fails, search falls back to the Tamil text.
        """
        reply = self.generate_json(
            _TRANSLATE_INSTRUCTION,
            [("user", text[:1000])],
            {"type": "object", "properties": {"english": {"type": "string"}}, "required": ["english"]},
            thinking_level="minimal",
            retry_delays=(1,),
        )
        english = str(reply.get("english") or "").strip()
        if not english:
            raise PermanentServiceError("Gemini returned an empty translation")
        return english

    def _post(self, payload: dict) -> dict:
        try:
            response = self._http.post(INTERACTIONS_URL, json=payload, headers=self._headers)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise TemporaryServiceError(f"network problem: {exc}") from exc

        if response.status_code == 200:
            try:
                return response.json()
            except ValueError as exc:
                raise TemporaryServiceError("Gemini returned a reply that is not JSON") from exc

        try:
            error = response.json().get("error", {}) or {}
        except ValueError:
            error = {}
        code = str(error.get("code") or error.get("status") or "")
        message = str(error.get("message") or response.text[:200])
        if response.status_code in _TEMPORARY_STATUS and code.lower() not in _NOT_WORTH_RETRYING:
            raise TemporaryServiceError(f"HTTP {response.status_code} {code}: {message}")
        raise PermanentServiceError(f"HTTP {response.status_code} {code}: {message}")


def _reply_text(body: dict) -> str:
    """Join the text parts of the model's output steps (thought steps are skipped)."""
    parts: list[str] = []
    for step in body.get("steps") or []:
        if step.get("type") != "model_output":
            continue
        for item in step.get("content") or []:
            if item.get("type") == "text" and item.get("text"):
                parts.append(item["text"])
    if not parts and isinstance(body.get("output_text"), str):  # tolerate the SDK-style field
        parts.append(body["output_text"])
    return "".join(parts).strip()


def _parse_json_reply(body: dict) -> dict:
    status = body.get("status", "completed")
    if status != "completed":
        # "incomplete" usually means the answer hit max_output_tokens; "failed" includes safety blocks.
        raise PermanentServiceError(f"Gemini did not complete the answer (status: {status})")
    text = _reply_text(body)
    if not text:
        raise PermanentServiceError("Gemini returned an empty answer")
    try:
        data = json.loads(text)
    except ValueError as exc:
        log.warning("Gemini reply was not valid JSON: %.200s", text)
        raise PermanentServiceError("Gemini's answer was not in the expected format") from exc
    if not isinstance(data, dict):
        raise PermanentServiceError("Gemini's answer was not in the expected format")
    return data
