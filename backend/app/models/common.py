"""Small types shared by several models."""

from typing import Literal

# Only Tamil and English are supported in V1 (Decision 15).
Language = Literal["en", "ta"]

# How an answer turned out (Decisions 9 and 27). "stt_failed": a voice question could not be
# recognised, and the message asks the user to repeat it (Decision 17).
AnswerStatus = Literal["answered", "insufficient_evidence", "out_of_scope", "stt_failed"]

# Where a message came from: typed in Flutter, or spoken at the ESP32.
MessageSource = Literal["text", "voice"]
