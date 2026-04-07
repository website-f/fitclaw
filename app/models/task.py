from enum import Enum
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Enum as SqlEnum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


def generate_task_id() -> str:
    return f"tsk_{uuid4().hex[:12]}"


class TaskStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    task_id: Mapped[str] = mapped_column(String(32), unique=True, index=True, default=generate_task_id, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TaskStatus] = mapped_column(SqlEnum(TaskStatus), default=TaskStatus.pending, index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="telegram", nullable=False)
    command_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    assigned_agent_name: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    user_session_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    result_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    started_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)

