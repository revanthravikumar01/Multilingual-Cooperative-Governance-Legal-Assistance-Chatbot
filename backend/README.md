# CIVI FastAPI backend (Phase 1)

This is the temporary text-only API foundation. It intentionally does **not** include RAG, Gemini, speech processing, text-to-speech, or ESP32 support.

## Run on the laptop

From this `backend` folder in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

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

The chat reply is deliberately labelled as temporary. Later phases should replace only the `chat()` answer generation while keeping this endpoint contract.
