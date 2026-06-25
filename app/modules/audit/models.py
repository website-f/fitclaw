from __future__ import annotations

from sqlalchemy import JSON, Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class AuditEvent(Base):
    """Generic action log row used by every governance-relevant operation."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_id: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    actor: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    related_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_audit_events_user_created", "user_id", "created_at"),
        Index("ix_audit_events_action", "action"),
    )


class LLMUsageEvent(Base):
    """Token + cost ledger for every LLM call we can attribute."""

    __tablename__ = "llm_usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    usage_id: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    tool: Mapped[str] = mapped_column(String(40), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(60), nullable=True)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_llm_usage_user_created", "user_id", "created_at"),
        Index("ix_llm_usage_user_model", "user_id", "model"),
    )


class ChatFeedback(Base):
    """\U0001f44d / \U0001f44e rating per assistant message, with optional comment."""

    __tablename__ = "chat_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    feedback_id: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    message_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    rating: Mapped[str] = mapped_column(String(8), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    correction: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_chat_feedback_user_created", "user_id", "created_at"),
    )


class BudgetCap(Base):
    """Spend limit per user (or scope) with optional alert threshold."""

    __tablename__ = "budget_caps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    budget_id: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    scope: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    scope_value: Mapped[str | None] = mapped_column(String(120), nullable=True)
    period: Mapped[str] = mapped_column(String(20), default="monthly", nullable=False)
    limit_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="MYR", nullable=False)
    threshold_pct: Mapped[float] = mapped_column(Float, default=80.0, nullable=False)
    last_alert_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_budget_caps_user_active", "user_id", "active"),
    )
