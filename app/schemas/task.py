from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.task import TaskStatus


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    assigned_agent_name: str | None = Field(default=None, max_length=100)
    source: str = Field(default="api", max_length=50)
    command_type: str | None = Field(default=None, max_length=50)
    created_by_user_id: str | None = Field(default=None, max_length=120)
    user_session_id: str | None = Field(default=None, max_length=120)
    metadata_json: dict = Field(default_factory=dict)


class TaskContinueRequest(BaseModel):
    note: str = Field(min_length=1)
    reset_to_pending: bool = True


class TaskClaimRequest(BaseModel):
    agent_name: str = Field(min_length=1, max_length=100)
    allow_unassigned: bool = True


class TaskResultRequest(BaseModel):
    agent_name: str = Field(min_length=1, max_length=100)
    status: TaskStatus
    result_text: str | None = None
    error_text: str | None = None
    metadata_json: dict = Field(default_factory=dict)


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_id: str
    title: str
    description: str
    status: TaskStatus
    source: str
    command_type: str | None
    assigned_agent_name: str | None
    created_by_user_id: str | None
    user_session_id: str | None
    result_text: str | None
    error_text: str | None
    metadata_json: dict
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
