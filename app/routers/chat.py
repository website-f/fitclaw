from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.chat import (
    ChatAttachmentResponse,
    ChatHistoryMessageResponse,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatSessionSummaryResponse,
)
from app.services.message_service import MessageService
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.post("/messages", response_model=ChatMessageResponse)
def send_message(payload: ChatMessageRequest, db: Session = Depends(get_db)):
    result = MessageService.process_user_message(
        db=db,
        user_id=payload.user_id,
        text=payload.text,
        username=payload.username,
        session_id=payload.session_id,
        attachment_asset_ids=payload.attachment_asset_ids,
    )
    return ChatMessageResponse(
        reply=result.reply,
        provider=result.provider,
        handled_as_task_command=result.handled_as_task_command,
        handled_as_agent_command=result.handled_as_agent_command,
        session_id=result.session_id,
        attachments=_serialize_processed_attachments(result.attachments),
    )


@router.get("/sessions", response_model=list[ChatSessionSummaryResponse])
def list_sessions(user_id: str, limit: int = 24, db: Session = Depends(get_db)):
    summaries = MemoryService.list_sessions(db, platform_user_id=user_id, limit=limit)
    return [ChatSessionSummaryResponse(**item) for item in summaries]


@router.get("/sessions/{session_id}/messages", response_model=list[ChatHistoryMessageResponse])
def list_session_messages(session_id: str, user_id: str, limit: int = 200, db: Session = Depends(get_db)):
    messages = MemoryService.list_session_messages(db, session_id=session_id, platform_user_id=user_id, limit=limit)
    return [
        ChatHistoryMessageResponse(
            id=item.id,
            session_id=item.session_id,
            role=item.role,
            content=item.content,
            provider=item.provider,
            created_at=item.created_at,
            attachments=_serialize_stored_attachments(item.metadata_json),
        )
        for item in messages
    ]


def _serialize_processed_attachments(attachments) -> list[ChatAttachmentResponse]:
    results: list[ChatAttachmentResponse] = []
    for attachment in attachments or []:
        results.append(
            ChatAttachmentResponse(
                kind=attachment.kind,
                caption=attachment.caption,
                filename=attachment.filename,
                public_url=attachment.public_url(),
            )
        )
    return results


def _serialize_stored_attachments(metadata_json: dict[str, Any] | None) -> list[ChatAttachmentResponse]:
    items = list((metadata_json or {}).get("attachments", []))
    results: list[ChatAttachmentResponse] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        results.append(
            ChatAttachmentResponse(
                kind=str(item.get("kind", "document")),
                caption=item.get("caption"),
                filename=item.get("filename"),
                public_url=item.get("public_url"),
            )
        )
    return results
