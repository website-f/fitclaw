"""Knowledge module — Retrieval-Augmented Generation (RAG).

Owns:
- `knowledge_documents` rows (uploaded SOPs, FAQs, catalogues, etc).
- `knowledge_chunks` rows (chunked + embedded segments used for search).
- `/api/v1/knowledge/*` HTTP surface.

The chat path queries `KnowledgeService.search` and the top chunks are
injected into the system prompt so replies can cite them inline.
"""
from fastapi import FastAPI

from app.modules.knowledge import models as _models  # noqa: F401
from app.modules.knowledge.api import router


def register(app: FastAPI) -> None:
    app.include_router(router)
