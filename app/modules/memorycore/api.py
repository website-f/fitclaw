"""FastAPI routes for the memorycore module.

Paths live under /api/v1/memorycore/usage and /api/v1/memorycore/designs.
The existing /api/v1/memorycore/profile and /api/v1/memorycore/projects
routes are unrelated and still served by app.routers.memorycore.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.memorycore.schemas import (
    DesignResponse,
    DesignUpsert,
    UsageLogRequest,
    UsageLogResponse,
    UsageSummaryResponse,
)
from app.modules.memorycore.service import DesignService, UsageService, notify_telegram_usage

router = APIRouter(prefix="/api/v1/memorycore", tags=["memorycore-v2"])


# --- Usage ledger ---


@router.post("/usage", response_model=UsageLogResponse)
def log_usage(
    user_id: str,
    payload: UsageLogRequest,
    notify: bool = False,
    db: Session = Depends(get_db),
) -> UsageLogResponse:
    row = UsageService.log(db, user_id, payload)
    if notify:
        notify_telegram_usage(row)
    return UsageLogResponse.model_validate(row, from_attributes=True)


@router.get("/usage/summary", response_model=UsageSummaryResponse)
def usage_summary(
    user_id: str,
    period: Literal["today", "week", "month"] = "today",
    db: Session = Depends(get_db),
) -> UsageSummaryResponse:
    return UsageService.summary(db, user_id, period)


@router.get("/usage/sessions/{session_id}", response_model=list[UsageLogResponse])
def usage_for_session(
    session_id: str,
    user_id: str,
    db: Session = Depends(get_db),
) -> list[UsageLogResponse]:
    rows = UsageService.list_for_session(db, user_id, session_id)
    return [UsageLogResponse.model_validate(r, from_attributes=True) for r in rows]


# --- Design library ---


@router.put("/designs/{name}", response_model=DesignResponse)
def upsert_design(
    name: str,
    user_id: str,
    payload: DesignUpsert,
    db: Session = Depends(get_db),
) -> DesignResponse:
    if payload.name != name:
        raise HTTPException(
            status_code=400,
            detail=f"URL name '{name}' does not match payload name '{payload.name}'",
        )
    row = DesignService.upsert(db, user_id, payload)
    return DesignResponse.model_validate(row, from_attributes=True)


@router.get("/designs", response_model=list[DesignResponse])
def list_designs(
    user_id: str,
    q: str | None = None,
    tag: str | None = None,
    db: Session = Depends(get_db),
) -> list[DesignResponse]:
    rows = DesignService.list(db, user_id, query=q, tag=tag)
    return [DesignResponse.model_validate(r, from_attributes=True) for r in rows]


@router.get("/designs/{name}", response_model=DesignResponse)
def get_design(
    name: str,
    user_id: str,
    db: Session = Depends(get_db),
) -> DesignResponse:
    row = DesignService.get(db, user_id, name)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Design '{name}' not found")
    return DesignResponse.model_validate(row, from_attributes=True)


@router.delete("/designs/{name}")
def delete_design(
    name: str,
    user_id: str,
    db: Session = Depends(get_db),
) -> dict:
    deleted = DesignService.delete(db, user_id, name)
    return {"deleted": deleted}
