from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


def generate_report_id() -> str:
    return f"rpt_{uuid4().hex[:12]}"


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    report_id: Mapped[str] = mapped_column(String(32), unique=True, index=True, default=generate_report_id, nullable=False)
    report_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    period_start: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

