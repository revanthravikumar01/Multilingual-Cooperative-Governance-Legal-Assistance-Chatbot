"""A stand-in for the kiosk's ESP32, run on the laptop (Phase 7).

It talks to the backend exactly like the firmware will, so the buttons, the app and voice can be tested
before the hardware is wired. It is also the reference for the firmware's behaviour.

  python -m app.scripts.fake_esp32 --wav question.wav            (interactive: press keys, then Enter)
  python -m app.scripts.fake_esp32 --press language confirm      (send button presses and exit)

Keys:  l = Language   y = Confirm   b = Back   r = Repeat Voice   m = Microphone   v = Visually Challenged
       q = quit

What the real ESP32 does for each button (this script does the same):
  - every press is reported:  POST /hardware/events {"kiosk_id", "button"}
  - Microphone, 1st press:    stop any playback, report status "recording", start recording
  - Microphone, 2nd press:    report "processing", look up the kiosk's session
                              (GET /kiosks/{id}/session), stream the WAV to POST /voice/query with an
                              "unknown length" header, then report "speaking", play the summary
                              (GET /voice/audio/...?variant=summary), report "idle"
  - Repeat Voice:             play the last played audio again
  - Confirm:                  play the whole latest answer (variant=full)
The app (with CIVI_APP_AUDIO=false) shows the status and the conversation; it plays no audio itself.
"""

import argparse
import io
import sys
import time
import wave

import httpx

BUTTONS = {"l": "language", "y": "confirm", "b": "back", "r": "repeat", "m": "mic", "v": "accessibility"}


class FakeEsp32:
    def __init__(self, api: str, kiosk_id: str, wav_path: str | None, play: bool):
        self.http = httpx.Client(base_url=api.rstrip("/") + "/api/v1", timeout=300)
        self.kiosk_id = kiosk_id
        self.wav_path = wav_path
        self.play_audio = play
        self.recording_since: float | None = None
        self.last_audio_url: str | None = None
        self.last_answer: tuple[str, int] | None = None  # (session_id, assistant seq)

    # ---------- reports ----------

    def report(self, button: str | None = None, status: str | None = None) -> None:
        body = {"kiosk_id": self.kiosk_id, **({"button": button} if button else {"status": status})}
        response = self.http.post("/hardware/events", json=body)
        what = button or f"status={status}"
        print(f"  -> {what}: HTTP {response.status_code}")

    # ---------- buttons ----------

    def press(self, button: str) -> None:
        self.report(button=button)
        if button == "mic":
            self._mic()
        elif button in ("repeat", "confirm"):
            answer = self.last_answer or self._latest_answer()
            if answer is None:
                print("  no answer to speak yet")
                return
            session_id, seq = answer
            if button == "repeat":
                self._play(self.last_audio_url or f"/voice/audio/{session_id}/{seq}?variant=summary")
            else:
                self._play(f"/voice/audio/{session_id}/{seq}?variant=full")

    def _latest_answer(self) -> tuple[str, int] | None:
        """After a restart the ESP32 doesn't remember the last answer: ask the backend for it."""
        session = self.http.get(f"/kiosks/{self.kiosk_id}/session")
        if session.status_code != 200:
            return None
        session_id = session.json()["session_id"]
        messages = self.http.get(f"/sessions/{session_id}/messages").json().get("messages", [])
        answers = [m["seq"] for m in messages if m["role"] == "assistant"]
        return (session_id, answers[-1]) if answers else None

    def _mic(self) -> None:
        if self.recording_since is None:
            if not self.wav_path:
                print("  (no --wav file given: can't simulate the microphone)")
                return
            self._stop_playback()
            self.recording_since = time.monotonic()
            self.report(status="recording")
            print("  recording... press m again to send")
            return
        self.recording_since = None
        self.report(status="processing")
        session = self.http.get(f"/kiosks/{self.kiosk_id}/session")
        if session.status_code != 200:
            print("  no active conversation on this kiosk (open the app's chat screen first)")
            self.report(status="idle")
            return
        session_id = session.json()["session_id"]
        started = time.perf_counter()
        response = self.http.post(
            "/voice/query",
            content=_stream_like_esp32(self.wav_path),
            headers={"X-Session-Id": session_id, "Content-Type": "audio/wav"},
        )
        if response.status_code != 200:
            print(f"  voice error {response.status_code}: {response.text[:200]}")
            self.report(status="idle")
            return
        body = response.json()
        print(f"  heard ({time.perf_counter() - started:.1f} s): {body['transcript'] or '(nothing)'}  [{body['status']}]")
        self.last_answer = (session_id, body["assistant_message_seq"])
        self._play(body["audio"]["summary_url"].removeprefix("/api/v1"))  # reports "speaking", then "idle"

    # ---------- audio ----------

    def _play(self, url: str) -> None:
        self.last_audio_url = url
        started = time.perf_counter()
        audio = self.http.get(url)
        if audio.status_code != 200:
            print(f"  audio error {audio.status_code}: {audio.text[:200]}")
            return
        seconds = (len(audio.content) - 44) / 32000
        print(f"  speaking: {seconds:.1f} s of audio (ready in {time.perf_counter() - started:.1f} s)")
        self.report(status="speaking")
        if self.play_audio:
            try:
                import winsound

                winsound.PlaySound(audio.content, winsound.SND_MEMORY)
            except (ImportError, RuntimeError) as exc:
                print(f"  (could not play: {exc})")
        self.report(status="idle")

    def _stop_playback(self) -> None:
        try:
            import winsound

            winsound.PlaySound(None, 0)
        except ImportError:
            pass


def _stream_like_esp32(path: str):
    """Yield the WAV in 4 KB pieces with "unknown length" sizes, the way the ESP32 streams it."""
    with wave.open(path) as w:
        if (w.getnchannels(), w.getsampwidth(), w.getframerate()) != (1, 2, 16000):
            sys.exit("Use a 16 kHz, 16-bit, mono WAV (the kiosk format).")
        pcm = w.readframes(w.getnframes())
    header = io.BytesIO()
    with wave.open(header, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"")
    head = bytearray(header.getvalue())
    head[4:8] = (0xFFFFFFFF).to_bytes(4, "little")  # RIFF size unknown
    head[40:44] = (0xFFFFFFFF).to_bytes(4, "little")  # data size unknown
    yield bytes(head)
    for i in range(0, len(pcm), 4096):
        yield pcm[i:i + 4096]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--kiosk", default="kiosk-1")
    parser.add_argument("--wav", help="16 kHz 16-bit mono WAV used as 'what the microphone heard'")
    parser.add_argument("--no-play", action="store_true", help="don't play answers on the laptop speakers")
    parser.add_argument("--press", nargs="+", choices=sorted(BUTTONS.values()), help="send these presses and exit")
    args = parser.parse_args()

    esp = FakeEsp32(args.api, args.kiosk, args.wav, play=not args.no_play)
    if args.press:
        for button in args.press:
            print(button)
            esp.press(button)
            time.sleep(0.6)
        return 0

    print(__doc__.split("Keys:")[1].split("What the real")[0])
    while True:
        try:
            key = input("button> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return 0
        if key == "q":
            return 0
        if key in BUTTONS:
            esp.press(BUTTONS[key])
        elif key:
            print("  unknown key")


if __name__ == "__main__":
    raise SystemExit(main())
