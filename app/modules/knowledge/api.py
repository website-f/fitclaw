from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.knowledge.schemas import (
    KnowledgeAskRequest,
    KnowledgeAskResponse,
    KnowledgeDocumentResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeUpdateRequest,
    KnowledgeUploadResponse,
)
from app.modules.knowledge.service import KnowledgeService

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def _split_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


@router.post("/documents", response_model=KnowledgeUploadResponse)
async def upload_document(
    user_id: str = Form(...),
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    department: str | None = Form(default=None),
    tags: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Uploaded file is too large (max 25 MB).")

    document, chunks_indexed = KnowledgeService.ingest(
        db,
        user_id=user_id,
        filename=file.filename or "untitled",
        data=data,
        content_type=file.content_type,
        title=title,
        department=department,
        tags=_split_tags(tags),
    )
    if chunks_indexed == 0:
        raise HTTPException(
            status_code=422,
            detail=document.error or "Could not extract any text from this document.",
        )
    return KnowledgeUploadResponse(
        document=KnowledgeDocumentResponse(**KnowledgeService.serialize(document)),
        chunks_indexed=chunks_indexed,
    )


@router.get("/documents", response_model=list[KnowledgeDocumentResponse])
def list_documents(
    user_id: str = Query(...),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    documents = KnowledgeService.list_documents(db, user_id=user_id, limit=limit)
    return [KnowledgeDocumentResponse(**KnowledgeService.serialize(doc)) for doc in documents]


@router.get("/documents/{doc_id}", response_model=KnowledgeDocumentResponse)
def get_document(
    doc_id: str,
    user_id: str = Query(...),
    db: Session = Depends(get_db),
):
    document = KnowledgeService.get_document(db, user_id=user_id, doc_id=doc_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return KnowledgeDocumentResponse(**KnowledgeService.serialize(document))


@router.patch("/documents/{doc_id}", response_model=KnowledgeDocumentResponse)
def update_document(
    doc_id: str,
    payload: KnowledgeUpdateRequest,
    user_id: str = Query(...),
    db: Session = Depends(get_db),
):
    document = KnowledgeService.update_document(
        db,
        user_id=user_id,
        doc_id=doc_id,
        title=payload.title,
        department=payload.department,
        tags=payload.tags,
        summary=payload.summary,
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return KnowledgeDocumentResponse(**KnowledgeService.serialize(document))


@router.delete("/documents/{doc_id}")
def delete_document(
    doc_id: str,
    user_id: str = Query(...),
    db: Session = Depends(get_db),
):
    deleted = KnowledgeService.delete_document(db, user_id=user_id, doc_id=doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"deleted": True, "doc_id": doc_id}


@router.post("/search", response_model=KnowledgeSearchResponse)
def search(payload: KnowledgeSearchRequest, db: Session = Depends(get_db)):
    hits = KnowledgeService.search(
        db,
        user_id=payload.user_id,
        query=payload.query,
        limit=payload.limit,
        department=payload.department,
    )
    return KnowledgeSearchResponse(query=payload.query, hits=hits)


@router.post("/ask", response_model=KnowledgeAskResponse)
def ask(payload: KnowledgeAskRequest, db: Session = Depends(get_db)):
    return KnowledgeService.ask(
        db,
        user_id=payload.user_id,
        question=payload.question,
        limit=payload.limit,
        department=payload.department,
    )
