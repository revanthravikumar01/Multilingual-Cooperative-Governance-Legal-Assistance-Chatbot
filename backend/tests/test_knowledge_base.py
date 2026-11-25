"""End-to-end knowledge-base tests: upload -> process -> ChromaDB -> search -> citations.

These use a real ChromaDB (in a temporary folder) but a tiny fake embedder instead of the
470 MB model, so they run in seconds. They are skipped if ChromaDB cannot load on this
computer (for example when Windows Smart App Control blocks its native file).
"""

import hashlib
import math

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_document_service, get_retrieval_service, require_trusted_client
from app.services.document_service import DocumentRegistry, DocumentService
from app.services.retrieval_service import RetrievalService
from app.utils.text_utils import tokenize
from main import create_app
from tests.pdf_factory import SAMPLE_ACT_PAGES, make_pdf

API = "/api/v1"


class FakeEmbedder:
    """Bag-of-words vectors: texts sharing words get high similarity. Good enough to test the plumbing."""

    dims = 256

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vector = [0.0] * self.dims
            for token in tokenize(text):
                vector[int(hashlib.md5(token.encode()).hexdigest(), 16) % self.dims] += 1.0
            norm = math.sqrt(sum(v * v for v in vector)) or 1.0
            vectors.append([v / norm for v in vector])
        return vectors


@pytest.fixture
def store(tmp_path):
    try:
        from app.services.vector_store import VectorStore

        return VectorStore(tmp_path / "chroma_db")
    except ImportError as exc:
        pytest.skip(f"ChromaDB cannot load on this computer: {exc}")


@pytest.fixture
def kb(tmp_path, store):
    embedder = FakeEmbedder()
    documents = DocumentService(
        registry=DocumentRegistry(tmp_path / "documents.json"),
        uploads_dir=tmp_path / "uploads",
        store=store,
        embedder=embedder,
    )
    retrieval = RetrievalService(store=store, embedder=embedder, relevance_threshold=0.2, top_k=3)
    return documents, retrieval


@pytest.fixture
def kb_client(kb):
    documents, retrieval = kb
    app = create_app()
    app.dependency_overrides[get_document_service] = lambda: documents
    app.dependency_overrides[get_retrieval_service] = lambda: retrieval
    app.dependency_overrides[require_trusted_client] = lambda: None
    return TestClient(app)


UPLOAD_FORM = {
    "title": "Sample Co-operative Societies Act",
    "citation_name": "Sample Act",
    "issuing_authority": "Government of Tamil Nadu",
    "jurisdiction": "tamil_nadu",
    "doc_type": "act",
    "language": "en",
    "published_on": "1983",
}


def _upload(client, pdf_bytes=None, **overrides):
    return client.post(
        f"{API}/documents",
        data={**UPLOAD_FORM, **overrides},
        files={"file": ("sample.pdf", pdf_bytes or make_pdf(SAMPLE_ACT_PAGES), "application/pdf")},
    )


def test_upload_processes_document(kb_client, tmp_path):
    response = _upload(kb_client)
    assert response.status_code == 202
    document_id = response.json()["document_id"]
    assert document_id.startswith("sample-act-")

    # TestClient runs the background processing before returning, so it is already done.
    status = kb_client.get(f"{API}/documents/{document_id}").json()
    assert status["status"] == "ready", status
    assert status["chunk_count"] >= 4
    assert (tmp_path / "uploads" / f"{document_id}.pdf").exists()

    listing = kb_client.get(f"{API}/documents").json()
    assert listing["total_chunks"] == status["chunk_count"]


def test_duplicate_upload_rejected(kb_client):
    first = _upload(kb_client).json()["document_id"]
    response = _upload(kb_client, title="Same file, different title")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "duplicate_document"
    assert first in response.json()["error"]["message"]


def test_invalid_pdf_rejected(kb_client):
    response = _upload(kb_client, pdf_bytes=b"not a pdf")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_pdf"


def test_upload_requires_metadata(kb_client):
    response = _upload(kb_client, jurisdiction="kerala")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_search_returns_cited_evidence(kb_client):
    _upload(kb_client)
    body = kb_client.post(
        f"{API}/search", json={"query": "How many days does the Registrar have to decide a registration application?"}
    ).json()
    assert body["sufficient"] is True
    top = body["evidence"][0]
    assert "ninety days" in top["text"]
    assert top["citation"]["label"] == "[1] Sample Act, Section 3(1), Page 3"
    assert [e["citation"]["number"] for e in body["evidence"]] == list(range(1, len(body["evidence"]) + 1))


def test_search_section_reference(kb_client):
    _upload(kb_client)
    body = kb_client.post(f"{API}/search", json={"query": "What does section 4 say?"}).json()
    assert body["evidence"][0]["citation"]["section"] == "4"


def test_search_unrelated_question_is_insufficient(kb_client):
    _upload(kb_client)
    body = kb_client.post(f"{API}/search", json={"query": "Who won the cricket world cup?"}).json()
    assert body["sufficient"] is False
    assert body["evidence"] == []


def test_search_filters(kb_client):
    _upload(kb_client)
    query = {"query": "admission of members share amount"}
    assert kb_client.post(f"{API}/search", json={**query, "jurisdiction": "central"}).json()["sufficient"] is False
    assert kb_client.post(f"{API}/search", json={**query, "jurisdiction": "tamil_nadu"}).json()["sufficient"] is True
    by_topic = kb_client.post(f"{API}/search", json={**query, "topic": "membership"}).json()
    assert by_topic["sufficient"] is True
    assert all(e["citation"]["section"] == "4" for e in by_topic["evidence"])


def test_search_with_empty_knowledge_base(kb_client):
    assert kb_client.post(f"{API}/search", json={"query": "anything"}).json()["sufficient"] is False


def test_rebuild_recreates_vectors(kb):
    documents, retrieval = kb
    record = documents.register_upload(make_pdf(SAMPLE_ACT_PAGES), "a.pdf", {**UPLOAD_FORM})
    documents.process(record["document_id"])
    count = documents.store.count()

    documents.store.reset()
    assert documents.store.count() == 0
    documents.rebuild(on_progress=lambda _: None)
    assert documents.store.count() == count
    assert retrieval.search("registration application Registrar").sufficient


def test_documents_endpoints_blocked_for_other_devices(kb):
    documents, retrieval = kb
    app = create_app()
    app.dependency_overrides[get_document_service] = lambda: documents
    client = TestClient(app)  # TestClient's address is "testclient", not this laptop
    response = client.get(f"{API}/documents")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


# ---------- Tamil questions: translate to English first (Sarvam), then search ----------


def _retrieval_with_translator(kb, translator):
    documents, retrieval = kb
    documents.process(documents.register_upload(make_pdf(SAMPLE_ACT_PAGES), "a.pdf", {**UPLOAD_FORM})["document_id"])
    return RetrievalService(
        store=retrieval.store, embedder=retrieval.embedder, relevance_threshold=0.2, top_k=3, translator=translator
    )


def test_tamil_question_is_translated_before_search(kb):
    asked = []

    def fake_translate(text):
        asked.append(text)
        return "How are members admitted on payment of the share amount?"

    retrieval = _retrieval_with_translator(kb, fake_translate)
    result = retrieval.search("சங்கத்தில் உறுப்பினராக எப்படி சேர்வது?", language="ta")
    assert asked == ["சங்கத்தில் உறுப்பினராக எப்படி சேர்வது?"]
    assert result.translated_query.startswith("How are members admitted")
    assert result.sufficient
    assert result.evidence[0].citation["section"] == "4"
    assert "பிரிவு 4" in result.evidence[0].citation["label"]  # citation in the user's language


def test_english_questions_are_not_translated(kb):
    def fail_if_called(text):
        raise AssertionError("should not translate English")

    retrieval = _retrieval_with_translator(kb, fail_if_called)
    assert retrieval.search("admission of members", language="ta").translated_query is None  # no Tamil letters
    assert retrieval.search("admission of members", language="en").translated_query is None


def test_translation_failure_falls_back_to_tamil_text(kb):
    from app.utils.retry import TemporaryServiceError

    def broken(text):
        raise TemporaryServiceError("Sarvam down")

    retrieval = _retrieval_with_translator(kb, broken)
    result = retrieval.search("உறுப்பினர் சேர்க்கை", language="ta")
    assert result.translated_query is None
    assert "Sarvam down" in result.translation_error  # reported, not hidden; no crash


def test_missing_translator_is_reported(kb):
    retrieval = _retrieval_with_translator(kb, None)
    assert "not configured" in retrieval.search("உறுப்பினர் சேர்க்கை", language="ta").translation_error


# ---------- embedding model guard ----------


def test_changing_embedding_model_requires_rebuild(tmp_path):
    from app.errors import ApiError
    from app.services.vector_store import VectorStore

    try:
        old = VectorStore(tmp_path / "db", embedding_model="model-a")
    except ImportError as exc:
        pytest.skip(f"ChromaDB cannot load on this computer: {exc}")
    old.add(["x"], ["text"], [[1.0, 0.0]], [{"document_id": "d"}])

    new = VectorStore(tmp_path / "db", embedding_model="model-b")
    with pytest.raises(ApiError, match="kb rebuild"):
        new.query([1.0, 0.0], 1)

    new.reset()  # what `kb rebuild` does
    new.add(["x"], ["text"], [[0.0, 1.0, 0.0]], [{"document_id": "d"}])  # new model, new vector size
    assert new.query([0.0, 1.0, 0.0], 1)[0].chunk_id == "x"
    assert VectorStore(tmp_path / "db", embedding_model="model-b").count() == 1  # reopens without complaint
