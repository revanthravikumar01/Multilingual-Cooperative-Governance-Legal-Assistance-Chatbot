"""Turns text into embeddings (lists of numbers that capture meaning), as in Decision 6.

The same model is used for document chunks and for user questions, so they can be compared.
The model (~470 MB) downloads once from Hugging Face on first use and is cached on the laptop.
"""

import threading
from typing import Protocol

MAX_TOKENS = 512


class Embedder(Protocol):
    """Anything with this method can be used as the embedder (tests use a tiny fake one)."""

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        # Loaded lazily: importing torch and the model takes several seconds,
        # so the server starts fast and only pays this cost on the first search/upload.
        with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer

                try:
                    # Use the downloaded copy without contacting Hugging Face. On a slow or
                    # unstable connection the online "is there an update?" checks can hang for minutes.
                    model = SentenceTransformer(self.model_name, device="cpu", local_files_only=True)
                except Exception:
                    # Not downloaded yet: fetch it (or run python -m app.scripts.download_model first).
                    model = SentenceTransformer(self.model_name, device="cpu")
                # Read up to 512 tokens per passage: enough for a whole ~1200-character chunk.
                # (Models with a smaller limit, like MiniLM's 128, keep their own limit.)
                model.max_seq_length = min(model.max_seq_length or MAX_TOKENS, MAX_TOKENS)
                self._model = model
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load()
        # normalize_embeddings=True makes cosine similarity a simple dot product.
        vectors = model.encode(texts, batch_size=16, normalize_embeddings=True, show_progress_bar=False)
        return vectors.tolist()
