"""Audit module — governance layer for the platform.

Bundles four related concerns so the cross-cutting "what happened, who
paid for it, and was it useful" story stays in one place:

- `audit_events`     — generic action log (every chat turn, ingestion,
                       approval decision, finance entry, etc).
- `llm_usage_events` — token + cost ledger per LLM call. Replaces the
                       removed memorycore ledger with a leaner shape.
- `chat_feedback`    — \U0001f44d / \U0001f44e ratings per assistant message.
- `budget_caps`      — per-user spend limits with threshold alerts.
"""
from fastapi import FastAPI

from app.modules.audit import models as _models  # noqa: F401
from app.modules.audit.api import router


def register(app: FastAPI) -> None:
    app.include_router(router)
