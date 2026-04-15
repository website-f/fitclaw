from __future__ import annotations

from enum import Enum

from sqlalchemy import JSON, Boolean, DateTime, Enum as SqlEnum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class FinanceRuleKind(str, Enum):
    category_keyword = "category_keyword"
    threshold = "threshold"


class FinanceEntry(Base):
    __tablename__ = "finance_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    entry_id: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    platform_user_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    source: Mapped[str] = mapped_column(String(40), default="receipt", nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    merchant_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    currency: Mapped[str] = mapped_column(String(12), default="MYR", nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(80), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class FinanceRule(Base):
    __tablename__ = "finance_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    rule_id: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    platform_user_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[FinanceRuleKind] = mapped_column(SqlEnum(FinanceRuleKind), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criteria_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    action_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
