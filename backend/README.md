# CIVI FastAPI backend (Phase 1)

Modular FastAPI foundation with temporary in-memory sessions. Answers are still placeholders: RAG, Gemini, Sarvam speech and ESP32 support come in later phases.

The full endpoint list (implemented and planned) is in [API_CONTRACT.md](API_CONTRACT.md).

## Folder layout

```
main.py                  builds the app and registers routes
app/config.py            settings from .env
app/errors.py            one error format for every endpoint
app/dependencies.py      shared objects (the session store)
app/api/                 endpoints: health, sessions, chat
app/models/              request/response shapes
app/services/            logic: sessions, answers (placeholder), documents, embeddings, vector store, retrieval, citations
app/utils/               PDF reading, legal chunking, text helpers
app/scripts/kb.py        knowledge-base command-line tool
knowledge_base/          uploads/ (PDFs) + documents.json are committed; chroma_db/ is rebuilt locally
tests/                   automated tests
```

## Run on the laptop

From this `backend` folder in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

All commands call the environment's Python directly (`.\.venv\Scripts\python.exe`), so you don't need `Activate.ps1`. Windows PowerShell blocks that script by default ("running scripts is disabled on this system"). In the commands below, `python` means `.\.venv\Scripts\python.exe`.

Verify locally at `http://127.0.0.1:8000/api/v1/health` or use the automatic API documentation at `http://127.0.0.1:8000/docs`.

The `.env` file is optional for the native mobile app. Its `CIVI_ALLOWED_ORIGINS` setting controls browser CORS when you later run Flutter web.

## Phone over Wi-Fi

1. Connect the laptop and phone to the same Wi-Fi network.
2. On the laptop, run `ipconfig` and copy the IPv4 address for the active Wi-Fi adapter, for example `192.168.1.20`.
3. If Windows asks, allow Python through the **Private** network firewall. Otherwise add an inbound Private-network rule for TCP port `8000`.
4. Start Flutter with the address from step 2:

```powershell
flutter run --dart-define=CIVI_API_BASE_URL=http://192.168.1.20:8000
```

Do not use `127.0.0.1` or `localhost` on a physical phone: they refer to the phone itself. For an Android emulator, use `http://10.0.2.2:8000` instead.

## Test endpoint

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/chat -ContentType 'application/json' -Body '{"message":"What is a cooperative society?","language":"en"}'
```

The chat reply is deliberately labelled as temporary. Phases 2–3 replace only `app/services/answer_service.py`; the endpoint contract stays the same.

## Knowledge base

**Add a PDF** in one of two ways:
- In the browser, open `http://127.0.0.1:8000/docs`, choose `POST /api/v1/documents`, click *Try it out*, pick the PDF, fill in the fields and click *Execute*. Then check `GET /api/v1/documents/{id}` until the status is `ready`.
- From PowerShell (in this folder, with the venv active):

```powershell
python -m app.scripts.kb add C:\Users\you\Downloads\tn_act_1983.pdf --title "Tamil Nadu Co-operative Societies Act, 1983" --citation-name "TN Co-operative Societies Act, 1983" --authority "Government of Tamil Nadu" --jurisdiction tamil_nadu --type act --language en --published 1983
```

The embedding model is **BAAI/bge-m3**. It's free and runs on this laptop, with no API key. It needs a one-time download (about 2.3 GB) and about 2.5 GB of memory while running. Download it first. If the connection stalls, it resumes automatically, and you can run it again if your internet drops:

```powershell
python -m app.scripts.download_model
```

**Other commands:**

```powershell
python -m app.scripts.kb list
python -m app.scripts.kb search "How do I register a cooperative society?"
python -m app.scripts.kb rebuild
```

`rebuild` recreates `knowledge_base/chroma_db/` from the committed PDFs and `documents.json` (about 17 minutes for the current 3 PDFs on a Ryzen 7). Run it after cloning the repo, or after changing the chunking settings or the embedding model in `.env`. If the model was changed without a rebuild, searches stop with a message asking you to rebuild.

Watch the `warnings` on each document. *Scanned PDF* or *non-Unicode Tamil font* means the extracted text is unreliable, and the document needs OCR or a better source.

**Tamil questions** work directly: bge-m3 matches Tamil questions to the English Acts (4 of 4 Tamil test questions find the right section). As an *optional* extra, a Sarvam key in `backend/.env` (`SARVAM_API_KEY=...`, never commit it) also translates Tamil questions to English before searching. That's paid, at about ₹0.20 per question, and not needed.

**Measure search quality** with the test questions in `evaluation/questions.json`:

```powershell
python -m app.scripts.evaluate
python -m app.scripts.evaluate --verbose --threshold 0.4
```

Re-run it after adding documents or changing settings. Add new questions to the JSON file whenever you find a question the chatbot answers badly.

**Windows note:** ChromaDB, PyTorch and scikit-learn include native files. If Windows *Smart App Control* blocks them ("An Application Control policy has blocked this file"), the knowledge base cannot start. The rest of the API (chat, sessions) still works.

## Run the tests

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```
