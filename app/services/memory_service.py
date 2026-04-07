from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import ConversationMessage, MessageRole


class MemoryService:
    @staticmethod
    def add_message(
        db: Session,
        session_id: str,
        platform_user_id: str,
        role: MessageRole,
        content: str,
        username: str | None = None,
        provider: str | None = None,
        metadata_json: dict | None = None,
    ) -> ConversationMessage:
        message = ConversationMessage(
            session_id=session_id,
            platform_user_id=platform_user_id,
            username=username,
            role=role,
            content=content,
            provider=provider,
            metadata_json=metadata_json or {},
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        return message

    @staticmethod
    def get_recent_messages(db: Session, session_id: str, limit: int = 12) -> list[ConversationMessage]:
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.session_id == session_id)
            .order_by(ConversationMessage.created_at.desc())
            .limit(limit)
        )
        return list(reversed(list(db.scalars(stmt).all())))

    @staticmethod
    def to_llm_messages(messages: list[ConversationMessage]) -> list[dict[str, str]]:
        return [{"role": item.role.value, "content": item.content} for item in messages]

