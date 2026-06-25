"""Service layer for audit, usage ledger, feedback, and budgets."""
from __future__ import annotations

import secrets
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.modules.audit import pricing
from app.modules.audit.models import AuditEvent, BudgetCap, ChatFeedback, LLMUsageEvent
from app.modules.audit.schemas import UsageBreakdown


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


def _period_start(period: str) -> datetime:
    now = datetime.now(timezone.utc)
    base = now.replace(hour=0, minute=0, second=0, microsecond=0)
    period = (period or "today").lower()
    if period == "today":
        return base
    if period == "week":
        return base - timedelta(days=base.weekday())
    if period == "month":
        return base.replace(day=1)
    if period == "daily":
        return base
    if period == "weekly":
        return base - timedelta(days=base.weekday())
    if period == "monthly":
        return base.replace(day=1)
    return base


class AuditService:
    @staticmethod
    def log(
        db: Session,
        *,
        user_id: str,
        source: str,
        action: str,
        summary: str,
        actor: str | None = None,
        detail: dict[str, Any] | None = None,
        related_ids: list[str] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_id=_new_id("ae"),
            user_id=user_id,
            actor=actor,
            source=source,
            action=action,
            summary=summary[:1000],
            detail=detail or {},
            related_ids=list(related_ids or []),
            created_at=utcnow(),
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event

    @staticmethod
    def list_events(
        db: Session,
        *,
        user_id: str,
        action: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.user_id == user_id)
            .order_by(AuditEvent.created_at.desc())
            .limit(limit)
        )
        if action:
            stmt = stmt.where(AuditEvent.action == action)
        return list(db.execute(stmt).scalars().all())


class UsageService:
    @staticmethod
    def log(
        db: Session,
        *,
        user_id: str,
        model: str,
        tool: str = "chat",
        provider: str | None = None,
        session_id: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        note: str | None = None,
    ) -> LLMUsageEvent:
        cost_cents = pricing.cost_cents(model, input_tokens, output_tokens)
        row = LLMUsageEvent(
            usage_id=_new_id("lu"),
            user_id=user_id,
            session_id=session_id,
            tool=tool,
            provider=provider,
            model=model or "unknown",
            input_tokens=max(0, int(input_tokens or 0)),
            output_tokens=max(0, int(output_tokens or 0)),
            cache_read_tokens=max(0, int(cache_read_tokens or 0)),
            cache_write_tokens=max(0, int(cache_write_tokens or 0)),
            cost_cents=cost_cents,
            currency="USD",
            note=(note or None),
            created_at=utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def summary(db: Session, *, user_id: str, period: str = "today") -> dict[str, Any]:
        start = _period_start(period)
        stmt = (
            select(LLMUsageEvent)
            .where(LLMUsageEvent.user_id == user_id)
            .where(LLMUsageEvent.created_at >= start)
        )
        rows = list(db.execute(stmt).scalars().all())

        total_calls = len(rows)
        total_in = sum(r.input_tokens for r in rows)
        total_out = sum(r.output_tokens for r in rows)
        total_cost = sum((r.cost_cents or 0) for r in rows)

        by_tool: dict[str, dict[str, int]] = defaultdict(lambda: {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_cents": 0})
        by_model: dict[str, dict[str, int]] = defaultdict(lambda: {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_cents": 0})
        for row in rows:
            for bucket, key in ((by_tool, row.tool), (by_model, row.model)):
                bucket[key]["calls"] += 1
                bucket[key]["input_tokens"] += row.input_tokens
                bucket[key]["output_tokens"] += row.output_tokens
                bucket[key]["cost_cents"] += row.cost_cents or 0
        return {
            "period": period,
            "total": UsageBreakdown(
                calls=total_calls, input_tokens=total_in, output_tokens=total_out, cost_cents=total_cost
            ).model_dump(),
            "by_tool": {k: UsageBreakdown(**v).model_dump() for k, v in by_tool.items()},
            "by_model": {k: UsageBreakdown(**v).model_dump() for k, v in by_model.items()},
            "currency": "USD",
        }

    @staticmethod
    def spent_in_period(db: Session, *, user_id: str, period: str) -> int:
        start = _period_start(period)
        stmt = (
            select(LLMUsageEvent.cost_cents)
            .where(LLMUsageEvent.user_id == user_id)
            .where(LLMUsageEvent.created_at >= start)
        )
        return sum(int(row or 0) for row in db.execute(stmt).scalars().all())


class FeedbackService:
    @staticmethod
    def record(
        db: Session,
        *,
        user_id: str,
        rating: str,
        session_id: str | None = None,
        message_id: int | None = None,
        comment: str | None = None,
        correction: str | None = None,
    ) -> ChatFeedback:
        row = ChatFeedback(
            feedback_id=_new_id("fb"),
            user_id=user_id,
            session_id=session_id,
            message_id=message_id,
            rating=rating,
            comment=(comment or None),
            correction=(correction or None),
            created_at=utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def list(db: Session, *, user_id: str, limit: int = 100) -> list[ChatFeedback]:
        stmt = (
            select(ChatFeedback)
            .where(ChatFeedback.user_id == user_id)
            .order_by(ChatFeedback.created_at.desc())
            .limit(limit)
        )
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def trends(db: Session, *, user_id: str, days: int = 7) -> dict[str, int]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(ChatFeedback)
            .where(ChatFeedback.user_id == user_id, ChatFeedback.created_at >= since)
        )
        rows = list(db.execute(stmt).scalars().all())
        return {
            "window_days": days,
            "total": len(rows),
            "up": sum(1 for r in rows if r.rating == "up"),
            "down": sum(1 for r in rows if r.rating == "down"),
            "corrections": sum(1 for r in rows if (r.correction or "").strip()),
        }


class BudgetService:
    @staticmethod
    def create(
        db: Session,
        *,
        user_id: str,
        limit_cents: int,
        scope: str = "user",
        scope_value: str | None = None,
        period: str = "monthly",
        currency: str = "MYR",
        threshold_pct: float = 80.0,
    ) -> BudgetCap:
        row = BudgetCap(
            budget_id=_new_id("bg"),
            user_id=user_id,
            scope=scope,
            scope_value=scope_value,
            period=period,
            limit_cents=limit_cents,
            currency=currency,
            threshold_pct=threshold_pct,
            active=True,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def update(
        db: Session,
        *,
        user_id: str,
        budget_id: str,
        period: str | None = None,
        limit_cents: int | None = None,
        threshold_pct: float | None = None,
        active: bool | None = None,
    ) -> BudgetCap | None:
        row = db.execute(
            select(BudgetCap).where(BudgetCap.user_id == user_id, BudgetCap.budget_id == budget_id)
        ).scalar_one_or_none()
        if row is None:
            return None
        if period is not None:
            row.period = period
        if limit_cents is not None:
            row.limit_cents = limit_cents
        if threshold_pct is not None:
            row.threshold_pct = threshold_pct
        if active is not None:
            row.active = active
        row.updated_at = utcnow()
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def list(db: Session, *, user_id: str) -> list[BudgetCap]:
        return list(
            db.execute(
                select(BudgetCap)
                .where(BudgetCap.user_id == user_id)
                .order_by(BudgetCap.created_at.desc())
            )
            .scalars()
            .all()
        )

    @staticmethod
    def serialize(db: Session, row: BudgetCap) -> dict[str, Any]:
        spent_cents = UsageService.spent_in_period(db, user_id=row.user_id, period=row.period)
        spent_pct = (spent_cents / row.limit_cents * 100.0) if row.limit_cents else 0.0
        return {
            "budget_id": row.budget_id,
            "user_id": row.user_id,
            "scope": row.scope,
            "scope_value": row.scope_value,
            "period": row.period,
            "limit_cents": row.limit_cents,
            "currency": row.currency,
            "threshold_pct": row.threshold_pct,
            "active": row.active,
            "spent_cents": spent_cents,
            "spent_pct": round(spent_pct, 2),
            "last_alert_pct": row.last_alert_pct,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    @staticmethod
    def check_alerts(db: Session) -> list[dict[str, Any]]:
        """Returns a list of breach descriptions for caps where spent% \u2265 threshold% since the last alert."""
        rows = list(db.execute(select(BudgetCap).where(BudgetCap.active.is_(True))).scalars().all())
        alerts: list[dict[str, Any]] = []
        for cap in rows:
            spent_cents = UsageService.spent_in_period(db, user_id=cap.user_id, period=cap.period)
            if cap.limit_cents <= 0:
                continue
            spent_pct = (spent_cents / cap.limit_cents) * 100.0
            should_alert = spent_pct >= cap.threshold_pct
            already_alerted = (cap.last_alert_pct or 0.0) >= cap.threshold_pct
            if should_alert and not already_alerted:
                cap.last_alert_pct = spent_pct
                cap.updated_at = utcnow()
                db.commit()
                alerts.append(
                    {
                        "budget_id": cap.budget_id,
                        "user_id": cap.user_id,
                        "period": cap.period,
                        "limit_cents": cap.limit_cents,
                        "spent_cents": spent_cents,
                        "spent_pct": round(spent_pct, 2),
                        "currency": cap.currency,
                    }
                )
            elif not should_alert and (cap.last_alert_pct or 0.0) > 0.0:
                # New period started — reset the alert latch.
                cap.last_alert_pct = 0.0
                cap.updated_at = utcnow()
                db.commit()
        return alerts
