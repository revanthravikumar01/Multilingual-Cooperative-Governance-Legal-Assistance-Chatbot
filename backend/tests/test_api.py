"""Tests for the Phase 1 endpoints. Run from the backend folder:  python -m pytest"""

API = "/api/v1"


def test_health(client):
    response = client.get(f"{API}/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


# ---------- chat ----------


def test_chat_without_session_creates_one(client):
    """The current Flutter app sends only message + language; that must keep working."""
    response = client.post(f"{API}/chat", json={"message": "What is a cooperative society?", "language": "en"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer"]
    assert body["session_id"]
    assert body["status"] == "answered"
    assert body["citations"] == []
    assert body["placeholder"] is True
    assert (body["user_message_seq"], body["assistant_message_seq"]) == (1, 2)


def test_chat_reuses_session(client):
    first = client.post(f"{API}/chat", json={"message": "Q1", "language": "ta"}).json()
    second = client.post(
        f"{API}/chat", json={"message": "Q2", "language": "ta", "session_id": first["session_id"]}
    ).json()
    assert second["session_id"] == first["session_id"]
    assert second["user_message_seq"] == 3


def test_chat_rejects_language_change(client):
    sid = client.post(f"{API}/sessions", json={"language": "en"}).json()["session_id"]
    response = client.post(f"{API}/chat", json={"message": "Q", "language": "ta", "session_id": sid})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "language_mismatch"


def test_chat_unknown_session(client):
    response = client.post(f"{API}/chat", json={"message": "Q", "language": "en", "session_id": "nope"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "session_not_found"


def test_chat_validation_errors(client):
    for bad in ({"message": "", "language": "en"}, {"message": "Q", "language": "hi"}, {"language": "en"}):
        response = client.post(f"{API}/chat", json=bad)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_request"


# ---------- sessions ----------


def test_create_and_get_session(client):
    created = client.post(f"{API}/sessions", json={"language": "ta", "kiosk_id": "kiosk-1"})
    assert created.status_code == 201
    body = created.json()
    assert body["language"] == "ta"
    assert body["kiosk_id"] == "kiosk-1"

    fetched = client.get(f"{API}/sessions/{body['session_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["session_id"] == body["session_id"]


def test_end_session(client):
    sid = client.post(f"{API}/sessions", json={"language": "en"}).json()["session_id"]
    assert client.delete(f"{API}/sessions/{sid}").status_code == 204
    assert client.get(f"{API}/sessions/{sid}").status_code == 404
    assert client.delete(f"{API}/sessions/{sid}").status_code == 204  # ending twice is fine


def test_session_expires_after_30_minutes_of_inactivity(client, clock):
    sid = client.post(f"{API}/sessions", json={"language": "en"}).json()["session_id"]

    clock.advance(20)
    assert client.post(f"{API}/chat", json={"message": "Q", "language": "en", "session_id": sid}).status_code == 200

    clock.advance(20)  # 40 min after start, but only 20 since last activity: still alive
    assert client.get(f"{API}/sessions/{sid}").status_code == 200

    clock.advance(10)  # 30 min since last activity: expired
    assert client.get(f"{API}/sessions/{sid}").status_code == 404


def test_polling_does_not_refresh_timer(client, clock):
    sid = client.post(f"{API}/sessions", json={"language": "en"}).json()["session_id"]
    clock.advance(29)
    assert client.get(f"{API}/sessions/{sid}/messages").status_code == 200
    clock.advance(1)
    assert client.get(f"{API}/sessions/{sid}/messages").status_code == 404


def test_messages_polling_with_after(client):
    sid = client.post(f"{API}/sessions", json={"language": "en"}).json()["session_id"]
    client.post(f"{API}/chat", json={"message": "Q1", "language": "en", "session_id": sid})
    client.post(f"{API}/chat", json={"message": "Q2", "language": "en", "session_id": sid})

    all_messages = client.get(f"{API}/sessions/{sid}/messages").json()["messages"]
    assert [m["seq"] for m in all_messages] == [1, 2, 3, 4]
    assert [m["role"] for m in all_messages] == ["user", "assistant", "user", "assistant"]
    assert all_messages[0]["text"] == "Q1"
    assert all_messages[0]["source"] == "text"

    newer = client.get(f"{API}/sessions/{sid}/messages", params={"after": 2}).json()["messages"]
    assert [m["seq"] for m in newer] == [3, 4]


def test_new_kiosk_session_replaces_old_one(service):
    old = service.create("en", kiosk_id="kiosk-1")
    new = service.create("ta", kiosk_id="kiosk-1")
    assert service.get_for_kiosk("kiosk-1").session_id == new.session_id
    try:
        service.get(old.session_id)
        raise AssertionError("old kiosk session should have been ended")
    except Exception as exc:  # SessionNotFound
        assert getattr(exc, "code", None) == "session_not_found"


def test_history_is_capped(service):
    session = service.create("en")
    for i in range(50):
        service.add_message(session.session_id, "user", f"m{i}", "text")
    messages = service.messages_after(session.session_id)
    assert len(messages) == 40
    assert messages[-1].seq == 50


# ---------- kiosk ----------


def test_kiosk_session_lookup(client):
    assert client.get(f"{API}/kiosks/kiosk-1/session").status_code == 404
    first = client.post(f"{API}/sessions", json={"language": "ta", "kiosk_id": "kiosk-1"}).json()
    found = client.get(f"{API}/kiosks/kiosk-1/session").json()
    assert found["session_id"] == first["session_id"] and found["language"] == "ta"
    # A new conversation at the kiosk replaces the old one.
    second = client.post(f"{API}/sessions", json={"language": "en", "kiosk_id": "kiosk-1"}).json()
    assert client.get(f"{API}/kiosks/kiosk-1/session").json()["session_id"] == second["session_id"]
    assert client.get(f"{API}/sessions/{first['session_id']}").status_code == 404
