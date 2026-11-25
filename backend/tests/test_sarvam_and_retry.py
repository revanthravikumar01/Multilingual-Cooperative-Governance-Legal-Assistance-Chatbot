"""Tests for the retry schedule and the Sarvam translate client. A fake HTTP server stands in for
Sarvam, so no API key or internet is needed and no credits are spent."""

import json

import httpx
import pytest

from app.services.sarvam_service import TRANSLATE_URL, SarvamClient
from app.utils.retry import PermanentServiceError, TemporaryServiceError, with_retries

# ---------- retry schedule (Decision 32) ----------


def test_retry_schedule_then_success():
    waits, calls = [], []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise TemporaryServiceError("timeout")
        return "ok"

    assert with_retries(flaky, "test", sleep=waits.append) == "ok"
    assert waits == [2, 5]


def test_retry_gives_up_after_three_retries():
    waits = []

    def always_down():
        raise TemporaryServiceError("down")

    with pytest.raises(TemporaryServiceError):
        with_retries(always_down, "test", sleep=waits.append)
    assert waits == [2, 5, 10]


def test_permanent_errors_are_not_retried():
    waits = []

    def bad_request():
        raise PermanentServiceError("bad key")

    with pytest.raises(PermanentServiceError):
        with_retries(bad_request, "test", sleep=waits.append)
    assert waits == []


# ---------- Sarvam translate client ----------


def _client(handler) -> SarvamClient:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return SarvamClient("test-key", http=http, retry_delays=(0, 0, 0))


def test_translate_sends_documented_request():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers["api-subscription-key"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"translated_text": "How do I join as a member?", "source_language_code": "ta-IN"})

    result = _client(handler).translate("உறுப்பினராக எப்படி சேர்வது?", source="ta", target="en")
    assert result == "How do I join as a member?"
    assert seen["url"] == TRANSLATE_URL
    assert seen["key"] == "test-key"
    assert seen["body"]["source_language_code"] == "ta-IN"
    assert seen["body"]["target_language_code"] == "en-IN"
    assert seen["body"]["model"] == "mayura:v1"


def test_translate_retries_rate_limit_then_succeeds():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, json={"error": {"code": "rate_limit_exceeded_error", "message": "slow down"}})
        return httpx.Response(200, json={"translated_text": "ok"})

    assert _client(handler).translate("வணக்கம்", "ta", "en") == "ok"
    assert len(calls) == 2


def test_translate_retries_network_errors():
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ConnectError("no internet")

    with pytest.raises(TemporaryServiceError):
        _client(handler).translate("வணக்கம்", "ta", "en")
    assert len(calls) == 4  # first try + 3 retries


@pytest.mark.parametrize(
    "status, code",
    [(403, "invalid_api_key_error"), (400, "invalid_request_error"), (429, "insufficient_quota_error")],
)
def test_translate_permanent_errors_fail_fast(status, code):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status, json={"error": {"code": code, "message": "no"}})

    with pytest.raises(PermanentServiceError, match=code):
        _client(handler).translate("வணக்கம்", "ta", "en")
    assert len(calls) == 1


def test_missing_api_key_is_rejected():
    with pytest.raises(ValueError, match="SARVAM_API_KEY"):
        SarvamClient("")
