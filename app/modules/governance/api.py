from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.governance.schemas import (
    HandoffClaimRequest,
    HandoffOpenRequest,
    HandoffResolveRequest,
    HandoffResponse,
    UserRoleResponse,
    UserRoleUpsert,
)
from app.modules.governance.service import HandoffService, RoleService

router = APIRouter(prefix="/api/v1", tags=["governance"])


# ── Roles ──────────────────────────────────────────────────────────────
@router.get("/roles/{user_id}", response_model=UserRoleResponse)
def get_role(user_id: str, db: Session = Depends(get_db)):
    payload = RoleService.get(db, user_id)
    # Defaults shape — pad timestamps so the response model validates.
    if "created_at" not in payload:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        payload.setdefault("created_at", now)
        payload.setdefault("updated_at", now)
        payload.setdefault("metadata_json", {})
    return payload


@router.put("/roles/{user_id}", response_model=UserRoleResponse)
def upsert_role(user_id: str, payload: UserRoleUpsert, db: Session = Depends(get_db)):
    row = RoleService.upsert(
        db,
        user_id=user_id,
        role=payload.role,
        department=payload.department,
        allowed_departments=payload.allowed_departments,
        can_resolve_handoffs=payload.can_resolve_handoffs,
        metadata_json=payload.metadata_json,
    )
    return RoleService.serialize(row)


@router.get("/roles", response_model=list[UserRoleResponse])
def list_roles(db: Session = Depends(get_db)):
    return [RoleService.serialize(row) for row in RoleService.list(db)]


# ── Handoffs ───────────────────────────────────────────────────────────
@router.post("/handoffs", response_model=HandoffResponse)
def open_handoff(payload: HandoffOpenRequest, db: Session = Depends(get_db)):
    row = HandoffService.open(
        db,
        user_id=payload.user_id,
        question=payload.question,
        session_id=payload.session_id,
        message_id=payload.message_id,
        reason=payload.reason,
        department=payload.department,
        context_excerpt=payload.context_excerpt,
    )
    return HandoffService.serialize(row)


@router.get("/handoffs", response_model=list[HandoffResponse])
def list_handoffs(
    status: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    rows = HandoffService.list(db, status=status, user_id=user_id, limit=limit)
    return [HandoffService.serialize(row) for row in rows]


@router.post("/handoffs/{handoff_id}/claim", response_model=HandoffResponse)
def claim_handoff(handoff_id: str, payload: HandoffClaimRequest, db: Session = Depends(get_db)):
    row = HandoffService.claim(db, handoff_id=handoff_id, assignee=payload.assignee)
    if row is None:
        raise HTTPException(status_code=404, detail="Handoff not open.")
    return HandoffService.serialize(row)


@router.post("/handoffs/{handoff_id}/resolve", response_model=HandoffResponse)
def resolve_handoff(handoff_id: str, payload: HandoffResolveRequest, db: Session = Depends(get_db)):
    row = HandoffService.resolve(
        db, handoff_id=handoff_id, assignee=payload.assignee, reply=payload.reply
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Handoff not found or already resolved.")
    return HandoffService.serialize(row)
