# CIVI kiosk ESP32 (Phase 7)

Status on 2026-11-26: **not wired yet.** The backend and the app side of the kiosk buttons are ready and tested
with a laptop stand-in for the ESP32; the firmware is written after the hardware is wired to the plan.

1. **Wire** the board following [WIRING.md](WIRING.md) (ESP32 DevKit V1, 30-pin).
2. **Firmware** (next step): PlatformIO project in this folder, built and tested part by part —
   speaker → microphone → buttons → Wi-Fi + backend. Wi-Fi name/password go in a git-ignored `secrets.h`.
3. **Run the app** with the ESP32 in charge of audio:

   ```powershell
   flutter run --dart-define=CIVI_API_BASE_URL=http://<laptop-ip>:8000 --dart-define=CIVI_APP_AUDIO=false
   ```

## Testing without the ESP32

`backend/app/scripts/fake_esp32.py` behaves exactly like the planned firmware (button presses, status reports,
streamed recordings, playback). With the backend, speech service and app running:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.scripts.fake_esp32 --wav C:\path\to\question.wav
```

Then type `l` (Language), `y` (Confirm), `b` (Back), `r` (Repeat), `m` (Mic: press twice), `v` (Visually
Challenged) and press Enter. The question WAV must be 16 kHz, 16-bit, mono.

How the ESP32, backend and app talk to each other: `backend/API_CONTRACT.md`, "Hardware buttons" and "Voice".
