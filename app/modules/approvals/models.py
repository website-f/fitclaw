from __future__ import annotations

from uuid import uuid4

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


def generate_approval_id() -> str:
    return f"apr_{uuid4().hex[:16]}"


class PendingApproval(Base):
    __tablename__ = "pending_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    approval_id: Mapped[str] = mapped_column(
        String(40), unique=True, index=True, default=generate_approval_id, nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)  # claude_code, codex, etc.
    session_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False)
    action_summary: Mapped[str] = mapped_column(Text, nullable=False)
    action_detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    decided_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    __table_args__ = (
        Index("ix_pending_approvals_user_status", "user_id", "status"),
    )
