from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.schemas.whatsapp import (
    WhatsAppBlastRequest,
    WhatsAppProfileUpdateRequest,
    WhatsAppQueuedSendResponse,
    WhatsAppSendRequest,
    WhatsAppStatusResponse,
)
from app.services.whatsapp_service import WhatsAppBetaService

router = APIRouter(prefix="/api/v1/whatsapp", tags=["whatsapp"])
settings = get_settings()


@router.get("/status", response_model=WhatsAppStatusResponse)
def whatsapp_status(db: Session = Depends(get_db)):
    return WhatsAppStatusResponse(**WhatsAppBetaService.status(db))


@router.get("/qr")
def whatsapp_qr():
    try:
        image_bytes, content_type = WhatsAppBetaService.fetch_bridge_qr()
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=image_bytes,
        media_type=content_type or "image/png",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@router.post("/profile", response_model=WhatsAppStatusResponse)
def update_whatsapp_profile(payload: WhatsAppProfileUpdateRequest, db: Session = Depends(get_db)):
    WhatsAppBetaService.update_profile(
        db,
        sender_phone=payload.sender_phone,
        sender_label=payload.sender_label,
        default_recipient=payload.default_recipient,
        allowed_senders=payload.allowed_senders,
        allowed_recipients=payload.allowed_recipients,
    )
    WhatsAppBetaService.append_event(
        db,
        kind="profile",
        status="updated",
        recipient=payload.default_recipient.strip() or None,
        detail="Updated WhatsApp beta sender and recipient settings.",
    )
    return WhatsAppStatusResponse(**WhatsAppBetaService.status(db))


@router.post("/test-send", response_model=WhatsAppQueuedSendResponse)
def whatsapp_test_send(payload: WhatsAppSendRequest, db: Session = Depends(get_db)):
    if not payload.warning_acknowledged:
        raise HTTPException(status_code=400, detail="Acknowledge the WhatsApp beta warning before sending.")
    if not WhatsAppBetaService.is_enabled():
        raise HTTPException(status_code=400, detail="WhatsApp beta is disabled.")
    if not WhatsAppBetaService.is_allowed_recipient(db, payload.recipient):
        raise HTTPException(status_code=400, detail="Recipient is not in the WhatsApp beta allowlist.")

    success, detail = WhatsAppBetaService.send_message_now(
        db,
        recipient=payload.recipient,
        message=payload.message,
        category="test",
        bypass_cooldown=True,
    )
    if not success:
        raise HTTPException(status_code=400, detail=detail)
    return WhatsAppQueuedSendResponse(
        queued=False,
        message=f"Sent beta test message to `{WhatsAppBetaService.normalize_recipient(payload.recipient)}`.",
        scheduled_count=1,
        delays_seconds=[],
    )


@router.post("/blast", response_model=WhatsAppQueuedSendResponse)
def whatsapp_blast(payload: WhatsAppBlastRequest, db: Session = Depends(get_db)):
    if not payload.warning_acknowledged:
        raise HTTPException(status_code=400, detail="Acknowledge the WhatsApp beta warning before blasting.")
    if not WhatsAppBetaService.is_enabled():
        raise HTTPException(status_code=400, detail="WhatsApp beta is disabled.")
    if not settings.whatsapp_beta_allow_blasting:
        raise HTTPException(status_code=400, detail="WhatsApp blasting beta is disabled.")

    recipients = []
    seen = set()
    for item in payload.recipients:
        normalized = WhatsAppBetaService.normalize_recipient(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        recipients.append(normalized)

    if not recipients:
        raise HTTPException(status_code=400, detail="Provide at least one allowlisted recipient.")
    if len(recipients) > settings.whatsapp_beta_max_blast_recipients:
        raise HTTPException(
            status_code=400,
            detail=f"Blast exceeds the beta cap of {settings.whatsapp_beta_max_blast_recipients} recipients.",
        )
    blocked = [recipient for recipient in recipients if not WhatsAppBetaService.is_allowed_recipient(db, recipient)]
    if blocked:
        raise HTTPException(status_code=400, detail=f"These recipients are not allowlisted: {', '.join(blocked)}")

    delays = WhatsAppBetaService.queue_blast(recipients=recipients, message=payload.message)
    WhatsAppBetaService.append_event(
        db,
        kind="blast",
        status="queued",
        detail=f"Queued beta blast to {len(recipients)} recipients.",
    )
    return WhatsAppQueuedSendResponse(
        queued=True,
        message=(
            f"Queued WhatsApp blasting beta to {len(recipients)} allowlisted recipients. "
            "Use a secondary number and keep volume low."
        ),
        scheduled_count=len(recipients),
        delays_seconds=delays,
    )
