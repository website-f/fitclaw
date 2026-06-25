from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class KnowledgeDocumentResponse(BaseModel):
    doc_id: str
    user_id: str
    title: str
    source: str | None = None
    kind: str
    department: str | None = None
    tags: list[str] = Field(default_factory=list)
    status: str
    chunk_count: int
    char_count: int
    summary: str | None = None
    error: str | None = None
    uploaded_at: datetime
    indexed_at: datetime | None = None


class KnowledgeUploadResponse(BaseModel):
    document: KnowledgeDocumentResponse
    chunks_indexed: int


class KnowledgeSearchRequest(BaseModel):
    user_id: str
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=20)
    department: str | None = None


class KnowledgeSearchHit(BaseModel):
    doc_id: str
    title: str
    source: str | None
    chunk_index: int
    text: str
    score: float
    department: str | None = None
    tags: list[str] = Field(default_factory=list)


class KnowledgeSearchResponse(BaseModel):
    query: str
    hits: list[KnowledgeSearchHit]


class KnowledgeAskRequest(BaseModel):
    user_id: str
    question: str = Field(min_length=1, max_length=4000)
    limit: int = Field(default=4, ge=1, le=10)
    department: str | None = None


class KnowledgeCitation(BaseModel):
    doc_id: str
    title: str
    chunk_index: int
    source: str | None = None


class KnowledgeAskResponse(BaseModel):
    answer: str
    citations: list[KnowledgeCitation]
    provider: str | None = None
    used_context: list[KnowledgeSearchHit] = Field(default_factory=list)


class KnowledgeUpdateRequest(BaseModel):
    title: str | None = None
    department: str | None = None
    tags: list[str] | None = None
    summary: str | None = None
