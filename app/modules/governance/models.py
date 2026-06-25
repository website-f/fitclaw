from __future__ import annotations

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class UserRole(Base):
    """RBAC entry: maps a user to a role + allowed department scopes."""

    __tablename__ = "user_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="staff", nullable=False)
    department: Mapped[str | None] = mapped_column(String(60), index=True, nullable=True)
    allowed_departments: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    can_resolve_handoffs: Mapped[bool] = mapped_column(
        # Stored as JSON-bool to avoid a separate Boolean column dependency.
        Integer, default=0, nullable=False,
    )
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class HandoffRequest(Base):
    """An escalation from the AI to a human responder."""

    __tablename__ = "handoff_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    handoff_id: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    message_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    department: Mapped[str | None] = mapped_column(String(60), index=True, nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    context_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True, nullable=False)
    assignee: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    claimed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_handoff_requests_user_status", "user_id", "status"),
        Index("ix_handoff_requests_status_created", "status", "created_at"),
    )
