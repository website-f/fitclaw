"""KnowledgeService — ingestion, search, and RAG-augmented Q&A."""
from __future__ import annotations

import secrets
from datetime import timezone
from typing import Any

from sqlalchemy import delete as sa_delete, select
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.modules.knowledge import chunker as _chunker
from app.modules.knowledge import embedder as _embedder
from app.modules.knowledge import extractor as _extractor
from app.modules.knowledge.models import KnowledgeChunk, KnowledgeDocument
from app.modules.knowledge.schemas import (
    KnowledgeAskResponse,
    KnowledgeCitation,
    KnowledgeSearchHit,
)
from app.services.llm_service import LLMService, LLMServiceError


def _make_doc_id() -> str:
    return f"kd_{secrets.token_hex(6)}"


class KnowledgeService:
    @staticmethod
    def ingest(
        db: Session,
        *,
        user_id: str,
        filename: str,
        data: bytes,
        content_type: str | None,
        title: str | None = None,
        department: str | None = None,
        tags: list[str] | None = None,
    ) -> tuple[KnowledgeDocument, int]:
        kind = _extractor.detect_kind(filename, content_type)
        try:
            text = _extractor.extract_text(data=data, kind=kind, filename=filename)
        except Exception as exc:  # pragma: no cover - defensive
            text = ""
            extract_error: str | None = f"extract failed: {exc}"
        else:
            extract_error = None

        normalized_title = (title or _extractor.derive_title(filename)).strip()
        chunks = _chunker.chunk_text(text) if text else []
        char_count = sum(len(chunk) for chunk in chunks)

        doc = KnowledgeDocument(
            doc_id=_make_doc_id(),
            user_id=user_id,
            title=normalized_title,
            source=filename,
            kind=kind,
            department=(department or None),
            tags=list(tags or []),
            status="indexed" if chunks else "empty",
            chunk_count=len(chunks),
            char_count=char_count,
            error=extract_error if not chunks else None,
            uploaded_at=utcnow(),
            indexed_at=utcnow() if chunks else None,
        )
        db.add(doc)
        db.flush()

        chunk_rows = [
            KnowledgeChunk(
                doc_id=doc.doc_id,
                user_id=user_id,
                chunk_index=index,
                text=chunk,
                token_estimate=_chunker.estimate_tokens(chunk),
                embedding=_embedder.embed(chunk),
                keywords=_embedder.keywords(chunk),
                created_at=utcnow(),
            )
            for index, chunk in enumerate(chunks)
        ]
        if chunk_rows:
            db.add_all(chunk_rows)
        db.commit()
        db.refresh(doc)
        try:
            from app.modules.audit.service import AuditService
            AuditService.log(
                db,
                user_id=user_id,
                source="knowledge",
                action="knowledge.ingest",
                summary=f"Indexed {doc.title} ({len(chunk_rows)} chunks)",
                detail={
                    "doc_id": doc.doc_id,
                    "kind": doc.kind,
                    "department": doc.department,
                    "chunk_count": len(chunk_rows),
                    "char_count": char_count,
                },
                related_ids=[doc.doc_id],
            )
        except Exception:
            pass
        return doc, len(chunk_rows)

    @staticmethod
    def list_documents(db: Session, *, user_id: str, limit: int = 50) -> list[KnowledgeDocument]:
        stmt = (
            select(KnowledgeDocument)
            .where(KnowledgeDocument.user_id == user_id)
            .order_by(KnowledgeDocument.uploaded_at.desc())
            .limit(limit)
        )
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def get_document(db: Session, *, user_id: str, doc_id: str) -> KnowledgeDocument | None:
        stmt = select(KnowledgeDocument).where(
            KnowledgeDocument.user_id == user_id, KnowledgeDocument.doc_id == doc_id
        )
        return db.execute(stmt).scalar_one_or_none()

    @staticmethod
    def delete_document(db: Session, *, user_id: str, doc_id: str) -> bool:
        doc = KnowledgeService.get_document(db, user_id=user_id, doc_id=doc_id)
        if doc is None:
            return False
        db.execute(sa_delete(KnowledgeChunk).where(KnowledgeChunk.doc_id == doc.doc_id))
        db.delete(doc)
        db.commit()
        return True

    @staticmethod
    def update_document(
        db: Session,
        *,
        user_id: str,
        doc_id: str,
        title: str | None = None,
        department: str | None = None,
        tags: list[str] | None = None,
        summary: str | None = None,
    ) -> KnowledgeDocument | None:
        doc = KnowledgeService.get_document(db, user_id=user_id, doc_id=doc_id)
        if doc is None:
            return None
        if title is not None:
            doc.title = title.strip() or doc.title
        if department is not None:
            doc.department = department.strip() or None
        if tags is not None:
            doc.tags = list(tags)
        if summary is not None:
            doc.summary = summary.strip() or None
        db.commit()
        db.refresh(doc)
        return doc

    @staticmethod
    def search(
        db: Session,
        *,
        user_id: str,
        query: str,
        limit: int = 5,
        department: str | None = None,
    ) -> list[KnowledgeSearchHit]:
        cleaned = (query or "").strip()
        if not cleaned:
            return []

        chunk_stmt = (
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeDocument.doc_id == KnowledgeChunk.doc_id)
            .where(KnowledgeDocument.user_id == user_id)
        )
        if department:
            chunk_stmt = chunk_stmt.where(KnowledgeDocument.department == department)
        else:
            try:
                from app.modules.governance.service import RoleService
                allowed = RoleService.allowed_departments(db, user_id)
            except Exception:
                allowed = None
            if allowed is not None:
                if not allowed:
                    return []
                chunk_stmt = chunk_stmt.where(KnowledgeDocument.department.in_(allowed))

        query_embedding = _embedder.embed(cleaned)
        query_keywords = set(_embedder.keywords(cleaned, limit=12))

        scored: list[tuple[float, KnowledgeChunk, KnowledgeDocument]] = []
        for chunk, document in db.execute(chunk_stmt).all():
            if not chunk.embedding:
                continue
            similarity = _embedder.cosine(query_embedding, chunk.embedding)
            chunk_keywords = set(chunk.keywords or [])
            keyword_overlap = len(query_keywords & chunk_keywords) / max(1, len(query_keywords))
            score = (similarity * 0.7) + (keyword_overlap * 0.3)
            if score <= 0:
                continue
            scored.append((score, chunk, document))

        scored.sort(key=lambda item: item[0], reverse=True)
        hits: list[KnowledgeSearchHit] = []
        for score, chunk, document in scored[:limit]:
            hits.append(
                KnowledgeSearchHit(
                    doc_id=document.doc_id,
                    title=document.title,
                    source=document.source,
                    chunk_index=chunk.chunk_index,
                    text=chunk.text,
                    score=round(score, 4),
                    department=document.department,
                    tags=list(document.tags or []),
                )
            )
        return hits

    @staticmethod
    def ask(
        db: Session,
        *,
        user_id: str,
        question: str,
        limit: int = 4,
        department: str | None = None,
    ) -> KnowledgeAskResponse:
        hits = KnowledgeService.search(
            db, user_id=user_id, query=question, limit=limit, department=department
        )
        if not hits:
            return KnowledgeAskResponse(
                answer="I could not find anything in the knowledge base for that question yet.",
                citations=[],
                provider="knowledge",
                used_context=[],
            )

        context_blocks = []
        for hit in hits:
            tag = f"[KB:{hit.doc_id}#{hit.chunk_index}]"
            context_blocks.append(f"{tag}\n{hit.text.strip()}")
        context_text = "\n\n".join(context_blocks)

        system_prompt = (
            "You are answering using only the knowledge-base excerpts provided. "
            "Cite the source of every claim by repeating the exact marker like [KB:doc-id#chunk-idx] inline. "
            "If the excerpts do not answer the question, say so plainly — do not invent."
        )
        user_prompt = (
            f"Question:\n{question.strip()}\n\n"
            f"Knowledge excerpts:\n{context_text}\n\n"
            "Answer concisely with inline [KB:...] markers."
        )

        try:
            reply, provider = LLMService.generate_reply(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
            )
            answer = (reply or "").strip() or "No answer produced."
        except LLMServiceError as exc:
            # Graceful fallback so the API is still useful when the LLM is down.
            answer = (
                "LLM unavailable, returning the top excerpt verbatim:\n\n" + hits[0].text.strip()
            )
            provider = f"fallback: {exc}"

        citations = [
            KnowledgeCitation(
                doc_id=hit.doc_id,
                title=hit.title,
                chunk_index=hit.chunk_index,
                source=hit.source,
            )
            for hit in hits
        ]
        return KnowledgeAskResponse(
            answer=answer,
            citations=citations,
            provider=provider,
            used_context=hits,
        )

    @staticmethod
    def serialize(document: KnowledgeDocument) -> dict[str, Any]:
        uploaded_at = document.uploaded_at
        if uploaded_at and uploaded_at.tzinfo is None:
            uploaded_at = uploaded_at.replace(tzinfo=timezone.utc)
        indexed_at = document.indexed_at
        if indexed_at and indexed_at.tzinfo is None:
            indexed_at = indexed_at.replace(tzinfo=timezone.utc)
        return {
            "doc_id": document.doc_id,
            "user_id": document.user_id,
            "title": document.title,
            "source": document.source,
            "kind": document.kind,
            "department": document.department,
            "tags": list(document.tags or []),
            "status": document.status,
            "chunk_count": document.chunk_count,
            "char_count": document.char_count,
            "summary": document.summary,
            "error": document.error,
            "uploaded_at": uploaded_at,
            "indexed_at": indexed_at,
        }
