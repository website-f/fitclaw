from enum import Enum

from sqlalchemy import JSON, DateTime, Enum as SqlEnum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class MessageRole(str, Enum):
    system = "system"
    user = "user"
    assistant = "assistant"


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    platform_user_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    role: Mapped[MessageRole] = mapped_column(SqlEnum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

