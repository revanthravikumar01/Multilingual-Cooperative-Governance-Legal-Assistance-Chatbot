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
| 502  | `upstream_error`       | Gemini (or the optional Sarvam service) failed after all retries (Decision 32) |
| 503  | `service_unavailable`  | A dependency is not ready (knowledge base not loaded, free Gemini daily limit used up) |
| 503  | `speech_unavailable`   | The local speech service is not running or still loading its models |
| 400  | `invalid_audio`        | Voice upload is not 16 kHz 16-bit mono WAV |
| 413  | `payload_too_large`    | Voice upload longer than 60 seconds |

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
  "placeholder": false
}
```

| Field            | Meaning                                                                                   |
| ---------------- | ----------------------------------------------------------------------------------------- |
| `answer`         | Plain text. Statements carry markers like `[1]` that match `citations[].number`           |
| `status`         | `answered` · `insufficient_evidence` (Decision 9) · `out_of_scope` (Decision 27)            |
| `citations`      | Built by the backend from document metadata, never written by Gemini (Decision 10). Numbered 1..n in the order the answer uses them. Empty unless `answered` |
| `spoken_summary` | A short spoken version of a long answer (Decision 23), numbers written as words. `null` when the answer is under 300 characters (speak it in full) |
| `placeholder`    | `true` only when `GEMINI_API_KEY` is not set (temporary answer). Flutter ignores it       |

**How an answer is made (✅ Phase 3)**

1. The question is searched in the knowledge base. A short follow-up (≤ 12 words) is also searched together
   with the previous question in the session.
2. No relevant evidence → `insufficient_evidence` with a fixed message. Gemini is **not** called.
3. Gemini (`gemini-3.5-flash-lite` by default, Interactions API, `store: false`) receives only the numbered
   evidence, the last 6 messages of the session, and strict rules. It replies in a fixed JSON shape.
4. The backend checks the reply: unknown `[n]` markers are removed, and an `answered` reply without a valid
   source becomes `insufficient_evidence`. For `insufficient_evidence` / `out_of_scope` the backend uses its own
   fixed text, not Gemini's.

Errors: `502 upstream_error` when Gemini fails after the retries (2 s, 5 s, 10 s); `503 service_unavailable`
when the free daily Gemini limit is used up or the knowledge base can't load. The question stays in the
session history without an answer.

Typed questions do not produce audio. When the kiosk's mode needs speech (Decision 14),
the ESP32 polls the messages and asks for the audio (see Voice).

---

## Voice (ESP32), ✅ Phase 4 (ESP32 side: Phase 7)

The ESP32 has about 320 KB of RAM, while 60 s of 16 kHz 16-bit mono audio is about 1.9 MB. Audio is
therefore **streamed** in both directions with chunked HTTP, never held whole in ESP32 memory.

### Speech engines (Decision 38: free, on the laptop)

Chosen on 2026-11-26 after testing on the kiosk laptop (Ryzen 7, 16 GB RAM, RTX 3050 4 GB).
Numbers come from `speech_bench/` (15 FLEURS clips per language). The engines run in the separate
**speech service** (`speech_service/`, port 8001, localhost only), which this backend calls.

| Job | Engine | Runs on | Measured |
|---|---|---|---|
| Tamil speech → text | AI4Bharat IndicConformer 600M (MIT) | CPU | ~1 s per question, 3.0% character errors |
| English speech → text | OpenAI Whisper small (Apache-2.0) | CPU | ~2 s per question, 6.6% word errors |
| Tamil text → speech | AI4Bharat IndicF5 (MIT) | GPU (bf16, 16 steps) | ~4 s per sentence |
| English text → speech | Windows built-in voice (Microsoft Zira) | CPU | ~1 s |

- The language is locked per session, so the backend always knows which recognizer and voice to use.
- IndicF5 needs ~2.9 GB of the 4 GB GPU, so speech-to-text stays on the CPU.
- IndicF5 speaks in the voice of a short **reference recording**: AI4Bharat's sample voice until a team
  member's recording (made **with their consent**) is added (`speech_service/voices/README.md`).
- Before speaking, the backend makes text speakable: `[n]` markers and list symbols are removed, and
  numbers become words ("Section 34(2)" → "Section thirty-four, sub-section two"; "பிரிவு 20" →
  "பிரிவு இருபது"), because the voices garble digits.
- IndicF5 outputs 24 kHz; the speech service converts all audio to 16 kHz 16-bit mono for the ESP32.
- Recordings quieter than speech are treated as "nothing said" (no guessing from noise).
- Fallback if the kiosk has no NVIDIA GPU: Sarvam text-to-speech (paid, ₹3 per 1,000 characters).

### ✅ `POST /voice/query`

- Headers: `Content-Type: audio/wav`, `X-Session-Id: <id>` (required), `Transfer-Encoding: chunked` (allowed)
- Body: a WAV file, **16 kHz, 16-bit, mono, ≤ 60 s** (Decision 20). Other formats → `400 invalid_audio`;
  longer → `413 payload_too_large`.

The session's language decides the recognizer. The recognised question is answered exactly like a typed
question (no confirmation step, Decision 21) and both messages are stored with `"source": "voice"`, so
Flutter shows them by polling `GET /sessions/{id}/messages`.

Response `200`:

```json
{
  "session_id": "3f6c...",
  "status": "answered",
  "transcript": "கூட்டுறவு சங்கம் என்றால் என்ன?",
  "answer": "... [1] ...",
  "citations": [ { "number": 1, "label": "[1] ...", "...": "..." } ],
  "spoken_summary": "...",
  "user_message_seq": 3,
  "assistant_message_seq": 4,
  "audio": {
    "summary_url": "/api/v1/voice/audio/3f6c.../4?variant=summary",
    "full_url": "/api/v1/voice/audio/3f6c.../4?variant=full"
  },
  "placeholder": false
}
```

If nothing could be recognised (silence, noise), `status` is `"stt_failed"`, `transcript` is `""`,
`user_message_seq` is `null`, and `answer` is a "please repeat in <language>, or type your question" prompt.
The prompt is stored as an assistant message with status `stt_failed`, so Flutter shows it, and its
`audio.summary_url` speaks it (Decision 17).

Errors: `503 speech_unavailable` when the speech service is not running or still loading;
`502 upstream_error` when recognition fails; the usual Gemini errors from `/chat`.

### ✅ `GET /voice/audio/{session_id}/{seq}?variant=summary|full`

A WAV file (16 kHz, 16-bit mono) for the MAX98357A, for **any** assistant message: voice answers, and
typed answers in visually challenged mode (Decision 14).

- `summary` (default): the short `spoken_summary` if the answer has one, otherwise the whole answer.
- `full`: the whole answer. **Confirm** plays `full`; **Repeat Voice** replays whichever variant was last
  played (Decision 24). The ESP32 keeps track of that.
- The summary of a voice answer is generated right after the answer, so it is usually ready when asked
  for. Audio is cached in memory, so Repeat Voice is instant. A long `full` answer takes ~4 s per Tamil
  sentence to generate the first time.
- Does not refresh the session timer. Errors: `404 message_not_found` (no assistant message with that
  number), `503 speech_unavailable`.

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

## Knowledge base (admin): Phase 2

These endpoints accept requests **only from the backend laptop itself** (Decision 30). Set
`CIVI_ADMIN_ALLOW_LAN=true` to also allow devices on the private Wi-Fi. Any other device gets
`403 forbidden`. The easiest way to use them is the browser page `http://127.0.0.1:8000/docs`.

### ✅ `POST /documents`: upload an official PDF

`multipart/form-data`:

| Field               | Required | Values                                                            |
| ------------------- | -------- | ----------------------------------------------------------------- |
| `file`              | yes      | PDF, ≤ 50 MB                                                      |
| `title`             | yes      | Full official title                                               |
| `citation_name`     | no       | Short name for citations (defaults to `title`)                    |
| `issuing_authority` | yes      | e.g. `Government of Tamil Nadu`                                   |
| `jurisdiction`      | yes      | `tamil_nadu` · `central`                                          |
| `doc_type`          | yes      | `act` · `rules` · `scheme` · `guideline` · `circular` · `other`   |
| `language`          | yes      | `en` · `ta` (the language the PDF is written in)                  |
| `published_on`      | no       | `1983`, `1983-05` or `1983-05-21`                                 |
| `validity`          | no       | `current` (default) · `superseded` · `unknown` (Decision 28)      |

Response `202`: the document record with `"status": "processing"`. Processing (text → chunks →
embeddings → ChromaDB) runs right after the response (Decision 5).
Errors: `400 invalid_pdf` (not a PDF, empty, password-protected, too large),
`409 duplicate_document` (same file already uploaded; the message names the existing ID).

### ✅ `GET /documents/{document_id}`

This returns the record: `status` is `processing` · `ready` · `failed`, plus `page_count`, `chunk_count`,
`warnings` (for example "looks like a scanned PDF" or "old non-Unicode Tamil font") and `error`.

### ✅ `GET /documents`

This returns `{ "documents": [...], "total_chunks": 123 }`.

### ✅ `POST /search`: see which evidence a question retrieves (testing and tuning)

```json
{ "query": "How do I register a society?", "language": "en",
  "jurisdiction": "tamil_nadu", "doc_type": "act", "topic": "registration" }
```

`jurisdiction`, `doc_type` and `topic` are optional filters. `topic` is one of `registration`, `membership`,
`elections`, `governance`, `auditing`, `schemes`.

```json
{
  "sufficient": true,
  "evidence": [
    { "chunk_id": "...", "text": "...", "score": 0.71, "similarity": 0.64,
      "citation": { "number": 1, "label": "[1] TN Co-operative Societies Act, 1983, Section 4(1), Page 7", ... } }
  ]
}
```

`sufficient: false` with no evidence means "Verified information is not available" (Decision 9).

For a Tamil question (`"language": "ta"`), the response also includes `translated_query` (the English
translation from Sarvam that was searched). If translation failed after all retries (Decision 32), it includes
`translation_error`, and only the Tamil text was searched, with a stricter threshold.
Phase 3 uses this same retrieval inside `/chat`.

---

## Linking Flutter and the ESP32

1. Flutter starts a conversation: `POST /sessions {language, kiosk_id: "kiosk-1"}`.
2. The ESP32 looks up the active session: `GET /kiosks/kiosk-1/session`.
3. Typed questions go `Flutter → POST /chat`. Voice questions go `ESP32 → POST /voice/query`.
   Both are stored in the same session.
4. Flutter polls `GET /sessions/{id}/messages?after=<seq>` to show voice questions and answers.
