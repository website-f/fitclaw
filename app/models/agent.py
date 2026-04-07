from enum import Enum

from sqlalchemy import JSON, DateTime, Enum as SqlEnum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class AgentStatus(str, Enum):
    online = "online"
    busy = "busy"
    offline = "offline"


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    status: Mapped[AgentStatus] = mapped_column(SqlEnum(AgentStatus), default=AgentStatus.online, nullable=False)
    capabilities_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    last_heartbeat_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    current_task_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    registered_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

