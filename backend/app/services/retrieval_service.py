"""Finds the best evidence for a question (Decision 8).

Pipeline:
 1. Embed the question with the same model used for the documents.
 2. Ask ChromaDB for the most similar chunks, applying metadata filters
    (Tamil Nadu / Central, Act / Rules / Scheme, topic).
 3. Relevance check: drop chunks below the similarity threshold (Decision 9).
 4. Rerank: combine meaning similarity with keyword overlap, boost an exact
    "Section 34" match, and slightly prefer documents marked as current law (Decision 28).
 5. Remove near-duplicate chunks (e.g. the overlap between neighbouring chunks).
 6. Keep the top few and attach a backend-built citation to each (Decision 10).

If nothing survives step 3, `sufficient` is False and the chatbot must answer
"Verified information is not available in the current knowledge base."
"""

import logging
import re
from dataclasses import dataclass
from typing import Callable

from app.services.citation_service import build_citation
from app.services.embedding_service import Embedder
from app.services.vector_store import StoredChunk, VectorStore
from app.utils.legal_chunker import section_key
from app.utils.retry import PermanentServiceError, TemporaryServiceError
from app.utils.text_utils import jaccard, tokenize

log = logging.getLogger("civi.retrieval")

_SECTION_REF = re.compile(r"(?:section|sec\.?|rule|பிரிவு|விதி)\s*(\d{1,3}(?:-?[a-z]{1,2})?)\b", re.IGNORECASE)

# Questions naming a jurisdiction: "... in Tamil Nadu", "multi-state society".
_JURISDICTION_HINTS = {
    # Tamil forms: தமிழ்நாடு, தமிழ்நாட்டில் ("in Tamil Nadu"), தமிழகம், தமிழகத்தில்
    "tamil_nadu": re.compile(r"tamil\s*nadu|\bT\.?N\.?\b|தமிழ்\s*நா(?:டு|ட்)|தமிழக", re.IGNORECASE),
    "central": re.compile(r"multi[-\s]?state|central\s+(government|registrar)|பல\s*மாநில|மத்திய", re.IGNORECASE),
}

# Rerank weights, tuned on evaluation/questions.json (python -m app.scripts.evaluate).
W_SIMILARITY = 0.8
W_KEYWORDS = 0.2  # share of question words found in the passage
W_TITLE = 0.15  # share of question words found in the section title ("Audit", "Expulsion")
SECTION_MATCH_BOOST = 0.25  # the question names this exact section
JURISDICTION_BOOST = 0.1  # the question names this document's jurisdiction
NO_SECTION_PENALTY = 0.05  # preambles/appendices are rarely the best citation
VALIDITY_ADJUST = {"current": 0.0, "unknown": -0.02, "superseded": -0.05}
DUPLICATE_OVERLAP = 0.6  # chunks sharing more than 60% of their words count as duplicates
MAX_PER_SECTION = 2


@dataclass
class Evidence:
    chunk_id: str
    text: str
    metadata: dict
    similarity: float
    score: float
    citation: dict | None = None


@dataclass
class RetrievalResult:
    sufficient: bool
    evidence: list[Evidence]
    translated_query: str | None = None  # English version of a Tamil question, if translated
    translation_error: str | None = None  # why translation failed (search then used the Tamil text only)


_TAMIL = re.compile(r"[஀-௿]")


def _where(jurisdiction: str | None, doc_type: str | None, topic: str | None) -> dict | None:
    conditions = []
    if jurisdiction:
        conditions.append({"jurisdiction": jurisdiction})
    if doc_type:
        conditions.append({"doc_type": doc_type})
    if topic:
        conditions.append({f"topic_{topic}": True})
    if not conditions:
        return None
    return conditions[0] if len(conditions) == 1 else {"$and": conditions}


class RetrievalService:
    def __init__(
        self,
        store: VectorStore,
        embedder: Embedder,
        relevance_threshold: float = 0.35,
        candidates: int = 20,
        top_k: int = 5,
        translator: Callable[[str], str] | None = None,
        tamil_query_threshold: float = 0.6,
        default_jurisdiction: str | None = None,
    ):
        self.store = store
        self.embedder = embedder
        self.relevance_threshold = relevance_threshold
        # Untranslated Tamil text scores ~0.4–0.5 against ANY English passage, relevant or not,
        # so it needs a much stricter threshold. Real Tamil-to-Tamil-document matches score higher.
        self.tamil_query_threshold = tamil_query_threshold
        self.candidates = candidates
        self.top_k = top_k
        # Translates a Tamil question to English (Sarvam). None means "search the Tamil text only".
        self.translator = translator
        # Jurisdiction to prefer when the question names none (the kiosk serves Tamil Nadu).
        # Without it, general questions often rank the Multi-State Act above the Tamil Nadu Act.
        self.default_jurisdiction = default_jurisdiction

    def _translate(self, query: str, language: str) -> tuple[str | None, str | None]:
        """Our documents are mostly English, and the small embedding model matches Tamil questions
        to English text poorly, so Tamil questions are translated first."""
        if language != "ta" or not _TAMIL.search(query):
            return None, None
        if self.translator is None:
            return None, "Translation is not configured (no GEMINI_API_KEY or SARVAM_API_KEY)."
        try:
            return self.translator(query), None
        except (TemporaryServiceError, PermanentServiceError) as exc:
            log.warning("Tamil question translation failed, searching the Tamil text only: %s", exc)
            return None, str(exc)

    def _fetch(self, queries: list[str], filters: dict | None, section_refs: set[str]) -> dict[str, StoredChunk]:
        """Fetch relevant candidates for every query version, keeping each chunk's best similarity.

        Relevance check (Decision 9) happens here: each query version has its own threshold, and a
        chunk from a section the user named explicitly is relevant by definition."""
        candidates: dict[str, StoredChunk] = {}

        def keep(chunk: StoredChunk, threshold: float) -> None:
            named = chunk.metadata.get("section_key") in section_refs
            if not named and chunk.similarity < threshold:
                return
            if chunk.chunk_id not in candidates or chunk.similarity > candidates[chunk.chunk_id].similarity:
                candidates[chunk.chunk_id] = chunk

        for query, embedding in zip(queries, self.embedder.embed(queries)):
            threshold = self.tamil_query_threshold if _TAMIL.search(query) else self.relevance_threshold
            for chunk in self.store.query(embedding, self.candidates, where=filters):
                keep(chunk, threshold)
            # "What does section 34 say?" has little meaning to compare, so also fetch the
            # referenced section directly by its number.
            for ref in section_refs:
                section_filter = {"section_key": ref}
                where = {"$and": [filters, section_filter]} if filters else section_filter
                for chunk in self.store.query(embedding, self.candidates, where=where):
                    keep(chunk, threshold)
        return candidates

    def search(
        self,
        query: str,
        language: str = "en",
        jurisdiction: str | None = None,
        doc_type: str | None = None,
        topic: str | None = None,
    ) -> RetrievalResult:
        # 0. Tamil question -> also search with its English translation.
        translated_query, translation_error = self._translate(query, language)
        queries = [q for q in (translated_query, query) if q]

        # 1–2. Embed and fetch candidates.
        filters = _where(jurisdiction, doc_type, topic)
        section_refs = {section_key(m) for q in queries for m in _SECTION_REF.findall(q)}
        candidates = self._fetch(queries, filters, section_refs)

        # 3. (Relevance was checked in _fetch.) 4. Rerank.
        # Keyword signals use the English translation when there is one (the documents are English).
        keyword_source = [translated_query] if translated_query else queries
        query_tokens = {t for q in keyword_source for t in tokenize(q)}
        hinted = None if jurisdiction else (_jurisdiction_hint(" ".join(queries)) or self.default_jurisdiction)

        scored: list[Evidence] = []
        for chunk in candidates.values():
            section_match = chunk.metadata.get("section_key") in section_refs
            scored.append(
                Evidence(
                    chunk_id=chunk.chunk_id,
                    text=chunk.text,
                    metadata=chunk.metadata,
                    similarity=round(chunk.similarity, 4),
                    score=round(self._score(chunk, query_tokens, section_match, hinted), 4),
                )
            )

        scored.sort(key=lambda e: e.score, reverse=True)

        # 5. Remove near-duplicates and limit chunks per section.
        selected: list[Evidence] = []
        selected_tokens: list[set[str]] = []
        per_section: dict[tuple, int] = {}
        for evidence in scored:
            tokens = set(tokenize(evidence.text))
            if any(jaccard(tokens, other) > DUPLICATE_OVERLAP for other in selected_tokens):
                continue
            key = (evidence.metadata.get("document_id"), evidence.metadata.get("section"))
            if key[1] and per_section.get(key, 0) >= MAX_PER_SECTION:
                continue
            per_section[key] = per_section.get(key, 0) + 1
            selected.append(evidence)
            selected_tokens.append(tokens)
            if len(selected) == self.top_k:
                break

        # 6. Citations, numbered in the order the evidence will be shown.
        for number, evidence in enumerate(selected, start=1):
            evidence.citation = build_citation(number, evidence.metadata, language)

        return RetrievalResult(
            sufficient=bool(selected),
            evidence=selected,
            translated_query=translated_query,
            translation_error=translation_error,
        )

    @staticmethod
    def _score(chunk: StoredChunk, query_tokens: set[str], section_match: bool, hinted: str | None) -> float:
        title = chunk.metadata.get("section_title") or ""
        chunk_tokens = set(tokenize(f"{title} {chunk.text}"))
        title_tokens = set(tokenize(title))
        size = len(query_tokens) or 1
        score = (
            W_SIMILARITY * chunk.similarity
            + W_KEYWORDS * len(query_tokens & chunk_tokens) / size
            + W_TITLE * len(query_tokens & title_tokens) / size
        )
        if section_match:
            score += SECTION_MATCH_BOOST
        if hinted and chunk.metadata.get("jurisdiction") == hinted:
            score += JURISDICTION_BOOST
        if not chunk.metadata.get("section"):
            score -= NO_SECTION_PENALTY
        score += VALIDITY_ADJUST.get(chunk.metadata.get("validity", "unknown"), 0.0)
        return score


def _jurisdiction_hint(text: str) -> str | None:
    """'... in Tamil Nadu' -> tamil_nadu; 'multi-state society' -> central; both or neither -> None."""
    found = [name for name, pattern in _JURISDICTION_HINTS.items() if pattern.search(text)]
    return found[0] if len(found) == 1 else None
