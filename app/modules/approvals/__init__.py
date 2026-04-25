"""Approvals module — Telegram-gated human-in-the-loop for risky agent actions.

Flow:
1. Agent's PreToolUse hook detects a risky action → POSTs to /api/v1/approvals.
2. Server creates a row (status=pending), sends a Telegram message with
   "Approve / Deny" inline keyboard.
3. Agent polls GET /api/v1/approvals/{approval_id} every ~2s (up to 5 min).
4. User taps button. Telegram callback → /api/v1/approvals/{id}/decide.
5. Agent's next poll sees status=approved|denied → exits 0 or 2.
"""
from fastapi import FastAPI

from app.modules.approvals import models as _models  # noqa: F401
from app.modules.approvals.api import router


def register(app: FastAPI) -> None:
    app.include_router(router)
