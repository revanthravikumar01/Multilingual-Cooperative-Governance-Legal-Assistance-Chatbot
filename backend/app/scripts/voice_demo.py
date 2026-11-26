"""Try the voice flow without the ESP32: send a recorded question, hear the spoken answer.

  python -m app.scripts.voice_demo question.wav --language ta
  python -m app.scripts.voice_demo question.wav --language en --full     (speak the whole answer)

Needs the backend (port 8000) and the speech service (port 8001) running. The WAV can be any PCM WAV
(e.g. exported from Audacity or Windows Sound Recorder converted to WAV); it is converted to the kiosk
format, 16 kHz 16-bit mono, before sending, exactly what the ESP32 will send.
"""

import argparse
import io
import sys
import time
import wave

import httpx
import numpy as np

KIOSK_RATE = 16_000


def to_kiosk_wav(path: str) -> bytes:
    with wave.open(path) as w:
        channels, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(w.getnframes())
    if width != 2:
        sys.exit("Please use a 16-bit PCM WAV file.")
    audio = np.frombuffer(raw, dtype="<i2").astype("float32").reshape(-1, channels).mean(axis=1)
    if rate != KIOSK_RATE:
        n = int(len(audio) * KIOSK_RATE / rate)
        audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(KIOSK_RATE)
        w.writeframes(np.clip(audio, -32768, 32767).astype("<i2").tobytes())
    return out.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("wav")
    parser.add_argument("--language", choices=["en", "ta"], default="en")
    parser.add_argument("--full", action="store_true", help="speak the whole answer instead of the summary")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--save", default="answer.wav", help="where to save the spoken answer")
    parser.add_argument("--no-play", action="store_true", help="only save the spoken answer")
    args = parser.parse_args()

    http = httpx.Client(base_url=args.api, timeout=300)
    session = http.post("/api/v1/sessions", json={"language": args.language}).json()["session_id"]

    started = time.perf_counter()
    response = http.post("/api/v1/voice/query", content=to_kiosk_wav(args.wav),
                         headers={"X-Session-Id": session, "Content-Type": "audio/wav"})
    if response.status_code != 200:
        print(f"Error {response.status_code}: {response.text}")
        return 1
    body = response.json()
    print(f"\nRecognised ({time.perf_counter() - started:.1f} s): {body['transcript'] or '(nothing)'}")
    print(f"Status: {body['status']}\n\n{body['answer']}\n")
    for citation in body.get("citations", []):
        print("  ", citation["label"])

    url = body["audio"]["full_url" if args.full else "summary_url"]
    started = time.perf_counter()
    audio = http.get(url)
    if audio.status_code != 200:
        print(f"\nAudio error {audio.status_code}: {audio.text}")
        return 1
    with open(args.save, "wb") as f:
        f.write(audio.content)
    print(f"\nSpoken answer ready in {time.perf_counter() - started:.1f} s, saved to {args.save}.")
    if args.no_play:
        return 0
    print("Playing...")
    try:
        import winsound

        winsound.PlaySound(args.save, winsound.SND_FILENAME)
    except ImportError:
        print("(Open the file to listen.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
