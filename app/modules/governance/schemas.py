from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class UserRoleResponse(BaseModel):
    user_id: str
    role: str
    department: str | None = None
    allowed_departments: list[str] = Field(default_factory=list)
    can_resolve_handoffs: bool = False
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class UserRoleUpsert(BaseModel):
    role: str = Field(default="staff", pattern=r"^(admin|staff|viewer)$")
    department: str | None = None
    allowed_departments: list[str] = Field(default_factory=list)
    can_resolve_handoffs: bool = False
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class HandoffOpenRequest(BaseModel):
    user_id: str
    question: str
    session_id: str | None = None
    message_id: int | None = None
    reason: str = Field(default="manual", pattern=r"^(manual|low_confidence|sensitive|keyword)$")
    department: str | None = None
    context_excerpt: str | None = None


class HandoffClaimRequest(BaseModel):
    assignee: str


class HandoffResolveRequest(BaseModel):
    assignee: str | None = None
    reply: str = Field(min_length=1, max_length=4000)


class HandoffResponse(BaseModel):
    handoff_id: str
    user_id: str
    session_id: str | None = None
    message_id: int | None = None
    reason: str
    department: str | None = None
    question: str
    context_excerpt: str | None = None
    status: str
    assignee: str | None = None
    reply: str | None = None
    created_at: datetime
    claimed_at: datetime | None = None
    resolved_at: datetime | None = None
