from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.audit.schemas import (
    AuditEventCreate,
    AuditEventResponse,
    BudgetCapCreate,
    BudgetCapResponse,
    BudgetCapUpdate,
    ChatFeedbackCreate,
    ChatFeedbackResponse,
    LLMUsageCreate,
    LLMUsageResponse,
    UsageSummaryResponse,
)
from app.modules.audit.service import (
    AuditService,
    BudgetService,
    FeedbackService,
    UsageService,
)

router = APIRouter(prefix="/api/v1", tags=["audit"])


def _serialize_event(row) -> dict:
    return {
        "event_id": row.event_id,
        "user_id": row.user_id,
        "actor": row.actor,
        "source": row.source,
        "action": row.action,
        "summary": row.summary,
        "detail": dict(row.detail or {}),
        "related_ids": list(row.related_ids or []),
        "created_at": row.created_at,
    }


def _serialize_usage(row) -> dict:
    return {
        "usage_id": row.usage_id,
        "user_id": row.user_id,
        "session_id": row.session_id,
        "tool": row.tool,
        "provider": row.provider,
        "model": row.model,
        "input_tokens": row.input_tokens,
        "output_tokens": row.output_tokens,
        "cache_read_tokens": row.cache_read_tokens,
        "cache_write_tokens": row.cache_write_tokens,
        "cost_cents": row.cost_cents,
        "currency": row.currency,
        "note": row.note,
        "created_at": row.created_at,
    }


def _serialize_feedback(row) -> dict:
    return {
        "feedback_id": row.feedback_id,
        "user_id": row.user_id,
        "session_id": row.session_id,
        "message_id": row.message_id,
        "rating": row.rating,
        "comment": row.comment,
        "correction": row.correction,
        "created_at": row.created_at,
    }


# ── Audit events ────────────────────────────────────────────────────────────
@router.post("/audit", response_model=AuditEventResponse)
def create_audit_event(payload: AuditEventCreate, db: Session = Depends(get_db)):
    row = AuditService.log(
        db,
        user_id=payload.user_id,
        source=payload.source,
        action=payload.action,
        summary=payload.summary,
        actor=payload.actor,
        detail=payload.detail,
        related_ids=payload.related_ids,
    )
    return _serialize_event(row)


@router.get("/audit", response_model=list[AuditEventResponse])
def list_audit_events(
    user_id: str = Query(...),
    action: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    rows = AuditService.list_events(db, user_id=user_id, action=action, limit=limit)
    return [_serialize_event(row) for row in rows]


# ── LLM usage ledger ────────────────────────────────────────────────────────
@router.post("/usage", response_model=LLMUsageResponse)
def log_usage(payload: LLMUsageCreate, db: Session = Depends(get_db)):
    row = UsageService.log(
        db,
        user_id=payload.user_id,
        model=payload.model,
        tool=payload.tool,
        provider=payload.provider,
        session_id=payload.session_id,
        input_tokens=payload.input_tokens,
        output_tokens=payload.output_tokens,
        cache_read_tokens=payload.cache_read_tokens,
        cache_write_tokens=payload.cache_write_tokens,
        note=payload.note,
    )
    return _serialize_usage(row)


@router.get("/usage/summary", response_model=UsageSummaryResponse)
def usage_summary(
    user_id: str = Query(...),
    period: str = Query(default="today"),
    db: Session = Depends(get_db),
):
    return UsageService.summary(db, user_id=user_id, period=period)


# ── Chat feedback ───────────────────────────────────────────────────────────
@router.post("/feedback", response_model=ChatFeedbackResponse)
def submit_feedback(payload: ChatFeedbackCreate, db: Session = Depends(get_db)):
    row = FeedbackService.record(
        db,
        user_id=payload.user_id,
        rating=payload.rating,
        session_id=payload.session_id,
        message_id=payload.message_id,
        comment=payload.comment,
        correction=payload.correction,
    )
    return _serialize_feedback(row)


@router.get("/feedback", response_model=list[ChatFeedbackResponse])
def list_feedback(
    user_id: str = Query(...),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    rows = FeedbackService.list(db, user_id=user_id, limit=limit)
    return [_serialize_feedback(row) for row in rows]


@router.get("/feedback/trends")
def feedback_trends(
    user_id: str = Query(...),
    days: int = Query(default=7, ge=1, le=90),
    db: Session = Depends(get_db),
):
    return FeedbackService.trends(db, user_id=user_id, days=days)


# ── Budget caps ─────────────────────────────────────────────────────────────
@router.post("/budgets", response_model=BudgetCapResponse)
def create_budget(payload: BudgetCapCreate, db: Session = Depends(get_db)):
    row = BudgetService.create(
        db,
        user_id=payload.user_id,
        scope=payload.scope,
        scope_value=payload.scope_value,
        period=payload.period,
        limit_cents=payload.limit_cents,
        currency=payload.currency,
        threshold_pct=payload.threshold_pct,
    )
    return BudgetService.serialize(db, row)


@router.get("/budgets", response_model=list[BudgetCapResponse])
def list_budgets(user_id: str = Query(...), db: Session = Depends(get_db)):
    rows = BudgetService.list(db, user_id=user_id)
    return [BudgetService.serialize(db, row) for row in rows]


@router.patch("/budgets/{budget_id}", response_model=BudgetCapResponse)
def update_budget(
    budget_id: str,
    payload: BudgetCapUpdate,
    user_id: str = Query(...),
    db: Session = Depends(get_db),
):
    row = BudgetService.update(
        db,
        user_id=user_id,
        budget_id=budget_id,
        period=payload.period,
        limit_cents=payload.limit_cents,
        threshold_pct=payload.threshold_pct,
        active=payload.active,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Budget cap not found.")
    return BudgetService.serialize(db, row)
