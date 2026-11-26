# Tamil reference voice

IndicF5 speaks Tamil in the voice of a short reference recording. Until a team voice is added, the
service uses AI4Bharat's sample voice from the model repository.

To use a team member's voice (only with their clear consent):

1. Record about 6–10 seconds of clear Tamil speech in a quiet room (any WAV format; it is converted).
2. Save it here as `tamil_reference.wav`.
3. Save the exact words spoken, in Tamil script, as `tamil_reference.txt` (UTF-8).
4. Restart the speech service. `GET http://127.0.0.1:8001/health` then shows `"tamil_voice": "team voice"`.

These two files are personal data, so git ignores them. Never clone anyone's voice without permission.
