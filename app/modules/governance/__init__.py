"""Governance module \u2014 user roles (RBAC) and human handoff queue.

- `user_roles`        \u2014 per-user role + department scoping (admin / staff / viewer).
- `handoff_requests`  \u2014 escalations from the chat agent to a human, with status
                        (open / claimed / resolved) and the resolver's reply.

The chat path consults `RoleService.allowed_departments` to scope RAG search
and creates `HandoffRequest` rows when low-confidence or sensitive triggers
fire. Resolution publishes the human's reply back into the conversation as
an assistant turn so the user sees a continuous thread.
"""
from fastapi import FastAPI

from app.modules.governance import models as _models  # noqa: F401
from app.modules.governance.api import router


def register(app: FastAPI) -> None:
    app.include_router(router)
