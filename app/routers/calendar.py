from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.calendar import CalendarEventResponse
from app.services.calendar_service import CalendarService

router = APIRouter(prefix="/api/v1/calendar", tags=["calendar"])


@router.get("/events", response_model=list[CalendarEventResponse])
def list_calendar_events(
    user_id: str = Query(..., min_length=1, max_length=120),
    days: int = Query(default=14, ge=1, le=90),
    db: Session = Depends(get_db),
):
    events = CalendarService.list_events(db, user_id=user_id, days=days)
    return [_to_response(event) for event in events]


@router.get("/events/{event_id}", response_model=CalendarEventResponse)
def get_calendar_event(event_id: str, db: Session = Depends(get_db)):
    event = CalendarService.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar event not found.")
    return _to_response(event)


@router.get("/events/{event_id}/ics", include_in_schema=False)
def get_calendar_invite(event_id: str, db: Session = Depends(get_db)):
    event = CalendarService.get_event(db, event_id)
    if event is None or not event.ics_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar invite not found.")

    file_path = Path(event.ics_path)
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar invite file is missing.")

    return FileResponse(file_path, media_type="text/calendar", filename=file_path.name)


def _to_response(event) -> CalendarEventResponse:
    return CalendarEventResponse(
        event_id=event.event_id,
        platform_user_id=event.platform_user_id,
        user_session_id=event.user_session_id,
        source=event.source,
        title=event.title,
        description=event.description,
        status=event.status,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        timezone=event.timezone,
        location=event.location,
        meeting_url=event.meeting_url,
        attendees_json=list(event.attendees_json or []),
        reminder_minutes_before=event.reminder_minutes_before,
        reminder_sent_at=event.reminder_sent_at,
        ics_url=f"/api/v1/calendar/events/{event.event_id}/ics" if event.ics_path else None,
        metadata_json=event.metadata_json or {},
        created_at=event.created_at,
        updated_at=event.updated_at,
    )
