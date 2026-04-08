from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.calendar_event import CalendarEventStatus


class CalendarEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    platform_user_id: str
    user_session_id: str | None
    source: str
    title: str
    description: str | None
    status: CalendarEventStatus
    starts_at: datetime
    ends_at: datetime | None
    timezone: str
    location: str | None
    meeting_url: str | None
    attendees_json: list = Field(default_factory=list)
    reminder_minutes_before: int
    reminder_sent_at: datetime | None
    ics_url: str | None = None
    metadata_json: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
