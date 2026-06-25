from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AuditEventResponse(BaseModel):
    event_id: str
    user_id: str
    actor: str | None = None
    source: str
    action: str
    summary: str
    detail: dict[str, Any] = Field(default_factory=dict)
    related_ids: list[str] = Field(default_factory=list)
    created_at: datetime


class AuditEventCreate(BaseModel):
    user_id: str
    source: str
    action: str
    summary: str
    actor: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    related_ids: list[str] = Field(default_factory=list)


class LLMUsageCreate(BaseModel):
    user_id: str
    tool: str = "chat"
    provider: str | None = None
    model: str
    session_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    note: str | None = None


class LLMUsageResponse(BaseModel):
    usage_id: str
    user_id: str
    session_id: str | None = None
    tool: str
    provider: str | None = None
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_cents: int | None = None
    currency: str
    note: str | None = None
    created_at: datetime


class UsageBreakdown(BaseModel):
    calls: int
    input_tokens: int
    output_tokens: int
    cost_cents: int


class UsageSummaryResponse(BaseModel):
    period: str
    total: UsageBreakdown
    by_tool: dict[str, UsageBreakdown] = Field(default_factory=dict)
    by_model: dict[str, UsageBreakdown] = Field(default_factory=dict)
    currency: str = "USD"


class ChatFeedbackCreate(BaseModel):
    user_id: str
    session_id: str | None = None
    message_id: int | None = None
    rating: str = Field(pattern=r"^(up|down)$")
    comment: str | None = Field(default=None, max_length=2000)
    correction: str | None = Field(default=None, max_length=4000)


class ChatFeedbackResponse(BaseModel):
    feedback_id: str
    user_id: str
    session_id: str | None = None
    message_id: int | None = None
    rating: str
    comment: str | None = None
    correction: str | None = None
    created_at: datetime


class BudgetCapCreate(BaseModel):
    user_id: str
    scope: str = "user"
    scope_value: str | None = None
    period: str = Field(default="monthly", pattern=r"^(daily|weekly|monthly)$")
    limit_cents: int = Field(ge=1)
    currency: str = "MYR"
    threshold_pct: float = Field(default=80.0, ge=1.0, le=100.0)


class BudgetCapUpdate(BaseModel):
    period: str | None = Field(default=None, pattern=r"^(daily|weekly|monthly)$")
    limit_cents: int | None = Field(default=None, ge=1)
    threshold_pct: float | None = Field(default=None, ge=1.0, le=100.0)
    active: bool | None = None


class BudgetCapResponse(BaseModel):
    budget_id: str
    user_id: str
    scope: str
    scope_value: str | None = None
    period: str
    limit_cents: int
    currency: str
    threshold_pct: float
    active: bool
    spent_cents: int = 0
    spent_pct: float = 0.0
    last_alert_pct: float | None = None
    created_at: datetime
    updated_at: datetime
