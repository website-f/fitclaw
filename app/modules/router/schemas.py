from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# The fixed list of categories the classifier may choose from.
# To add a category: add it here, add a one-line description in the prompt,
# and (optionally) add a dispatcher in the caller. No DB changes needed.
RouteCategory = Literal[
    "fix",        # "the button on X is broken" → dispatch /fix
    "push",       # "push my changes on X to dev" → dispatch /push
    "deploy",     # "deploy X to prod" → dispatch /deploy
    "query",      # "what's my RAM" / "show today usage" → readonly action
    "finance",    # receipt or "paid X for Y" → finance module (stub)
    "crm",        # "new lead from John" → crm module (stub)
    "calendar",   # "book Friday 3pm with X" → calendar service
    "task",       # "remind me to X" → task service
    "chat",       # fallback — pass to general chat LLM
]


class RouteIntent(BaseModel):
    category: RouteCategory
    confidence: float = Field(..., ge=0.0, le=1.0)
    params: dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""


class ClassifyRequest(BaseModel):
    text: str
    source: str = "api"


class ClassifyResponse(BaseModel):
    intent: RouteIntent
    decision_id: int
    created_at: datetime
