"""Pydantic schemas for the memorycore module (usage + designs)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# --- Usage ledger ---


class UsageLogRequest(BaseModel):
    tool: Literal["claude_code", "codex", "api", "other"] = "claude_code"
    model: str
    session_id: str | None = None
    project_key: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    note: str | None = None


class UsageLogResponse(BaseModel):
    id: int
    user_id: str
    tool: str
    model: str
    session_id: str | None
    project_key: str | None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float | None
    note: str | None
    created_at: datetime


class UsageBreakdown(BaseModel):
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float
    calls: int


class UsageSummaryResponse(BaseModel):
    period: str
    range_start: datetime
    range_end: datetime
    total: UsageBreakdown
    by_tool: dict[str, UsageBreakdown]
    by_model: dict[str, UsageBreakdown]


# --- Design library ---


class DesignUpsert(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    title: str | None = None
    prompt: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    image_paths: list[str] = Field(default_factory=list)
    source_url: str | None = None
    project_key: str | None = None


class DesignResponse(BaseModel):
    id: int
    user_id: str
    name: str
    title: str | None
    prompt: str
    description: str | None
    tags: list[str]
    image_paths: list[str]
    source_url: str | None
    project_key: str | None
    created_at: datetime
    updated_at: datetime
