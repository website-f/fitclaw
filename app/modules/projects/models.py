from __future__ import annotations

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class Project(Base):
    """A code project tracked across PC + VPS for the fix-and-deploy loop."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # Git
    repo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    default_branch: Mapped[str] = mapped_column(String(120), default="main", nullable=False)
    branches: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # PC side
    agent_name: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    local_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # VPS side
    vps_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    deploy_command: Mapped[str | None] = mapped_column(Text, nullable=True)

    user_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False, default="fitclaw")
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_projects_user_slug", "user_id", "slug"),
    )
