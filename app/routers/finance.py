from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.finance import (
    FinanceEntryResponse,
    FinanceOverviewResponse,
    FinanceRuleCreateRequest,
    FinanceRuleResponse,
)
from app.services.finance_service import FinanceService

router = APIRouter(prefix="/api/v1/finance", tags=["finance"])


def _resolve_finance_user_scope(user_id: str | None) -> str | None:
    normalized = str(user_id or "").strip()
    if not normalized:
        return None
    lowered = normalized.lower()
    if lowered in {"web-finance", "all", "*"}:
        return None
    if lowered.startswith("web-") or lowered.startswith("web:"):
        return None
    return normalized


def _resolve_finance_rule_owner(user_id: str | None) -> str:
    normalized = str(user_id or "").strip()
    if not normalized:
        return "web-finance"
    lowered = normalized.lower()
    if lowered in {"all", "*", "web-finance"}:
        return "web-finance"
    return normalized


@router.get("/overview", response_model=FinanceOverviewResponse)
def finance_overview(user_id: str, display_currency: str | None = None, db: Session = Depends(get_db)):
    resolved = _resolve_finance_user_scope(user_id)
    return FinanceService.build_overview(db, user_id=resolved, display_currency=display_currency)


@router.get("/entries", response_model=list[FinanceEntryResponse])
def finance_entries(
    user_id: str,
    limit: int = 50,
    category: str | None = None,
    period: str | None = None,
    db: Session = Depends(get_db),
):
    resolved = _resolve_finance_user_scope(user_id)
    return FinanceService.list_entries(db, user_id=resolved, limit=min(max(limit, 1), 200), category=category, period=period)


@router.delete("/entries/{entry_id}")
def delete_finance_entry(entry_id: str, user_id: str, db: Session = Depends(get_db)):
    resolved = _resolve_finance_user_scope(user_id)
    deleted = FinanceService.delete_entry(db, user_id=resolved, entry_id=entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Finance entry not found.")
    return {"deleted": True}


@router.get("/rules", response_model=list[FinanceRuleResponse])
def finance_rules(user_id: str, active_only: bool = False, db: Session = Depends(get_db)):
    resolved = _resolve_finance_user_scope(user_id)
    return FinanceService.list_rules(db, user_id=resolved, active_only=active_only)


@router.post("/rules", response_model=FinanceRuleResponse)
def create_finance_rule(payload: FinanceRuleCreateRequest, db: Session = Depends(get_db)):
    return FinanceService.create_rule(
        db,
        user_id=_resolve_finance_rule_owner(payload.user_id),
        name=payload.name,
        kind=payload.kind,
        is_active=payload.is_active,
        criteria_json=payload.criteria_json,
        action_json=payload.action_json,
    )


@router.delete("/rules/{rule_id}")
def delete_finance_rule(rule_id: str, user_id: str, db: Session = Depends(get_db)):
    deleted = FinanceService.delete_rule(db, user_id=_resolve_finance_user_scope(user_id), rule_id=rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Finance rule not found.")
    return {"deleted": True}
