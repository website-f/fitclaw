from pydantic import BaseModel, Field


class ChatMessageRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1)
    username: str | None = None
    session_id: str | None = None


class ChatMessageResponse(BaseModel):
    reply: str
    provider: str
    handled_as_task_command: bool

