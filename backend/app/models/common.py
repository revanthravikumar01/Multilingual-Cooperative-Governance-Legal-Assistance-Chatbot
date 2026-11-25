"""Small types shared by several models."""

from typing import Literal

# Only Tamil and English are supported in V1 (Decision 15).
Language = Literal["en", "ta"]

# How an answer turned out. Later phases set this from RAG + Gemini (Decisions 9 and 27).
AnswerStatus = Literal["answered", "insufficient_evidence", "out_of_scope"]

# Where a message came from: typed in Flutter, or spoken at the ESP32.
MessageSource = Literal["text", "voice"]
