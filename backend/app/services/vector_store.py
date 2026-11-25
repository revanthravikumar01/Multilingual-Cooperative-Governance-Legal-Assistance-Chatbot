"""ChromaDB wrapper: stores chunks + metadata on disk and finds the most similar ones.

ChromaDB runs inside this Python process and saves to knowledge_base/chroma_db/.
That folder is NOT committed to git: it can always be rebuilt from the PDFs
(`python -m app.scripts.kb rebuild`).

The collection remembers which embedding model built it. Vectors from different models
can't be compared, so after changing CIVI_EMBEDDING_MODEL the database must be rebuilt.
"""

from dataclasses import dataclass
from pathlib import Path

from app.errors import ApiError

COLLECTION = "civi_chunks"


@dataclass
class StoredChunk:
    chunk_id: str
    text: str
    metadata: dict
    similarity: float  # cosine similarity, 0 (unrelated) to 1 (same meaning)


def _clean_metadata(metadata: dict) -> dict:
    # ChromaDB only accepts str/int/float/bool values, not None.
    return {k: v for k, v in metadata.items() if v is not None}


class ModelMismatch(ApiError):
    def __init__(self, built_with: str, configured: str):
        super().__init__(
            503,
            "service_unavailable",
            f"The knowledge base was built with embedding model '{built_with}', but the settings now use "
            f"'{configured}'. Run: python -m app.scripts.kb rebuild",
        )


class VectorStore:
    def __init__(self, path: Path, embedding_model: str = "unknown"):
        import chromadb  # imported here so the rest of the app starts even if ChromaDB can't load

        path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(path))
        self.embedding_model = embedding_model
        try:
            self._collection = self._client.get_collection(COLLECTION)
        except Exception:  # not created yet (the exception type differs between ChromaDB versions)
            self._collection = self._create()
        built_with = (self._collection.metadata or {}).get("embedding_model", "unknown")
        self._mismatch = ModelMismatch(built_with, embedding_model) if built_with != embedding_model else None

    def _create(self):
        return self._client.create_collection(
            name=COLLECTION, metadata={"hnsw:space": "cosine", "embedding_model": self.embedding_model}
        )

    def _check_model(self) -> None:
        if self._mismatch and self._collection.count() > 0:
            raise self._mismatch

    def add(self, ids: list[str], texts: list[str], embeddings: list[list[float]], metadatas: list[dict]) -> None:
        self._check_model()
        batch = 1000  # ChromaDB limits how many rows one call may add
        for start in range(0, len(ids), batch):
            end = start + batch
            self._collection.upsert(
                ids=ids[start:end],
                documents=texts[start:end],
                embeddings=embeddings[start:end],
                metadatas=[_clean_metadata(m) for m in metadatas[start:end]],
            )

    def delete_document(self, document_id: str) -> None:
        self._collection.delete(where={"document_id": document_id})

    def reset(self) -> None:
        """Delete everything. The new, empty collection is tagged with the current model."""
        self._client.delete_collection(COLLECTION)
        self._collection = self._create()
        self._mismatch = None

    def count(self) -> int:
        return self._collection.count()

    def query(self, embedding: list[float], n_results: int, where: dict | None = None) -> list[StoredChunk]:
        total = self.count()
        if total == 0:
            return []
        self._check_model()
        result = self._collection.query(
            query_embeddings=[embedding],
            n_results=min(n_results, total),
            where=where or None,
            include=["documents", "metadatas", "distances"],
        )
        chunks = []
        for chunk_id, text, metadata, distance in zip(
            result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0]
        ):
            # Chroma returns cosine *distance* (1 - similarity).
            chunks.append(StoredChunk(chunk_id, text, metadata or {}, similarity=1.0 - float(distance)))
        return chunks
