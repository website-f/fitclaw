from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.agent import AgentStatus
from app.schemas.model import ActiveModelConfig


class AgentRegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    capabilities_json: list[str] = Field(default_factory=list)
    metadata_json: dict = Field(default_factory=dict)


class AgentHeartbeatRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    status: AgentStatus = AgentStatus.online
    current_task_id: str | None = None
    metadata_json: dict = Field(default_factory=dict)


class AgentModelPreferences(BaseModel):
    preferred_text: ActiveModelConfig | None = None
    preferred_vision: ActiveModelConfig | None = None
    allowed_models: list[ActiveModelConfig] = Field(default_factory=list)


class AgentModelPreferencesUpdate(BaseModel):
    preferred_text: ActiveModelConfig | None = None
    preferred_vision: ActiveModelConfig | None = None
    allowed_models: list[ActiveModelConfig] = Field(default_factory=list)


class AgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    name: str
    status: AgentStatus
    capabilities_json: list[str]
    metadata_json: dict
    last_heartbeat_at: datetime
    current_task_id: str | None
    registered_at: datetime
    updated_at: datetime
    model_preferences: AgentModelPreferences = Field(default_factory=AgentModelPreferences)
