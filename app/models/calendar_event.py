from enum import Enum
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Enum as SqlEnum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


def generate_event_id() -> str:
    return f"evt_{uuid4().hex[:12]}"


class CalendarEventStatus(str, Enum):
    scheduled = "scheduled"
    cancelled = "cancelled"
    completed = "completed"


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_id: Mapped[str] = mapped_column(String(32), unique=True, index=True, default=generate_event_id, nullable=False)
    platform_user_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    user_session_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="chat", nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[CalendarEventStatus] = mapped_column(
        SqlEnum(CalendarEventStatus),
        default=CalendarEventStatus.scheduled,
        index=True,
        nullable=False,
    )
    starts_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ends_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="UTC")
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meeting_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attendees_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    reminder_minutes_before: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    reminder_sent_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ics_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
