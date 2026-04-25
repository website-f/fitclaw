from __future__ import annotations

from sqlalchemy import JSON, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class RoutingDecision(Base):
    """Audit row — every classification we make, with what we did about it.

    Lets you build "did the router get it right?" dashboards, train
    a better classifier from labeled data, or refund a misroute later.
    """

    __tablename__ = "routing_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(40), index=True, nullable=False)  # telegram, whatsapp, api, etc.
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    params: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    dispatched: Mapped[bool] = mapped_column(default=False, nullable=False)
    dispatch_action: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_routing_decisions_user_created", "user_id", "created_at"),
    )
