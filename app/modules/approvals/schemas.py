from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ApprovalCreate(BaseModel):
    source: str = "claude_code"
    session_id: str | None = None
    tool_name: str
    action_summary: str = Field(..., description="Human-readable one-liner shown in Telegram.")
    action_detail: dict[str, Any] = Field(default_factory=dict)


class ApprovalResponse(BaseModel):
    approval_id: str
    user_id: str
    source: str
    session_id: str | None
    tool_name: str
    action_summary: str
    action_detail: dict[str, Any]
    status: Literal["pending", "approved", "denied", "timeout"]
    created_at: datetime
    decided_at: datetime | None
    decided_by: str | None


class ApprovalDecision(BaseModel):
    approved: bool
    decided_by: str | None = None
