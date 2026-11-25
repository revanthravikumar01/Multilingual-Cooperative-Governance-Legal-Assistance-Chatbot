"""Document ingestion pipeline (Decision 5): upload -> validate -> extract -> chunk -> embed -> store.

Files on disk (all under backend/knowledge_base/):
- uploads/<document_id>.pdf   the original PDFs        (committed to git)
- documents.json              one record per document  (committed to git)
- chroma_db/                  the vector database      (NOT committed; rebuilt from the two above)
"""

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.errors import ApiError
from app.services.embedding_service import Embedder
from app.services.vector_store import VectorStore
from app.utils.legal_chunker import chunk_pages, section_key
from app.utils.pdf_utils import PdfError, extract_pages, text_quality_warnings, validate_pdf
from app.utils.text_utils import TOPIC_KEYWORDS, slugify, topics_for


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DuplicateDocument(ApiError):
    def __init__(self, existing_id: str):
        super().__init__(409, "duplicate_document", f"This PDF was already uploaded as '{existing_id}'.")
        self.existing_id = existing_id


class DocumentNotFound(ApiError):
    def __init__(self) -> None:
        super().__init__(404, "document_not_found", "No document with this ID.")


class DocumentRegistry:
    """documents.json: a small JSON list of every uploaded document and its status."""

    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()

    def _read(self) -> list[dict]:
        if not self._path.exists():
            return []
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _write(self, records: list[dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        # ensure_ascii=False keeps Tamil titles readable in the file.
        tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)  # replace in one step so a crash never leaves half a file

    def all(self) -> list[dict]:
        with self._lock:
            return self._read()

    def get(self, document_id: str) -> dict | None:
        return next((r for r in self.all() if r["document_id"] == document_id), None)

    def find_by_hash(self, sha256: str) -> dict | None:
        return next((r for r in self.all() if r["sha256"] == sha256), None)

    def add(self, record: dict) -> None:
        with self._lock:
            records = self._read()
            records.append(record)
            self._write(records)

    def update(self, document_id: str, **changes) -> dict:
        with self._lock:
            records = self._read()
            for record in records:
                if record["document_id"] == document_id:
                    record.update(changes)
                    self._write(records)
                    return record
        raise DocumentNotFound()


class DocumentService:
    def __init__(
        self,
        registry: DocumentRegistry,
        uploads_dir: Path,
        store: VectorStore,
        embedder: Embedder,
        max_upload_mb: int = 50,
        chunk_max_chars: int = 1200,
        chunk_overlap_chars: int = 200,
    ):
        self.registry = registry
        self.uploads_dir = uploads_dir
        self.store = store
        self.embedder = embedder
        self.max_upload_bytes = max_upload_mb * 1024 * 1024
        self.chunk_max_chars = chunk_max_chars
        self.chunk_overlap_chars = chunk_overlap_chars

    # ---------- step 1: accept the upload ----------

    def register_upload(self, data: bytes, filename: str, metadata: dict) -> dict:
        """Validate and save the PDF, and record it as 'processing'. Call `process` next."""
        try:
            page_count = validate_pdf(data, self.max_upload_bytes)
        except PdfError as exc:
            raise ApiError(400, "invalid_pdf", str(exc)) from exc

        sha256 = hashlib.sha256(data).hexdigest()
        existing = self.registry.find_by_hash(sha256)
        if existing:
            raise DuplicateDocument(existing["document_id"])

        citation_name = (metadata.get("citation_name") or "").strip() or metadata["title"].strip()
        document_id = f"{slugify(citation_name)}-{sha256[:8]}"

        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        (self.uploads_dir / f"{document_id}.pdf").write_bytes(data)

        record = {
            "document_id": document_id,
            "title": metadata["title"].strip(),
            "citation_name": citation_name,
            "issuing_authority": metadata["issuing_authority"].strip(),
            "jurisdiction": metadata["jurisdiction"],
            "doc_type": metadata["doc_type"],
            "language": metadata["language"],
            "published_on": metadata.get("published_on") or None,
            "validity": metadata.get("validity") or "current",
            "filename": filename,
            "sha256": sha256,
            "status": "processing",
            "page_count": page_count,
            "chunk_count": None,
            "warnings": [],
            "error": None,
            "uploaded_at": _now(),
            "processed_at": None,
        }
        self.registry.add(record)
        return record

    # ---------- step 2: extract, chunk, embed, store ----------

    def process(self, document_id: str) -> dict:
        """Run the pipeline for one document. Never raises: failures are saved as status 'failed'."""
        record = self.registry.get(document_id)
        if record is None:
            raise DocumentNotFound()
        try:
            pages = extract_pages(str(self.uploads_dir / f"{document_id}.pdf"))
            warnings = text_quality_warnings(pages, record["language"])
            chunks = chunk_pages(pages, self.chunk_max_chars, self.chunk_overlap_chars)
            if not chunks:
                return self.registry.update(
                    document_id,
                    status="failed",
                    warnings=warnings,
                    error="No usable text could be extracted (scanned PDFs need OCR).",
                    processed_at=_now(),
                )

            ids, texts, metadatas = [], [], []
            for chunk in chunks:
                ids.append(f"{document_id}::{chunk.chunk_index}")
                texts.append(chunk.text)
                chunk_topics = set(topics_for(f"{chunk.section_title or ''} {chunk.text}"))
                metadatas.append(
                    {
                        "document_id": document_id,
                        "document_title": record["title"],
                        "citation_name": record["citation_name"],
                        "issuing_authority": record["issuing_authority"],
                        "jurisdiction": record["jurisdiction"],
                        "doc_type": record["doc_type"],
                        "doc_language": record["language"],
                        "published_on": record["published_on"],
                        "validity": record["validity"],
                        "chunk_index": chunk.chunk_index,
                        "chapter": chunk.chapter,
                        "section": chunk.section,
                        "section_key": section_key(chunk.section),
                        "section_title": chunk.section_title,
                        "subsection": chunk.subsection,
                        "page_start": chunk.page_start,
                        "page_end": chunk.page_end,
                        # One true/false flag per topic, so searches can filter by topic.
                        **{f"topic_{t}": (t in chunk_topics) for t in TOPIC_KEYWORDS},
                    }
                )

            embeddings = self.embedder.embed([c.embed_text for c in chunks])
            self.store.delete_document(document_id)  # re-processing replaces old chunks
            self.store.add(ids, texts, embeddings, metadatas)
            return self.registry.update(
                document_id,
                status="ready",
                page_count=len(pages),
                chunk_count=len(chunks),
                warnings=warnings,
                error=None,
                processed_at=_now(),
            )
        except Exception as exc:
            return self.registry.update(document_id, status="failed", error=str(exc), processed_at=_now())

    # ---------- other operations ----------

    def get(self, document_id: str) -> dict:
        record = self.registry.get(document_id)
        if record is None:
            raise DocumentNotFound()
        return record

    def list(self) -> list[dict]:
        return self.registry.all()

    def rebuild(self, on_progress=print) -> list[dict]:
        """Recreate the whole vector database from the PDFs + documents.json."""
        self.store.reset()
        results = []
        for record in self.registry.all():
            on_progress(f"Processing {record['document_id']} ...")
            result = self.process(record["document_id"])
            on_progress(f"  -> {result['status']}, {result.get('chunk_count') or 0} chunks")
            results.append(result)
        return results
