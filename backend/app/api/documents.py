"""Knowledge-base endpoints: upload PDFs, check their status, and test searches.

All of these are admin tools, limited to this laptop (Decision 30).
The easiest way to use them is the browser page http://127.0.0.1:8000/docs
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile

from app.dependencies import get_document_service, get_retrieval_service, require_trusted_client
from app.models.document_models import (
    DocType,
    DocumentListOut,
    DocumentOut,
    Jurisdiction,
    SearchRequest,
    SearchResponse,
    Validity,
)
from app.models.common import Language

router = APIRouter(tags=["knowledge base"], dependencies=[Depends(require_trusted_client)])

DatePattern = r"^\d{4}(-\d{2}(-\d{2})?)?$"  # 1983, 1983-05 or 1983-05-21


@router.post("/documents", status_code=202, response_model=DocumentOut)
async def upload_document(
    background: BackgroundTasks,
    file: Annotated[UploadFile, File(description="Official PDF")],
    title: Annotated[str, Form(min_length=3, max_length=300)],
    issuing_authority: Annotated[str, Form(min_length=2, max_length=200)],
    jurisdiction: Annotated[Jurisdiction, Form()],
    doc_type: Annotated[DocType, Form()],
    language: Annotated[Language, Form()],
    citation_name: Annotated[str | None, Form(max_length=120, description="Short name for citations")] = None,
    published_on: Annotated[str | None, Form(pattern=DatePattern)] = None,
    validity: Annotated[Validity, Form()] = "current",
    service=Depends(get_document_service),
) -> DocumentOut:
    data = await file.read()
    record = service.register_upload(
        data,
        file.filename or "upload.pdf",
        {
            "title": title,
            "citation_name": citation_name,
            "issuing_authority": issuing_authority,
            "jurisdiction": jurisdiction,
            "doc_type": doc_type,
            "language": language,
            "published_on": published_on,
            "validity": validity,
        },
    )
    # Processing (text extraction + embeddings) runs after the reply is sent.
    # Check progress with GET /documents/{document_id}.
    background.add_task(service.process, record["document_id"])
    return DocumentOut(**record)


@router.get("/documents", response_model=DocumentListOut)
def list_documents(service=Depends(get_document_service)) -> DocumentListOut:
    return DocumentListOut(
        documents=[DocumentOut(**r) for r in service.list()],
        total_chunks=service.store.count(),
    )


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: str, service=Depends(get_document_service)) -> DocumentOut:
    return DocumentOut(**service.get(document_id))


@router.post("/search", response_model=SearchResponse)
def search_knowledge_base(request: SearchRequest, retrieval=Depends(get_retrieval_service)) -> SearchResponse:
    """See exactly which evidence the chatbot would use for a question (for testing and tuning)."""
    result = retrieval.search(
        request.query,
        language=request.language,
        jurisdiction=request.jurisdiction,
        doc_type=request.doc_type,
        topic=request.topic,
    )
    return SearchResponse(
        sufficient=result.sufficient,
        evidence=[
            {
                "chunk_id": e.chunk_id,
                "text": e.text,
                "score": e.score,
                "similarity": e.similarity,
                "citation": e.citation,
            }
            for e in result.evidence
        ],
        translated_query=result.translated_query,
        translation_error=result.translation_error,
    )
