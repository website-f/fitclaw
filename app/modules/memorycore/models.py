"""SQLAlchemy models owned by the memorycore module.

These are picked up by Alembic autogenerate because app.modules.memorycore
is imported at app startup (and by alembic/env.py), so the classes register
on Base.metadata before autogenerate runs.
"""
from __future__ import annotations

from sqlalchemy import JSON, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class MemoryUsage(Base):
    """One row per LLM call we want to track token + cost for."""

    __tablename__ = "memory_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    tool: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    model: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    project_key: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True, nullable=False
    )

    __table_args__ = (
        Index("ix_memory_usage_user_created", "user_id", "created_at"),
        Index("ix_memory_usage_user_tool", "user_id", "tool"),
    )


class DesignReference(Base):
    """A frontend design reference: prompt + image paths + tags.

    Retrieved by name or by keyword/tag search. v1 stores image paths as
    strings (local paths or URLs); no image upload yet.
    """

    __tablename__ = "memory_design"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    image_paths: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    project_key: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_memory_design_user_name", "user_id", "name", unique=True),
    )
