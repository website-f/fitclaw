from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.chat import ChatMessageRequest, ChatMessageResponse
from app.services.message_service import MessageService

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.post("/messages", response_model=ChatMessageResponse)
def send_message(payload: ChatMessageRequest, db: Session = Depends(get_db)):
    result = MessageService.process_user_message(
        db=db,
        user_id=payload.user_id,
        text=payload.text,
        username=payload.username,
        session_id=payload.session_id,
    )
    return ChatMessageResponse(
        reply=result.reply,
        provider=result.provider,
        handled_as_task_command=result.handled_as_task_command,
    )

