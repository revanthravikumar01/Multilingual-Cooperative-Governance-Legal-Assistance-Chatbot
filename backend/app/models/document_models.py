"""Shapes for document upload/status and the knowledge-base search endpoint."""

from typing import Literal

from pydantic import BaseModel, Field

from app.models.chat_models import Citation
from app.models.common import Language

Jurisdiction = Literal["tamil_nadu", "central"]
DocType = Literal["act", "rules", "scheme", "guideline", "circular", "other"]
# Decision 28: legal status is set by the uploader. Never guessed from the upload date.
Validity = Literal["current", "superseded", "unknown"]
DocumentStatus = Literal["processing", "ready", "failed"]
Topic = Literal["registration", "membership", "elections", "governance", "auditing", "schemes"]


class DocumentOut(BaseModel):
    document_id: str
    title: str
    citation_name: str
    issuing_authority: str
    jurisdiction: Jurisdiction
    doc_type: DocType
    language: Language
    published_on: str | None
    validity: Validity
    filename: str
    sha256: str
    status: DocumentStatus
    page_count: int | None = None
    chunk_count: int | None = None
    warnings: list[str] = []
    error: str | None = None
    uploaded_at: str
    processed_at: str | None = None


class DocumentListOut(BaseModel):
    documents: list[DocumentOut]
    total_chunks: int


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    language: Language = "en"
    jurisdiction: Jurisdiction | None = None
    doc_type: DocType | None = None
    topic: Topic | None = None


class EvidenceOut(BaseModel):
    chunk_id: str
    text: str
    score: float  # final rerank score (used for ordering)
    similarity: float  # raw semantic similarity (used for the relevance threshold)
    citation: Citation


class SearchResponse(BaseModel):
    sufficient: bool  # False means "Verified information is not available" (Decision 9)
    evidence: list[EvidenceOut]
    translated_query: str | None = None  # English translation used for a Tamil question
    translation_error: str | None = None  # set when translation failed (Tamil text searched alone)
