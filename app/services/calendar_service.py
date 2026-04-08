from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import date, datetime, time as dt_time, timedelta
import json
import re
from pathlib import Path
import time as time_module
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.agent import Agent, AgentStatus
from app.models.base import utcnow
from app.models.calendar_event import CalendarEvent, CalendarEventStatus
from app.models.device_command import DeviceCommandStatus
from app.models.task import TaskStatus
from app.services.agent_service import AgentService
from app.services.command_result import CommandResult, MessageAttachment
from app.services.device_control_service import DeviceControlService
from app.services.task_service import TaskService
from app.services.telegram_service import TelegramService

settings = get_settings()

CALENDAR_DIR = Path("/data/calendar_invites")


@dataclass(slots=True)
class ParsedCalendarRequest:
    title: str
    description: str | None
    starts_at: datetime
    ends_at: datetime | None
    timezone: str
    location: str | None
    meeting_url: str | None
    attendees: list[str]
    reminder_minutes_before: int
    kind: str


@dataclass(slots=True)
class CalendarSyncResult:
    attempted: bool = False
    reply_lines: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class CalendarService:
    CREATE_PATTERN = re.compile(
        r"\b(?:schedule|set|add|book|create|plan|put|save|insert|mark|send|sent)\b.*\b(?:meeting|call|event|calendar|reminder|appointment|birthday)\b|"
        r"^\s*remind me to\b|"
        r"\b(?:in|on|to)\s+my\s+calendar\b",
        re.IGNORECASE,
    )
    LIST_PATTERN = re.compile(
        r"\b(?:show|list|what(?:'s| is)|see)\b.*\b(?:calendar|schedule|meetings?|events?|reminders?)\b|"
        r"\bupcoming\s+(?:meetings?|events?)\b|\btoday(?:'s)?\s+schedule\b|\btomorrow(?:'s)?\s+schedule\b",
        re.IGNORECASE,
    )
    CANCEL_PATTERN = re.compile(
        r"\b(?:cancel|delete|remove)\b.*\b(?:meeting|event|reminder)\b",
        re.IGNORECASE,
    )
    WEEKDAYS = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }

    @staticmethod
    def try_handle(db: Session, user_id: str, session_id: str, text: str) -> CommandResult | None:
        normalized = text.strip()
        if not normalized:
            return None

        if CalendarService.LIST_PATTERN.search(normalized):
            return CalendarService._handle_list(db, user_id, normalized)
        if CalendarService.CANCEL_PATTERN.search(normalized):
            return CalendarService._handle_cancel(db, user_id, normalized)
        if CalendarService.CREATE_PATTERN.search(normalized) or CalendarService._looks_like_create_request(normalized):
            return CalendarService._handle_create(db, user_id, session_id, normalized)
        return None

    @staticmethod
    def list_events(db: Session, user_id: str, days: int = 14) -> list[CalendarEvent]:
        now = utcnow()
        end = now + timedelta(days=max(days, 1))
        stmt = (
            select(CalendarEvent)
            .where(CalendarEvent.platform_user_id == user_id)
            .where(CalendarEvent.status == CalendarEventStatus.scheduled)
            .where(CalendarEvent.starts_at >= now)
            .where(CalendarEvent.starts_at <= end)
            .order_by(CalendarEvent.starts_at.asc())
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def get_event(db: Session, event_id: str) -> CalendarEvent | None:
        return db.scalar(select(CalendarEvent).where(CalendarEvent.event_id == event_id))

    @staticmethod
    def _handle_create(db: Session, user_id: str, session_id: str, text: str) -> CommandResult:
        try:
            parsed = CalendarService._parse_request(text)
        except ValueError as exc:
            return CommandResult(
                reply=(
                    f"{exc}\n\n"
                    "Example: `schedule a meeting with Sarah tomorrow at 3pm for 45 minutes` or "
                    "`remind me to review the report next monday at 9am`."
                ),
                provider="calendar-command",
            )

        event = CalendarEvent(
            platform_user_id=user_id,
            user_session_id=session_id,
            source="chat",
            title=parsed.title,
            description=parsed.description,
            starts_at=parsed.starts_at,
            ends_at=parsed.ends_at,
            timezone=parsed.timezone,
            location=parsed.location,
            meeting_url=parsed.meeting_url,
            attendees_json=parsed.attendees,
            reminder_minutes_before=parsed.reminder_minutes_before,
            metadata_json={"kind": parsed.kind, "created_from_text": text},
        )
        db.add(event)
        db.commit()
        db.refresh(event)

        ics_path = CalendarService._write_ics_file(event)
        event.ics_path = str(ics_path)
        db.commit()
        db.refresh(event)

        sync_result = CalendarService._attempt_device_calendar_sync(
            db=db,
            user_id=user_id,
            text=text,
            event=event,
        )
        if sync_result.metadata:
            event.metadata_json = {**(event.metadata_json or {}), "device_sync": sync_result.metadata}
            db.commit()
            db.refresh(event)

        lines = [
            f"Calendar event `{event.event_id}` is scheduled.",
            f"Title: {event.title}",
            f"Starts: {CalendarService._format_event_time(event.starts_at, event.timezone)}",
        ]
        if event.ends_at:
            lines.append(f"Ends: {CalendarService._format_event_time(event.ends_at, event.timezone)}")
        if event.location:
            lines.append(f"Location: {event.location}")
        if event.meeting_url:
            lines.append(f"Meeting link: {event.meeting_url}")
        lines.append(f"Reminder: {event.reminder_minutes_before} minutes before")
        lines.append("I attached an `.ics` invite so you can import it elsewhere if needed.")
        if sync_result.reply_lines:
            lines.extend(["", *sync_result.reply_lines])

        attachment = MessageAttachment(
            kind="document",
            path=str(ics_path),
            caption=f"Calendar invite for {event.title}",
            filename=ics_path.name,
            explicit_public_url=f"/api/v1/calendar/events/{event.event_id}/ics",
        )
        return CommandResult(
            reply="\n".join(lines),
            provider="calendar-command",
            attachments=[attachment],
        )

    @staticmethod
    def _handle_list(db: Session, user_id: str, text: str) -> CommandResult:
        normalized = text.lower()
        scope_days = 14
        label = "the next 14 days"
        if "today" in normalized:
            scope_days = 1
            label = "today"
        elif "tomorrow" in normalized:
            scope_days = 2
            label = "tomorrow and the day after"

        events = CalendarService.list_events(db, user_id=user_id, days=scope_days)
        if "today" in normalized:
            today = datetime.now(ZoneInfo(settings.timezone)).date()
            events = [item for item in events if item.starts_at.astimezone(ZoneInfo(item.timezone)).date() == today]
        elif "tomorrow" in normalized:
            tomorrow = datetime.now(ZoneInfo(settings.timezone)).date() + timedelta(days=1)
            events = [item for item in events if item.starts_at.astimezone(ZoneInfo(item.timezone)).date() == tomorrow]

        if not events:
            return CommandResult(
                reply=f"You do not have any scheduled calendar items for {label}.",
                provider="calendar-command",
            )

        lines = [f"Upcoming calendar items for {label}:"]
        for event in events[:12]:
            when = CalendarService._format_event_time(event.starts_at, event.timezone)
            suffix = f" -> {CalendarService._format_event_time(event.ends_at, event.timezone)}" if event.ends_at else ""
            lines.append(f"- {event.event_id}: {event.title} | {when}{suffix}")
        return CommandResult(reply="\n".join(lines), provider="calendar-command")

    @staticmethod
    def _handle_cancel(db: Session, user_id: str, text: str) -> CommandResult:
        match = re.search(r"\b(evt_[a-z0-9]{12})\b", text, re.IGNORECASE)
        event: CalendarEvent | None = None
        if match:
            event = db.scalar(
                select(CalendarEvent)
                .where(CalendarEvent.event_id == match.group(1))
                .where(CalendarEvent.platform_user_id == user_id)
            )
        else:
            lowered = text.lower()
            candidates = CalendarService.list_events(db, user_id=user_id, days=30)
            keywords = {
                token
                for token in re.split(r"[^a-z0-9]+", lowered)
                if token and token not in {"cancel", "delete", "remove", "meeting", "event", "reminder", "the", "my"}
            }
            for candidate in candidates:
                haystack = f"{candidate.title} {candidate.description or ''}".lower()
                if keywords and all(keyword in haystack for keyword in keywords):
                    event = candidate
                    break

        if event is None:
            return CommandResult(
                reply="I could not find a matching scheduled event to cancel. Mention the event id like `cancel event evt_xxxxx` if needed.",
                provider="calendar-command",
            )

        event.status = CalendarEventStatus.cancelled
        db.commit()
        return CommandResult(
            reply=f"Cancelled `{event.title}` ({event.event_id}).",
            provider="calendar-command",
        )

    @staticmethod
    def deliver_due_reminders(db: Session) -> dict[str, int]:
        now = utcnow()
        delivered = 0
        checked = 0
        stmt = (
            select(CalendarEvent)
            .where(CalendarEvent.status == CalendarEventStatus.scheduled)
            .where(CalendarEvent.reminder_sent_at.is_(None))
            .where(CalendarEvent.starts_at >= now - timedelta(hours=2))
            .order_by(CalendarEvent.starts_at.asc())
        )
        events = list(db.scalars(stmt).all())
        for event in events:
            checked += 1
            reminder_at = event.starts_at - timedelta(minutes=max(event.reminder_minutes_before, 0))
            if reminder_at > now:
                continue
            destination = CalendarService._resolve_reminder_destination(event.platform_user_id)
            if not destination:
                event.reminder_sent_at = now
                continue

            lines = [
                f"Reminder: {event.title}",
                f"Starts: {CalendarService._format_event_time(event.starts_at, event.timezone)}",
            ]
            if event.location:
                lines.append(f"Location: {event.location}")
            if event.meeting_url:
                lines.append(f"Meeting link: {event.meeting_url}")
            if TelegramService.send_message(destination, "\n".join(lines)):
                event.reminder_sent_at = now
                delivered += 1
        db.commit()
        return {"checked": checked, "delivered": delivered}

    @staticmethod
    def _resolve_reminder_destination(platform_user_id: str) -> str | None:
        raw = str(platform_user_id or "").strip()
        if raw.isdigit():
            return raw
        fallback = str(settings.default_report_chat_id or "").strip()
        return fallback or None

    @staticmethod
    def _looks_like_create_request(text: str) -> bool:
        lowered = text.lower()
        def has_word(*words: str) -> bool:
            return any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in words)

        has_calendar_target = any(
            phrase in lowered
            for phrase in (
                "my calendar",
                "google calendar",
                "outlook calendar",
                "calendar reminder",
                "calendar event",
            )
        )
        has_time_marker = bool(
            re.search(
                r"\b(today|tomorrow|day after tomorrow|next\s+\w+|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
                lowered,
            )
            or re.search(r"\b\d{4}-\d{2}-\d{2}\b", lowered)
            or re.search(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b", lowered)
            or re.search(r"\bat\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b", lowered)
        )
        has_event_hint = has_word("birthday", "meeting", "appointment", "event", "reminder", "call")
        has_create_intent = has_word("schedule", "set", "add", "create", "plan", "put", "save", "insert", "mark", "send", "sent")
        return (has_calendar_target and (has_time_marker or has_event_hint)) or (
            has_create_intent and has_event_hint and has_time_marker
        )

    @staticmethod
    def _attempt_device_calendar_sync(db: Session, user_id: str, text: str, event: CalendarEvent) -> CalendarSyncResult:
        agent, status_note = CalendarService._resolve_calendar_agent(db, text)
        if agent is None:
            if status_note:
                return CalendarSyncResult(reply_lines=[status_note], metadata={"status": "not_attempted"})
            return CalendarSyncResult()

        provider_preference = CalendarService._extract_calendar_provider_preference(text)
        probe_command, timeout_error = CalendarService._execute_device_command_and_wait(
            db=db,
            user_id=user_id,
            agent=agent,
            command_type="app_action",
            payload_json={"action": "calendar_probe"},
            timeout_seconds=25,
        )
        if timeout_error:
            return CalendarSyncResult(
                attempted=True,
                reply_lines=[f"Device calendar check on `{agent.name}` is still running. Try again in a few seconds."],
                metadata={"status": "pending", "agent_name": agent.name},
            )

        probe_result = {}
        if probe_command is not None and probe_command.status == DeviceCommandStatus.completed:
            probe_result = dict(probe_command.result_json or {})
        elif probe_command is not None and CalendarService._should_use_calendar_fallback(probe_command.error_text):
            return CalendarService._attempt_legacy_device_calendar_sync(
                db=db,
                user_id=user_id,
                agent=agent,
                event=event,
                provider_preference=provider_preference,
            )
        elif probe_command is not None and probe_command.status == DeviceCommandStatus.failed:
            return CalendarSyncResult(
                attempted=True,
                reply_lines=[f"Device calendar inspection failed on `{agent.name}`: {probe_command.error_text or 'unknown error'}"],
                metadata={"status": "probe_failed", "agent_name": agent.name},
            )

        chosen_provider = provider_preference or str(probe_result.get("recommended_provider") or "google")
        payload = {
            "action": "calendar_create",
            "provider": chosen_provider,
            "event_id": event.event_id,
            "title": event.title,
            "description": event.description or "",
            "location": event.location or "",
            "meeting_url": event.meeting_url or "",
            "starts_at": event.starts_at.isoformat(),
            "ends_at": event.ends_at.isoformat() if event.ends_at else "",
            "timezone": event.timezone,
            "reminder_minutes_before": event.reminder_minutes_before,
        }

        create_command, timeout_error = CalendarService._execute_device_command_and_wait(
            db=db,
            user_id=user_id,
            agent=agent,
            command_type="app_action",
            payload_json=payload,
            timeout_seconds=45,
        )
        if timeout_error:
            return CalendarSyncResult(
                attempted=True,
                reply_lines=[f"Calendar sync on `{agent.name}` is still running. I already saved the internal event and attached the invite."],
                metadata={"status": "pending", "agent_name": agent.name, "probe": probe_result},
            )

        if create_command is None:
            return CalendarSyncResult()

        if create_command.status == DeviceCommandStatus.failed and CalendarService._should_use_calendar_fallback(
            create_command.error_text
        ):
            return CalendarService._attempt_legacy_device_calendar_sync(
                db=db,
                user_id=user_id,
                agent=agent,
                event=event,
                provider_preference=provider_preference,
            )

        if create_command.status == DeviceCommandStatus.failed:
            return CalendarSyncResult(
                attempted=True,
                reply_lines=[f"Device calendar sync failed on `{agent.name}`: {create_command.error_text or 'unknown error'}"],
                metadata={"status": "create_failed", "agent_name": agent.name, "probe": probe_result},
            )

        result = dict(create_command.result_json or {})
        return CalendarSyncResult(
            attempted=True,
            reply_lines=CalendarService._build_calendar_sync_reply_lines(agent.name, probe_result, result),
            metadata={"status": "completed", "agent_name": agent.name, "probe": probe_result, "result": result},
        )

    @staticmethod
    def _attempt_legacy_device_calendar_sync(
        db: Session,
        user_id: str,
        agent: Agent,
        event: CalendarEvent,
        provider_preference: str | None,
    ) -> CalendarSyncResult:
        platform_name = str((agent.metadata_json or {}).get("platform", "")).lower()
        if "windows" not in platform_name:
            return CalendarSyncResult(
                attempted=True,
                reply_lines=[
                    f"`{agent.name}` is on an older agent build, so I kept the event internally and attached the `.ics` invite instead."
                ],
                metadata={"status": "legacy-unsupported", "agent_name": agent.name},
            )

        script = CalendarService._build_windows_calendar_fallback_script(event, provider_preference)
        task, timeout_error = CalendarService._execute_task_and_wait(
            db=db,
            user_id=user_id,
            agent=agent,
            description=f"powershell:\n{script}",
            timeout_seconds=120,
            title="Legacy calendar sync",
            metadata_json={"execution_mode": "powershell", "command": script, "hidden_window": True},
        )
        if timeout_error:
            return CalendarSyncResult(
                attempted=True,
                reply_lines=[f"Legacy calendar sync on `{agent.name}` is still running. I attached the `.ics` invite as a fallback."],
                metadata={"status": "legacy-pending", "agent_name": agent.name},
            )
        assert task is not None
        if task.status == TaskStatus.failed:
            return CalendarSyncResult(
                attempted=True,
                reply_lines=[f"Legacy calendar sync failed on `{agent.name}`: {task.error_text or 'unknown error'}"],
                metadata={"status": "legacy-failed", "agent_name": agent.name},
            )

        output = (task.result_text or "").strip()
        lines = [f"Device calendar sync used a compatibility path on `{agent.name}`."]
        if output:
            lines.extend(["", *output.splitlines()])
        return CalendarSyncResult(
            attempted=True,
            reply_lines=lines,
            metadata={"status": "legacy-completed", "agent_name": agent.name, "output": output},
        )

    @staticmethod
    def _resolve_calendar_agent(db: Session, text: str) -> tuple[Agent | None, str | None]:
        agents = AgentService.list_agents(db)
        if not agents:
            return None, None

        matches = CalendarService._match_agents_in_text(text, agents)
        if len(matches) == 1:
            agent = matches[0]
            if agent.status != AgentStatus.online:
                return None, f"`{agent.name}` is currently `{agent.status.value}`, so I kept the event internally and attached the invite."
            return agent, None
        if len(matches) > 1:
            names = ", ".join(agent.name for agent in matches)
            return None, f"I scheduled the event, but I found multiple matching agents for device sync: {names}."

        online_agents = [agent for agent in agents if agent.status == AgentStatus.online]
        if len(online_agents) == 1:
            return online_agents[0], None
        if len(online_agents) > 1:
            names = ", ".join(agent.name for agent in online_agents)
            return None, f"I scheduled the event and attached the invite. If you want device sync too, name one online agent: {names}."
        return None, None

    @staticmethod
    def _extract_calendar_provider_preference(text: str) -> str | None:
        lowered = text.lower()
        if "google calendar" in lowered or "gmail calendar" in lowered:
            return "google"
        if "outlook" in lowered or "microsoft calendar" in lowered:
            return "outlook"
        if ".ics" in lowered or "invite file" in lowered:
            return "ics"
        return None

    @staticmethod
    def _match_agents_in_text(text: str, agents: list[Agent]) -> list[Agent]:
        normalized_text = CalendarService._normalize_agent_label(text)
        matches: list[Agent] = []
        for agent in agents:
            if re.search(rf"(?<![\w.-]){re.escape(agent.name)}(?![\w.-])", text, re.IGNORECASE):
                matches.append(agent)
                continue
            if CalendarService._normalize_agent_label(agent.name) in normalized_text:
                matches.append(agent)
        deduped: dict[str, Agent] = {}
        for agent in matches:
            deduped[agent.name] = agent
        return list(deduped.values())

    @staticmethod
    def _normalize_agent_label(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", value.lower())

    @staticmethod
    def _execute_device_command_and_wait(
        db: Session,
        user_id: str,
        agent: Agent,
        command_type: str,
        payload_json: dict,
        timeout_seconds: int,
    ):
        if agent.status != AgentStatus.online:
            return None, f"`{agent.name}` is currently `{agent.status.value}`."

        command = DeviceControlService.create_command(
            db=db,
            agent_name=agent.name,
            command_type=command_type,
            payload_json=payload_json,
            source="calendar",
            created_by_user_id=user_id,
        )

        deadline = time_module.monotonic() + max(timeout_seconds, 5)
        while time_module.monotonic() < deadline:
            db.expire_all()
            current = DeviceControlService.get_command(db, command.command_id)
            if current and current.status in {DeviceCommandStatus.completed, DeviceCommandStatus.failed}:
                return current, None
            time_module.sleep(0.75)

        db.expire_all()
        current = DeviceControlService.get_command(db, command.command_id)
        if current and current.status in {DeviceCommandStatus.completed, DeviceCommandStatus.failed}:
            return current, None
        return current, f"Sent calendar command `{command.command_id}` to `{agent.name}`, but it is still pending."

    @staticmethod
    def _execute_task_and_wait(
        db: Session,
        user_id: str,
        agent: Agent,
        description: str,
        timeout_seconds: int,
        title: str,
        metadata_json: dict | None = None,
    ):
        task = TaskService.create_task(
            db=db,
            title=title,
            description=description,
            assigned_agent_name=agent.name,
            source="calendar",
            command_type="compatibility-task",
            created_by_user_id=user_id,
            metadata_json=metadata_json or {},
        )

        deadline = time_module.monotonic() + max(timeout_seconds, 5)
        while time_module.monotonic() < deadline:
            db.expire_all()
            current = TaskService.get_task_by_task_id(db, task.task_id)
            if current and current.status in {TaskStatus.completed, TaskStatus.failed}:
                return current, None
            time_module.sleep(1.0)

        db.expire_all()
        current = TaskService.get_task_by_task_id(db, task.task_id)
        if current and current.status in {TaskStatus.completed, TaskStatus.failed}:
            return current, None
        return current, f"Sent legacy calendar task `{task.task_id}` to `{agent.name}`, but it is still running."

    @staticmethod
    def _should_use_calendar_fallback(error_text: str | None) -> bool:
        lowered = str(error_text or "").strip().lower()
        return "unsupported control command" in lowered or "unsupported app action" in lowered or "calendar_" in lowered

    @staticmethod
    def _build_calendar_sync_reply_lines(agent_name: str, probe_result: dict, result: dict) -> list[str]:
        lines: list[str] = []
        if probe_result.get("has_google_calendar_window"):
            lines.append(f"`{agent_name}` already appears to have Google Calendar open.")
        elif probe_result.get("outlook_available"):
            lines.append(f"`{agent_name}` appears to have Outlook available for direct calendar saves.")

        provider_used = str(result.get("provider_used") or "").strip().lower()
        if provider_used == "outlook":
            lines.append(f"Device calendar sync: saved the event directly into Outlook on `{agent_name}`.")
        elif provider_used == "google":
            lines.append(
                f"Device calendar sync: opened a prefilled Google Calendar event on `{agent_name}`. "
                "If that browser session is already signed in, you can confirm it there immediately."
            )
        elif provider_used == "ics":
            lines.append(
                f"Device calendar sync: opened a local `.ics` invite on `{agent_name}` so the device calendar app can import it."
            )

        if result.get("outlook_error"):
            lines.append(f"Outlook direct-save was unavailable, so I fell back automatically: {result['outlook_error']}")
        reason = str(probe_result.get("reason") or "").strip()
        if reason:
            lines.append(f"Device check: {reason}")
        return lines

    @staticmethod
    def _build_windows_calendar_fallback_script(event: CalendarEvent, provider_preference: str | None) -> str:
        payload = {
            "provider_preference": provider_preference or "",
            "event_id": event.event_id,
            "title": event.title,
            "description": event.description or "",
            "location": event.location or "",
            "meeting_url": event.meeting_url or "",
            "starts_at": event.starts_at.isoformat(),
            "ends_at": event.ends_at.isoformat() if event.ends_at else "",
            "timezone": event.timezone,
            "reminder_minutes_before": event.reminder_minutes_before,
        }
        payload_b64 = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
        return f"""
$ErrorActionPreference = 'Stop'
$PayloadJson = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('{payload_b64}'))
$Payload = $PayloadJson | ConvertFrom-Json
$Preferred = [string]$Payload.provider_preference
$Messages = [System.Collections.Generic.List[string]]::new()
$UsedProvider = $null

function New-GoogleCalendarUrl([object]$Item) {{
  $StartUtc = [DateTime]::Parse([string]$Item.starts_at).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
  $EndUtc = if ([string]::IsNullOrWhiteSpace([string]$Item.ends_at)) {{ $StartUtc }} else {{ [DateTime]::Parse([string]$Item.ends_at).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') }}
  $Title = [uri]::EscapeDataString([string]$Item.title)
  $Details = [uri]::EscapeDataString([string]$Item.description)
  $Location = [uri]::EscapeDataString([string]$Item.location)
  $Timezone = [uri]::EscapeDataString([string]$Item.timezone)
  return "https://calendar.google.com/calendar/render?action=TEMPLATE&text=$Title&dates=$StartUtc/$EndUtc&details=$Details&location=$Location&ctz=$Timezone"
}}

function Write-IcsFile([object]$Item) {{
  $StartUtc = [DateTime]::Parse([string]$Item.starts_at).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
  $EndUtc = if ([string]::IsNullOrWhiteSpace([string]$Item.ends_at)) {{ $StartUtc }} else {{ [DateTime]::Parse([string]$Item.ends_at).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') }}
  $Target = Join-Path $env:TEMP ("{event.event_id}.ics")
  $Description = [string]$Item.description
  if ([string]::IsNullOrWhiteSpace($Description)) {{
    $Description = 'Created by Personal AI Ops Platform'
  }}
  $Lines = @(
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//FitClaw//Personal AI Ops Platform//EN',
    'BEGIN:VEVENT',
    'UID:{event.event_id}@fitclaw.aiops',
    ('DTSTAMP:' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')),
    ('DTSTART:' + $StartUtc),
    ('DTEND:' + $EndUtc),
    ('SUMMARY:' + [string]$Item.title),
    ('DESCRIPTION:' + $Description),
    'STATUS:CONFIRMED'
  )
  if (-not [string]::IsNullOrWhiteSpace([string]$Item.location)) {{
    $Lines += ('LOCATION:' + [string]$Item.location)
  }}
  if (-not [string]::IsNullOrWhiteSpace([string]$Item.meeting_url)) {{
    $Lines += ('URL:' + [string]$Item.meeting_url)
  }}
  $Lines += 'END:VEVENT'
  $Lines += 'END:VCALENDAR'
  Set-Content -LiteralPath $Target -Value $Lines -Encoding UTF8
  return $Target
}}

if ($Preferred -ne 'google') {{
  try {{
    $Outlook = New-Object -ComObject Outlook.Application
    $Appointment = $Outlook.CreateItem(1)
    $Appointment.Subject = [string]$Payload.title
    $Appointment.Start = [DateTime]::Parse([string]$Payload.starts_at).ToLocalTime().ToString('yyyy-MM-dd HH:mm:ss')
    $Appointment.End = if ([string]::IsNullOrWhiteSpace([string]$Payload.ends_at)) {{ $Appointment.Start }} else {{ [DateTime]::Parse([string]$Payload.ends_at).ToLocalTime().ToString('yyyy-MM-dd HH:mm:ss') }}
    $Appointment.Location = [string]$Payload.location
    $Body = [string]$Payload.description
    if ([string]::IsNullOrWhiteSpace($Body)) {{
      $Body = 'Created by Personal AI Ops Platform'
    }}
    if (-not [string]::IsNullOrWhiteSpace([string]$Payload.meeting_url)) {{
      $Body = ($Body.TrimEnd() + [Environment]::NewLine + [Environment]::NewLine + 'Meeting URL: ' + [string]$Payload.meeting_url)
    }}
    $Appointment.Body = $Body
    $Appointment.ReminderSet = $true
    $Appointment.ReminderMinutesBeforeStart = [int]$Payload.reminder_minutes_before
    $Appointment.BusyStatus = 2
    $Appointment.Save()
    $UsedProvider = 'outlook'
    $Messages.Add('Saved the event directly into Outlook on this device.')
  }} catch {{
    $Messages.Add('Outlook direct-save was not available, so I switched to a fallback path.')
  }}
}}

if (-not $UsedProvider -and $Preferred -ne 'ics') {{
  $Url = New-GoogleCalendarUrl $Payload
  Start-Process $Url | Out-Null
  $UsedProvider = 'google'
  $Messages.Add('Opened a prefilled Google Calendar event in the default browser. If you are already signed in there, you can confirm it right away.')
}}

if (-not $UsedProvider) {{
  $IcsPath = Write-IcsFile $Payload
  Start-Process $IcsPath | Out-Null
  $UsedProvider = 'ics'
  $Messages.Add('Opened a local .ics invite in the default calendar app.')
}}

$Messages -join [Environment]::NewLine
""".strip()

    @staticmethod
    def _parse_request(text: str) -> ParsedCalendarRequest:
        tz_name = settings.timezone
        tz = ZoneInfo(tz_name)
        now_local = utcnow().astimezone(tz)
        lower = text.lower()
        is_all_day = "all day" in lower or "all-day" in lower or "birthday" in lower

        event_date = CalendarService._parse_date_reference(lower, now_local.date())
        hour, minute, explicit_time = CalendarService._parse_time_reference(lower)
        default_hour = 9 if lower.startswith("remind me to") else 10
        start_date = event_date or now_local.date()
        start_time = dt_time(0 if is_all_day else (hour if explicit_time else default_hour), 0 if is_all_day else (minute if explicit_time else 0))
        starts_at = datetime.combine(start_date, start_time, tzinfo=tz)
        if event_date is None and starts_at <= now_local:
            starts_at = starts_at + timedelta(days=1)

        duration_minutes = CalendarService._parse_duration_minutes(
            lower,
            default=1440 if is_all_day else (30 if lower.startswith("remind me to") else settings.calendar_default_event_duration_minutes),
        )
        ends_at = starts_at + timedelta(minutes=duration_minutes) if duration_minutes > 0 else None
        reminder_minutes_before = CalendarService._parse_reminder_minutes(lower)
        attendees = sorted(set(re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.IGNORECASE)))
        meeting_url_match = re.search(r"https?://\S+", text, re.IGNORECASE)
        meeting_url = meeting_url_match.group(0).rstrip(").,") if meeting_url_match else None
        location = CalendarService._extract_tagged_value(text, ("location", "loc", "venue", "room"))
        title = CalendarService._extract_title(text)
        description = CalendarService._extract_description(text)
        kind = "reminder" if lower.startswith("remind me to") else "meeting" if any(token in lower for token in ("meeting", "call")) else "event"

        if not title:
            raise ValueError("I need a clearer meeting or reminder title.")
        if starts_at <= now_local - timedelta(minutes=2):
            raise ValueError("That time is already in the past. Please give me a future meeting time.")

        return ParsedCalendarRequest(
            title=title,
            description=description,
            starts_at=starts_at.astimezone(ZoneInfo("UTC")),
            ends_at=ends_at.astimezone(ZoneInfo("UTC")) if ends_at else None,
            timezone=tz_name,
            location=location,
            meeting_url=meeting_url,
            attendees=attendees,
            reminder_minutes_before=reminder_minutes_before,
            kind=kind,
        )

    @staticmethod
    def _parse_date_reference(text: str, today: date) -> date | None:
        if "day after tomorrow" in text:
            return today + timedelta(days=2)
        if "tomorrow" in text:
            return today + timedelta(days=1)
        if "today" in text:
            return today

        iso_match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
        if iso_match:
            year, month, day = map(int, iso_match.groups())
            return date(year, month, day)

        slash_match = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", text)
        if slash_match:
            day_value = int(slash_match.group(1))
            month_value = int(slash_match.group(2))
            year_raw = slash_match.group(3)
            year_value = today.year if not year_raw else int(year_raw) + (2000 if len(year_raw) == 2 else 0)
            return date(year_value, month_value, day_value)

        for weekday_name, weekday_number in CalendarService.WEEKDAYS.items():
            if re.search(rf"\bnext\s+{weekday_name}\b", text):
                days_ahead = (weekday_number - today.weekday()) % 7
                days_ahead = 7 if days_ahead == 0 else days_ahead
                return today + timedelta(days=days_ahead)
            if re.search(rf"\b(?:on|this)\s+{weekday_name}\b", text):
                days_ahead = (weekday_number - today.weekday()) % 7
                return today + timedelta(days=days_ahead)

        return None

    @staticmethod
    def _parse_time_reference(text: str) -> tuple[int, int, bool]:
        if "all day" in text or "all-day" in text:
            return 0, 0, True
        meridiem_match = re.search(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text)
        if meridiem_match:
            hour = int(meridiem_match.group(1))
            minute = int(meridiem_match.group(2) or 0)
            meridiem = meridiem_match.group(3).lower()
            if hour == 12:
                hour = 0
            if meridiem == "pm":
                hour += 12
            return hour, minute, True

        clock_match = re.search(r"\b(?:at\s+)?([01]?\d|2[0-3]):([0-5]\d)\b", text)
        if clock_match:
            return int(clock_match.group(1)), int(clock_match.group(2)), True
        return 9, 0, False

    @staticmethod
    def _parse_duration_minutes(text: str, default: int) -> int:
        match = re.search(r"\bfor\s+(\d+)\s*(minutes?|mins?|hours?|hrs?)\b", text)
        if not match:
            return default
        amount = int(match.group(1))
        unit = match.group(2).lower()
        if unit.startswith("hour") or unit.startswith("hr"):
            return amount * 60
        return amount

    @staticmethod
    def _parse_reminder_minutes(text: str) -> int:
        match = re.search(
            r"\b(?:remind me|send (?:me )?a reminder)\s+(\d+)\s*(minutes?|mins?|hours?|hrs?)\s+before\b",
            text,
        )
        if not match:
            return settings.calendar_default_reminder_minutes
        amount = int(match.group(1))
        unit = match.group(2).lower()
        return amount * 60 if unit.startswith("hour") or unit.startswith("hr") else amount

    @staticmethod
    def _extract_tagged_value(text: str, tags: tuple[str, ...]) -> str | None:
        for tag in tags:
            match = re.search(rf"\b{tag}\s*:\s*([^,\n]+)", text, re.IGNORECASE)
            if match:
                value = match.group(1).strip().rstrip(".")
                return value or None
        return None

    @staticmethod
    def _extract_title(text: str) -> str:
        working = " ".join(text.strip().split())
        if working.lower().startswith("remind me to"):
            working = re.sub(r"^remind me to\s+", "", working, flags=re.IGNORECASE)
            working = CalendarService._remove_schedule_suffixes(working)
            cleaned = working.strip(" .,-")
            return f"Reminder: {cleaned[:140]}" if cleaned else ""

        as_title = re.search(
            r"\bas\s+(.+?)(?=\s+\b(?:today|tomorrow|day after tomorrow|next|on|at|for|location|loc|venue|room|note|notes|agenda|description|desc)\b|$)",
            working,
            re.IGNORECASE,
        )
        if as_title:
            cleaned = " ".join(as_title.group(1).split()).strip(" .,-")
            if cleaned:
                return cleaned[:140]

        with_person = re.search(
            r"\b(?:meeting|call)\s+with\s+(.+?)(?=\s+\b(?:today|tomorrow|next|on|at|for|location|loc|venue|room)\b|$)",
            working,
            re.IGNORECASE,
        )
        if with_person:
            person = with_person.group(1).strip(" .,-")
            return f"Meeting with {person}"[:140]

        working = re.sub(r"^\s*(schedule|set|add|book|create|plan|put|save|insert|mark|send|sent)\s+", "", working, flags=re.IGNORECASE)
        working = re.sub(r"\b(a|an|my)\b", "", working, flags=re.IGNORECASE)
        working = re.sub(r"\b(calendar|meeting|call|event|reminder|appointment)\b", "", working, flags=re.IGNORECASE)
        working = re.sub(r"\b(?:in|on|to)\s+(?:the\s+)?calendar\b", "", working, flags=re.IGNORECASE)
        working = CalendarService._remove_schedule_suffixes(working)
        cleaned = " ".join(working.split()).strip(" .,-")
        return cleaned[:140]

    @staticmethod
    def _extract_description(text: str) -> str | None:
        note = CalendarService._extract_tagged_value(text, ("note", "notes", "agenda", "description", "desc"))
        if note:
            return note[:500]
        return None

    @staticmethod
    def _remove_schedule_suffixes(value: str) -> str:
        patterns = [
            r"\b(day after tomorrow|tomorrow|today)\b.*$",
            r"\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b.*$",
            r"\b(?:on|this)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b.*$",
            r"\bon\s+\d{4}-\d{2}-\d{2}\b.*$",
            r"\bon\s+\d{1,2}/\d{1,2}(?:/\d{2,4})?\b.*$",
            r"\bat\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b.*$",
            r"\bfor\s+\d+\s*(?:minutes?|mins?|hours?|hrs?)\b.*$",
            r"\b(?:in|on|to)\s+my\s+calendar\b.*$",
            r"\bas\s+.+$",
            r"\b(?:location|loc|venue|room|note|notes|agenda|description|desc)\s*:.*$",
            r"https?://\S+.*$",
        ]
        cleaned = value
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        return cleaned

    @staticmethod
    def _format_event_time(value: datetime | None, timezone_name: str) -> str:
        if value is None:
            return "--"
        try:
            tz = ZoneInfo(timezone_name)
        except Exception:
            tz = ZoneInfo(settings.timezone)
        localized = value.astimezone(tz)
        return localized.strftime("%Y-%m-%d %I:%M %p %Z")

    @staticmethod
    def _write_ics_file(event: CalendarEvent) -> Path:
        CALENDAR_DIR.mkdir(parents=True, exist_ok=True)
        output_path = CALENDAR_DIR / f"{event.event_id}.ics"
        start_utc = event.starts_at.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")
        end_dt = (event.ends_at or (event.starts_at + timedelta(minutes=max(event.reminder_minutes_before, 15)))).astimezone(ZoneInfo("UTC"))
        end_utc = end_dt.strftime("%Y%m%dT%H%M%SZ")
        created_utc = event.created_at.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//FitClaw//Personal AI Ops//EN",
            "BEGIN:VEVENT",
            f"UID:{event.event_id}@fitclaw.aiops",
            f"DTSTAMP:{created_utc}",
            f"DTSTART:{start_utc}",
            f"DTEND:{end_utc}",
            f"SUMMARY:{CalendarService._escape_ics_text(event.title)}",
            f"DESCRIPTION:{CalendarService._escape_ics_text(event.description or 'Created by Personal AI Ops Platform')}",
            f"STATUS:{'CANCELLED' if event.status == CalendarEventStatus.cancelled else 'CONFIRMED'}",
        ]
        if event.location:
            lines.append(f"LOCATION:{CalendarService._escape_ics_text(event.location)}")
        if event.meeting_url:
            lines.append(f"URL:{event.meeting_url}")
        lines.extend(["END:VEVENT", "END:VCALENDAR", ""])
        output_path.write_text("\r\n".join(lines), encoding="utf-8")
        return output_path

    @staticmethod
    def _escape_ics_text(value: str) -> str:
        return value.replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")
