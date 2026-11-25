# CIVI API Contract (V1)

**Protocol (Decision 37): REST over HTTP on the local Wi-Fi network.**
Flutter and the ESP32 each talk to FastAPI directly. There are no WebSockets in V1.
Flutter learns about voice questions (asked through the ESP32) by **polling**
the session's message list every 1–2 seconds.

Base URL: `http://<laptop-wifi-ip>:8000/api/v1`

Status legend: ✅ implemented · 🕓 planned (contract fixed now, built in the named phase)

---

## Common rules

- Request and response bodies are JSON (UTF-8), except audio and PDF uploads.
- `language` is always `"en"` (English) or `"ta"` (Tamil).
- A session's language cannot change (Decision 16). To switch language, create a new session.
- Sessions expire after **30 minutes of inactivity** (Decision 31). Every chat or
  voice request refreshes the timer. Reading messages (polling) does **not**.
- Times are ISO-8601 UTC strings, e.g. `2026-11-25T10:15:00Z`.

### Error format

Every error response uses the same shape:

```json
{
  "error": {
    "code": "session_not_found",
    "message": "Session not found or expired. Start a new session."
  }
}
```

| HTTP | `code`                 | Meaning                                                   |
| ---- | ---------------------- | --------------------------------------------------------- |
| 400  | `invalid_request`      | Body failed validation (missing field, bad language, ...) |
| 404  | `session_not_found`    | Session ID is unknown or has expired                      |
| 409  | `language_mismatch`    | Request language differs from the session's language      |
| 502  | `upstream_error`       | Gemini / Sarvam failed after all retries (Decision 32)    |
| 503  | `service_unavailable`  | A dependency (e.g. the knowledge base) is not ready yet   |

---

## Health

### ✅ `GET /health`

```json
{ "status": "ok", "service": "civi-api", "timestamp": "2026-11-25T10:15:00Z" }
```

---

## Sessions

### ✅ `POST /sessions`: start a new conversation

Request:

```json
{ "language": "ta", "kiosk_id": "kiosk-1" }
```

`kiosk_id` is optional. When it is given, this session becomes the kiosk's
**active session**, which is how the ESP32 and Flutter share one conversation
(see "Linking Flutter and the ESP32" below).

Response `201`:

```json
{
  "session_id": "3f6c1e0a9b2d4c7e8f1a2b3c4d5e6f70",
  "language": "ta",
  "kiosk_id": "kiosk-1",
  "created_at": "2026-11-25T10:15:00Z",
  "expires_at": "2026-11-25T10:45:00Z"
}
```

### ✅ `GET /sessions/{session_id}`

This returns the same body as above and **does not** refresh the timer. It returns `404` if the session has expired.

### ✅ `DELETE /sessions/{session_id}`: end a conversation (the Reset button)

Response `204`, with no body. Ending a session that is already gone also returns `204`.

### ✅ `GET /sessions/{session_id}/messages?after=<seq>`: polling

This returns the messages whose `seq` is greater than `after` (default `0`, meaning all messages).
Flutter keeps the highest `seq` it has seen and sends it next time.

```json
{
  "session_id": "3f6c...",
  "messages": [
    {
      "seq": 1,
      "role": "user",
      "text": "கூட்டுறவு சங்கம் என்றால் என்ன?",
      "source": "voice",
      "created_at": "2026-11-25T10:16:02Z"
    },
    {
      "seq": 2,
      "role": "assistant",
      "text": "...full written answer...",
      "source": "voice",
      "status": "answered",
      "citations": [ ...see Citation below... ],
      "spoken_summary": "...short summary...",
      "created_at": "2026-11-25T10:16:07Z"
    }
  ]
}
```

`source` is `"text"` (typed in Flutter) or `"voice"` (spoken at the ESP32).

### 🕓 `GET /kiosks/{kiosk_id}/session` (Phase 7)

The ESP32 calls this to find the kiosk's active session. It returns the session body, or `404` if there is none.

---

## Chat (typed questions)

### ✅ `POST /chat`

Request:

```json
{
  "message": "What is a cooperative society?",
  "language": "en",
  "session_id": "3f6c1e0a9b2d4c7e8f1a2b3c4d5e6f70"
}
```

`session_id` is **optional** so the current Flutter app keeps working.
If it is missing, the backend creates a new session and returns its ID. The client
should send that ID with every later message.

Response `200`:

```json
{
  "session_id": "3f6c1e0a9b2d4c7e8f1a2b3c4d5e6f70",
  "answer": "A cooperative society is ...",
  "status": "answered",
  "citations": [
    {
      "number": 1,
      "label": "[1] Tamil Nadu Co-operative Societies Act, 1983, Section 2, Page 4",
      "document_id": "tn-coop-act-1983",
      "document_title": "Tamil Nadu Co-operative Societies Act, 1983",
      "issuing_authority": "Government of Tamil Nadu",
      "chapter": "I",
      "section": "2",
      "subsection": null,
      "page": 4,
      "published_on": "1983-..."
    }
  ],
  "spoken_summary": null,
  "user_message_seq": 1,
  "assistant_message_seq": 2,
  "placeholder": true
}
```

| Field            | Meaning                                                                                   |
| ---------------- | ----------------------------------------------------------------------------------------- |
| `status`         | `answered` · `insufficient_evidence` (Decision 9) · `out_of_scope` (Decision 27)            |
| `citations`      | Built by the backend from document metadata, never written by Gemini (Decision 10). Empty unless `answered` |
| `spoken_summary` | A short spoken version of a long answer (Decision 23). `null` when the full answer is short enough to speak |
| `placeholder`    | `true` until RAG + Gemini are connected (Phases 2–3). Flutter ignores it                  |

Typed questions do not produce audio. When the kiosk's mode needs speech (Decision 14),
the ESP32 polls the messages and asks for the audio (see Voice).

---

## Voice (ESP32), 🕓 Phase 4 / Phase 7

The ESP32 has about 320 KB of RAM, while 60 s of 16 kHz 16-bit mono audio is about 1.9 MB. Audio is
therefore **streamed** in both directions with chunked HTTP, never held whole in ESP32 memory.

### 🕓 `POST /voice/query`

- Headers: `Content-Type: audio/wav`, `X-Session-Id: <id>`, `Transfer-Encoding: chunked`
- Body: a WAV file, **16 kHz, 16-bit, mono, ≤ 60 s** (Decision 20)

Response `200`:

```json
{
  "session_id": "3f6c...",
  "status": "answered",
  "transcript": "கூட்டுறவு சங்கம் என்றால் என்ன?",
  "answer": "...",
  "spoken_summary": "...",
  "audio": {
    "summary_url": "/api/v1/voice/audio/ab12?variant=summary",
    "full_url": "/api/v1/voice/audio/ab12?variant=full"
  }
}
```

If speech is not recognized, `status` is `"stt_failed"` and `audio.summary_url` points to the spoken
"please repeat" prompt (Decision 17).

### 🕓 `GET /voice/audio/{audio_id}?variant=summary|full`

This streams a WAV file (16 kHz, 16-bit mono) for the MAX98357A. **Confirm** plays `full`, and
**Repeat Voice** replays whichever variant was last selected (Decision 24).

---

## Hardware buttons, 🕓 Phase 7

### 🕓 `POST /hardware/events`

```json
{ "kiosk_id": "kiosk-1", "button": "language" }
```

`button` is one of `language`, `confirm`, `back`, `repeat`, `mic`, `accessibility`.
Microphone recording, the stop-at-60-seconds limit and playback interruption happen on the ESP32 itself. This
endpoint only reports state changes, such as language or mode, so Flutter can show them.

---

## Documents (admin, local network only), 🕓 Phase 2

### 🕓 `POST /documents`

`multipart/form-data` with fields `file` (PDF), `title`, `issuing_authority`, `jurisdiction`
(`tamil_nadu` | `central`), `doc_type` (`act` | `rules` | `scheme` | `guideline`), `published_on`.
It is processed automatically (Decision 5). Response `202` returns `{ "document_id": "...", "status": "processing" }`.

### 🕓 `GET /documents/{document_id}`

This returns the processing status: `processing` | `ready` | `failed` | `duplicate`.

It is only accepted from the laptop itself or the trusted local network (Decision 30).

---

## Linking Flutter and the ESP32

1. Flutter starts a conversation: `POST /sessions {language, kiosk_id: "kiosk-1"}`.
2. The ESP32 looks up the active session: `GET /kiosks/kiosk-1/session`.
3. Typed questions go `Flutter → POST /chat`. Voice questions go `ESP32 → POST /voice/query`.
   Both are stored in the same session.
4. Flutter polls `GET /sessions/{id}/messages?after=<seq>` to show voice questions and answers.
