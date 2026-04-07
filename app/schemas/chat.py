from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.conversation import MessageRole


class ChatMessageRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=120)
    text: str = Field(default="")
    username: str | None = None
    session_id: str | None = None
    attachment_asset_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_message_or_attachment(self):
        if not self.text.strip() and not self.attachment_asset_ids:
            raise ValueError("Provide either text or at least one attachment.")
        return self


class ChatAttachmentResponse(BaseModel):
    kind: str
    caption: str | None = None
    filename: str | None = None
    public_url: str | None = None


class ChatMessageResponse(BaseModel):
    reply: str
    provider: str
    handled_as_task_command: bool
    handled_as_agent_command: bool
    session_id: str | None = None
    attachments: list[ChatAttachmentResponse] = Field(default_factory=list)


class ChatSessionSummaryResponse(BaseModel):
    session_id: str
    title: str
    preview: str
    last_message_at: datetime
    message_count: int
    last_role: MessageRole


class ChatHistoryMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: str
    role: MessageRole
    content: str
    provider: str | None = None
    created_at: datetime
    attachments: list[ChatAttachmentResponse] = Field(default_factory=list)
