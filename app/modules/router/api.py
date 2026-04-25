from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.router.schemas import ClassifyRequest, ClassifyResponse
from app.modules.router.service import RouterService

router = APIRouter(prefix="/api/v1/router", tags=["router"])


@router.post("/classify", response_model=ClassifyResponse)
def classify(
    user_id: str,
    payload: ClassifyRequest,
    db: Session = Depends(get_db),
) -> ClassifyResponse:
    intent, decision = RouterService.classify(db, user_id, payload.text, source=payload.source)
    return ClassifyResponse(intent=intent, decision_id=decision.id, created_at=decision.created_at)
