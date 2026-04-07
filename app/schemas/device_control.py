from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.device_command import DeviceCommandStatus


class DeviceCommandCreateRequest(BaseModel):
    agent_name: str = Field(min_length=1, max_length=100)
    command_type: str = Field(min_length=1, max_length=80)
    payload_json: dict = Field(default_factory=dict)
    source: str = Field(default="api", max_length=50)
    created_by_user_id: str | None = Field(default=None, max_length=120)


class DeviceCommandResultRequest(BaseModel):
    status: DeviceCommandStatus
    result_json: dict = Field(default_factory=dict)
    error_text: str | None = None


class DeviceCommandResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    command_id: str
    agent_name: str
    command_type: str
    source: str
    status: DeviceCommandStatus
    payload_json: dict
    result_json: dict
    artifact_path: str | None
    created_by_user_id: str | None
    error_text: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

