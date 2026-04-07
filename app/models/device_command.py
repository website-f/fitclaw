from enum import Enum
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Enum as SqlEnum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


def generate_command_id() -> str:
    return f"cmd_{uuid4().hex[:12]}"


class DeviceCommandStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class DeviceCommand(Base):
    __tablename__ = "device_commands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    command_id: Mapped[str] = mapped_column(String(32), unique=True, index=True, default=generate_command_id, nullable=False)
    agent_name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    command_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="api", nullable=False)
    status: Mapped[DeviceCommandStatus] = mapped_column(
        SqlEnum(DeviceCommandStatus), default=DeviceCommandStatus.pending, index=True, nullable=False
    )
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    artifact_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    completed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)

