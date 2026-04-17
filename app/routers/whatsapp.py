from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.conversation import ConversationMessage
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

WHATSAPP_SESSION_PREFIX = "whatsapp:"


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


@router.get("/conversations")
def list_whatsapp_conversations(limit: int = 60, db: Session = Depends(get_db)):
    rows = db.execute(
        select(
            ConversationMessage.session_id,
            ConversationMessage.platform_user_id,
            func.max(ConversationMessage.created_at).label("last_at"),
            func.count(ConversationMessage.id).label("message_count"),
        )
        .where(ConversationMessage.session_id.like(f"{WHATSAPP_SESSION_PREFIX}%"))
        .group_by(ConversationMessage.session_id, ConversationMessage.platform_user_id)
        .order_by(func.max(ConversationMessage.created_at).desc())
        .limit(max(1, min(limit, 200)))
    ).all()

    conversations: list[dict] = []
    for row in rows:
        chat_jid = str(row.session_id).removeprefix(WHATSAPP_SESSION_PREFIX)
        user_id = str(row.platform_user_id or "")
        sender_key = user_id.removeprefix(WHATSAPP_SESSION_PREFIX)
        latest = db.scalars(
            select(ConversationMessage)
            .where(ConversationMessage.session_id == row.session_id)
            .order_by(ConversationMessage.created_at.desc())
            .limit(1)
        ).first()
        preview = ""
        last_role = "assistant"
        if latest is not None:
            preview = (latest.content or "").strip().replace("\n", " ")[:160]
            last_role = latest.role.value if latest.role else "assistant"
        conversations.append(
            {
                "chat_jid": chat_jid,
                "session_id": row.session_id,
                "user_id": user_id,
                "sender_key": sender_key,
                "display_name": latest.username if latest and latest.username else sender_key,
                "last_message_at": row.last_at.isoformat() if row.last_at else None,
                "last_preview": preview,
                "last_role": last_role,
                "message_count": int(row.message_count or 0),
            }
        )
    return conversations


@router.get("/conversations/{chat_jid:path}/messages")
def list_whatsapp_conversation_messages(chat_jid: str, limit: int = 200, db: Session = Depends(get_db)):
    session_id = f"{WHATSAPP_SESSION_PREFIX}{chat_jid}"
    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.session_id == session_id)
        .order_by(ConversationMessage.created_at.asc())
        .limit(max(1, min(limit, 500)))
    )
    items = list(db.scalars(stmt).all())
    return [
        {
            "id": item.id,
            "session_id": item.session_id,
            "role": item.role.value if item.role else "assistant",
            "content": item.content,
            "provider": item.provider,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "attachments": list((item.metadata_json or {}).get("attachments", [])),
        }
        for item in items
    ]


@router.post("/chat-send", response_model=WhatsAppQueuedSendResponse)
def whatsapp_chat_send(payload: WhatsAppSendRequest, db: Session = Depends(get_db)):
    if not WhatsAppBetaService.is_enabled():
        raise HTTPException(status_code=400, detail="WhatsApp beta is disabled.")
    if not WhatsAppBetaService.is_allowed_recipient(db, payload.recipient):
        raise HTTPException(status_code=400, detail="Recipient is not in the WhatsApp beta allowlist.")

    success, detail = WhatsAppBetaService.send_message_now(
        db,
        recipient=payload.recipient,
        message=payload.message,
        category="chat",
        bypass_cooldown=True,
    )
    if not success:
        raise HTTPException(status_code=400, detail=detail)
    return WhatsAppQueuedSendResponse(
        queued=False,
        message=f"Sent WhatsApp message to `{WhatsAppBetaService.normalize_recipient(payload.recipient)}`.",
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
