"""Single read-only aggregate endpoint that powers the /analytics page.

Glues the audit, knowledge, and finance modules into one payload so the
front-end can render every dashboard card with one round-trip.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.finance import FinanceEntry
from app.modules.audit.models import AuditEvent
from app.modules.audit.service import BudgetService, FeedbackService, UsageService
from app.modules.knowledge.models import KnowledgeChunk, KnowledgeDocument

router = APIRouter(prefix="/api/v1", tags=["analytics"])


@router.get("/analytics/overview")
def analytics_overview(
    user_id: str = Query(...),
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)

    usage_today = UsageService.summary(db, user_id=user_id, period="today")
    usage_week = UsageService.summary(db, user_id=user_id, period="week")
    usage_month = UsageService.summary(db, user_id=user_id, period="month")
    feedback = FeedbackService.trends(db, user_id=user_id, days=days)

    kb_doc_count = db.execute(
        select(KnowledgeDocument).where(KnowledgeDocument.user_id == user_id)
    ).scalars().all()
    kb_chunks = db.execute(
        select(KnowledgeChunk).where(KnowledgeChunk.user_id == user_id)
    ).scalars().all()

    finance_rows = db.execute(
        select(FinanceEntry)
        .where(FinanceEntry.platform_user_id == user_id)
        .where(FinanceEntry.occurred_at >= since)
    ).scalars().all()
    finance_total_cents = sum(row.amount_cents for row in finance_rows)
    finance_by_category: dict[str, int] = {}
    for row in finance_rows:
        bucket = (row.category or "Uncategorized").strip()
        finance_by_category[bucket] = finance_by_category.get(bucket, 0) + row.amount_cents
    finance_currency = finance_rows[0].currency if finance_rows else "MYR"

    audit_rows = (
        db.execute(
            select(AuditEvent)
            .where(AuditEvent.user_id == user_id)
            .order_by(AuditEvent.created_at.desc())
            .limit(20)
        )
        .scalars()
        .all()
    )

    budgets = [BudgetService.serialize(db, row) for row in BudgetService.list(db, user_id=user_id)]

    return {
        "window_days": days,
        "usage": {
            "today": usage_today,
            "week": usage_week,
            "month": usage_month,
        },
        "feedback": feedback,
        "knowledge": {
            "documents": len(kb_doc_count),
            "chunks": len(kb_chunks),
            "by_department": _kb_by_department(kb_doc_count),
            "recent": [
                {
                    "doc_id": doc.doc_id,
                    "title": doc.title,
                    "chunk_count": doc.chunk_count,
                    "uploaded_at": doc.uploaded_at,
                    "department": doc.department,
                }
                for doc in sorted(kb_doc_count, key=lambda d: d.uploaded_at, reverse=True)[:5]
            ],
        },
        "finance": {
            "since": since,
            "currency": finance_currency,
            "total_cents": finance_total_cents,
            "entries": len(finance_rows),
            "by_category": [
                {"category": name, "cents": amount}
                for name, amount in sorted(finance_by_category.items(), key=lambda item: item[1], reverse=True)[:6]
            ],
        },
        "budgets": budgets,
        "audit": [
            {
                "event_id": row.event_id,
                "source": row.source,
                "action": row.action,
                "summary": row.summary,
                "actor": row.actor,
                "created_at": row.created_at,
            }
            for row in audit_rows
        ],
    }


def _kb_by_department(documents: list[KnowledgeDocument]) -> list[dict[str, object]]:
    buckets: dict[str, int] = {}
    for doc in documents:
        key = doc.department or "general"
        buckets[key] = buckets.get(key, 0) + 1
    return [
        {"department": name, "documents": count}
        for name, count in sorted(buckets.items(), key=lambda item: item[1], reverse=True)
    ]
