from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.approvals.schemas import ApprovalCreate, ApprovalDecision, ApprovalResponse
from app.modules.approvals.service import ApprovalService

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])


@router.post("", response_model=ApprovalResponse)
def create_approval(
    user_id: str,
    payload: ApprovalCreate,
    db: Session = Depends(get_db),
) -> ApprovalResponse:
    row = ApprovalService.create(db, user_id, payload)
    return ApprovalResponse.model_validate(row, from_attributes=True)


@router.get("/{approval_id}", response_model=ApprovalResponse)
def get_approval(approval_id: str, db: Session = Depends(get_db)) -> ApprovalResponse:
    row = ApprovalService.get(db, approval_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"approval {approval_id} not found")
    return ApprovalResponse.model_validate(row, from_attributes=True)


@router.post("/{approval_id}/decide", response_model=ApprovalResponse)
def decide_approval(
    approval_id: str,
    payload: ApprovalDecision,
    db: Session = Depends(get_db),
) -> ApprovalResponse:
    row = ApprovalService.decide(db, approval_id, payload.approved, payload.decided_by)
    if row is None:
        raise HTTPException(status_code=404, detail=f"approval {approval_id} not found")
    return ApprovalResponse.model_validate(row, from_attributes=True)
