"""Phase 7: kiosk button events and streamed ESP32 recordings."""

import pytest

from app.dependencies import get_hardware_service
from app.services.hardware_service import HardwareEventService
from tests.test_voice import make_wav, speech, voice_client  # noqa: F401  (fixtures reused)

API = "/api/v1"


@pytest.fixture
def hw_client(client):
    events = HardwareEventService()
    client.app.dependency_overrides[get_hardware_service] = lambda: events
    return client


def test_button_events_reach_the_app(hw_client):
    # The app starts: it asks for the current position, not old events.
    start = hw_client.get(f"{API}/kiosks/kiosk-1/events?after=-1").json()
    assert start == {"kiosk_id": "kiosk-1", "latest_seq": 0, "events": []}

    for button in ("language", "confirm", "mic"):
        assert hw_client.post(f"{API}/hardware/events", json={"kiosk_id": "kiosk-1", "button": button}).status_code == 201
    hw_client.post(f"{API}/hardware/events", json={"kiosk_id": "kiosk-1", "status": "recording"})

    body = hw_client.get(f"{API}/kiosks/kiosk-1/events?after=0").json()
    assert body["latest_seq"] == 4
    assert [(e["seq"], e["button"], e["status"]) for e in body["events"]] == [
        (1, "language", None), (2, "confirm", None), (3, "mic", None), (4, None, "recording"),
    ]
    # Only newer events on the next poll; other kiosks are separate.
    assert [e["seq"] for e in hw_client.get(f"{API}/kiosks/kiosk-1/events?after=3").json()["events"]] == [4]
    assert hw_client.get(f"{API}/kiosks/kiosk-2/events?after=0").json()["events"] == []
    # Starting again later skips what already happened.
    assert hw_client.get(f"{API}/kiosks/kiosk-1/events?after=-1").json()["events"] == []


@pytest.mark.parametrize("body", [
    {"kiosk_id": "kiosk-1"},  # nothing
    {"kiosk_id": "kiosk-1", "button": "mic", "status": "idle"},  # both
    {"kiosk_id": "kiosk-1", "button": "power"},  # not one of the six buttons
    {"kiosk_id": "kiosk-1", "status": "dancing"},
    {"button": "mic"},  # no kiosk
])
def test_invalid_events_are_rejected(hw_client, body):
    response = hw_client.post(f"{API}/hardware/events", json=body)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_event_history_is_bounded():
    events = HardwareEventService()
    for _ in range(150):
        events.add("kiosk-1", button="mic")
    kept = events.after("kiosk-1", 0)
    assert len(kept) == 100 and kept[0].seq == 51 and events.latest_seq("kiosk-1") == 150


# ---------- streamed recordings from the ESP32 ----------


def _streaming_header(wav: bytes, size_value: int) -> bytes:
    """Replace the RIFF and data sizes the way a streaming recorder does (length unknown)."""
    data = bytearray(wav)
    data[4:8] = size_value.to_bytes(4, "little")
    pos = data.find(b"data")
    data[pos + 4:pos + 8] = size_value.to_bytes(4, "little")
    return bytes(data)


@pytest.mark.parametrize("size_value", [0, 0xFFFFFFFF])
def test_streamed_wav_with_unknown_length_is_accepted(voice_client, size_value):  # noqa: F811
    sid = voice_client.post(f"{API}/sessions", json={"language": "en"}).json()["session_id"]

    def chunks():
        wav = _streaming_header(make_wav(seconds=2), size_value)
        for i in range(0, len(wav), 1024):  # sent piece by piece, like the ESP32
            yield wav[i:i + 1024]

    response = voice_client.post(f"{API}/voice/query", content=chunks(),
                                 headers={"X-Session-Id": sid, "Content-Type": "audio/wav"})
    assert response.status_code == 200
    assert response.json()["status"] == "answered"


def test_streamed_wav_still_limited_to_60_seconds(voice_client):  # noqa: F811
    sid = voice_client.post(f"{API}/sessions", json={"language": "en"}).json()["session_id"]
    wav = _streaming_header(make_wav(seconds=62.5), 0xFFFFFFFF)
    response = voice_client.post(f"{API}/voice/query", content=wav,
                                 headers={"X-Session-Id": sid, "Content-Type": "audio/wav"})
    assert response.status_code == 413
