from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re
import time as time_module
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.agent import Agent, AgentStatus
from app.models.task import TaskStatus
from app.services.agent_service import AgentService
from app.services.calendar_service import CalendarService
from app.services.chat_approval_service import ChatApprovalService
from app.services.command_result import CommandResult
from app.services.task_service import TaskService

settings = get_settings()


@dataclass(slots=True)
class ParsedAutomationRequest:
    agent: Agent
    action_kind: str
    risk_level: str
    url: str | None
    scheduled_for: datetime | None
    summary: str
    detail: str
    workflow_goal: str
    requires_confirmation: bool


class AgentAutomationService:
    URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
    CRAWL_PATTERN = re.compile(
        r"\b(crawl|scrape|inspect|read|summari[sz]e|check)\b.*\b(site|website|page|url|link|web)\b|"
        r"\bwebsite\b.*\bsummar|\bpage\b.*\bsummar",
        re.IGNORECASE,
    )
    OPEN_PATTERN = re.compile(
        r"\b(open|visit|go to|navigate to|launch)\b.*\b(site|website|page|url|link|browser)\b",
        re.IGNORECASE,
    )
    AUTOMATION_PATTERN = re.compile(
        r"\b(automate|automation|autobuy|auto buy|buy|purchase|checkout|order|add to cart|cart|shoppe|shopee|lazada|browser|open website|visit website)\b",
        re.IGNORECASE,
    )
    HIGH_RISK_PATTERN = re.compile(
        r"\b(buy|purchase|checkout|pay|payment|order|place order|add to cart|autobuy|auto buy|shoppe|shopee|lazada)\b",
        re.IGNORECASE,
    )
    MEDIUM_RISK_PATTERN = re.compile(
        r"\b(login|log in|sign in|submit|book|register|reserve|fill in|fill out|apply)\b",
        re.IGNORECASE,
    )
    AGENT_CONTEXT_PATTERN = re.compile(
        r"\b(agent|device|pc|computer|desktop|laptop|phone|mobile)\b",
        re.IGNORECASE,
    )
    CONFIRM_PATTERN = re.compile(r"^(yes|y|confirm|approved?|go ahead|do it|queue it|run it|proceed|ok|okay|sure)\b", re.IGNORECASE)
    CANCEL_PATTERN = re.compile(r"^(cancel|stop|nevermind|never mind|no)\b", re.IGNORECASE)
    TIME_HINT_PATTERN = re.compile(
        r"\b(today|tomorrow|tomorow|tmr|tmrw|day after tomorrow|next\s+\w+|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b|"
        r"\b(?:at\s+)?(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)|[01]?\d|2[0-3]:[0-5]\d)\b",
        re.IGNORECASE,
    )

    @classmethod
    def try_handle(cls, db: Session, user_id: str, session_id: str, text: str) -> CommandResult | None:
        normalized = text.strip()
        if not normalized:
            return None

        pending = cls._handle_pending_confirmation(db, user_id, session_id, normalized)
        if pending is not None:
            return pending

        parsed, error_reply = cls._parse_request(db, normalized)
        if error_reply is not None:
            return CommandResult(
                reply=error_reply,
                provider="agent-automation",
                handled_as_agent_command=True,
            )
        if parsed is None:
            return None

        if parsed.requires_confirmation:
            approval = ChatApprovalService.set_pending(
                db,
                user_id=user_id,
                session_id=session_id,
                payload={
                    "kind": "agent_automation",
                    "agent_name": parsed.agent.name,
                    "action_kind": parsed.action_kind,
                    "risk_level": parsed.risk_level,
                    "url": parsed.url,
                    "scheduled_for": parsed.scheduled_for.isoformat() if parsed.scheduled_for else "",
                    "summary": parsed.summary,
                    "detail": parsed.detail,
                    "workflow_goal": parsed.workflow_goal,
                },
            )
            when_text = cls._format_schedule(parsed.scheduled_for)
            reply_lines = [
                f"This is a `{parsed.risk_level}`-risk browser automation for `{parsed.agent.name}`.",
                parsed.detail,
            ]
            if when_text:
                reply_lines.append(f"When: {when_text}")
            if parsed.url:
                reply_lines.append(f"Target URL: {parsed.url}")
            reply_lines.extend(
                [
                    "",
                    "I will not queue it until you explicitly confirm.",
                    "Reply `confirm` to queue it, or `cancel` to drop it.",
                ]
            )
            return CommandResult(
                reply="\n".join(reply_lines),
                provider="agent-automation",
                handled_as_agent_command=True,
                metadata_json={"pending_chat_approval": approval},
            )

        return cls._queue_automation_task(
            db=db,
            user_id=user_id,
            session_id=session_id,
            parsed=parsed,
        )

    @classmethod
    def _handle_pending_confirmation(cls, db: Session, user_id: str, session_id: str, text: str) -> CommandResult | None:
        pending = ChatApprovalService.get_pending(db, user_id=user_id, session_id=session_id)
        if not pending or str(pending.get("kind", "")).strip() != "agent_automation":
            return None

        normalized = text.strip()
        if cls.CANCEL_PATTERN.match(normalized):
            ChatApprovalService.clear_pending(db, user_id=user_id, session_id=session_id)
            return CommandResult(
                reply="Okay, I cancelled that pending automation request.",
                provider="agent-automation",
                handled_as_agent_command=True,
            )

        if not cls.CONFIRM_PATTERN.match(normalized):
            return CommandResult(
                reply=(
                    "That automation is waiting for confirmation.\n\n"
                    "Reply `confirm` to queue it, or `cancel` to drop it."
                ),
                provider="agent-automation",
                handled_as_agent_command=True,
            )

        agent = AgentService.get_agent(db, str(pending.get("agent_name", "")).strip())
        if agent is None:
            ChatApprovalService.clear_pending(db, user_id=user_id, session_id=session_id)
            return CommandResult(
                reply="The target agent for that pending automation is no longer registered. Please send the request again.",
                provider="agent-automation",
                handled_as_agent_command=True,
            )

        scheduled_for = cls._parse_iso_datetime(str(pending.get("scheduled_for", "")).strip())
        parsed = ParsedAutomationRequest(
            agent=agent,
            action_kind=str(pending.get("action_kind", "")).strip() or "browser_open",
            risk_level=str(pending.get("risk_level", "")).strip() or "high",
            url=str(pending.get("url", "")).strip() or None,
            scheduled_for=scheduled_for,
            summary=str(pending.get("summary", "")).strip() or "Queue guarded browser automation",
            detail=str(pending.get("detail", "")).strip() or "Run a guarded browser workflow on the selected agent.",
            workflow_goal=str(pending.get("workflow_goal", "")).strip() or "Run a guarded browser workflow.",
            requires_confirmation=False,
        )
        ChatApprovalService.clear_pending(db, user_id=user_id, session_id=session_id)
        return cls._queue_automation_task(
            db=db,
            user_id=user_id,
            session_id=session_id,
            parsed=parsed,
        )

    @classmethod
    def _queue_automation_task(
        cls,
        *,
        db: Session,
        user_id: str,
        session_id: str,
        parsed: ParsedAutomationRequest,
    ) -> CommandResult:
        metadata = {
            "execution_mode": "device_command_proxy",
            "device_command_type": cls._command_type_for_action(parsed.action_kind),
            "device_payload_json": cls._build_command_payload(parsed),
            "automation_kind": parsed.action_kind,
            "risk_level": parsed.risk_level,
            "workflow_goal": parsed.workflow_goal,
        }
        if parsed.scheduled_for is not None:
            metadata["not_before_at"] = parsed.scheduled_for.isoformat()

        task = TaskService.create_task(
            db=db,
            title=parsed.summary,
            description=parsed.detail,
            assigned_agent_name=parsed.agent.name,
            source="chat_automation",
            command_type="agent_automation",
            created_by_user_id=user_id,
            user_session_id=session_id,
            metadata_json=metadata,
        )

        if parsed.scheduled_for is None and parsed.agent.status == AgentStatus.online:
            task, timeout_error = cls._wait_for_task(db, task.task_id, timeout_seconds=95)
            if timeout_error:
                return CommandResult(
                    reply=timeout_error,
                    provider="agent-automation",
                    handled_as_agent_command=True,
                )
            assert task is not None
            if task.status == TaskStatus.failed:
                return CommandResult(
                    reply=f"Automation failed on `{parsed.agent.name}`: {task.error_text or 'unknown error'}",
                    provider="agent-automation",
                    handled_as_agent_command=True,
                )
            lines = [
                f"Automation finished on `{parsed.agent.name}`.",
                f"Task: `{task.task_id}`",
            ]
            if task.result_text:
                lines.extend(["", task.result_text.strip()])
            return CommandResult(
                reply="\n".join(lines),
                provider="agent-automation",
                handled_as_agent_command=True,
            )

        schedule_line = cls._format_schedule(parsed.scheduled_for)
        if parsed.scheduled_for is not None:
            reply = (
                f"Queued automation task `{task.task_id}` for `{parsed.agent.name}`.\n"
                f"When: {schedule_line}\n"
                f"Plan: {parsed.detail}"
            )
        else:
            reply = (
                f"Queued automation task `{task.task_id}` for `{parsed.agent.name}`.\n"
                f"`{parsed.agent.name}` is currently `{parsed.agent.status.value}`, so it will run when that agent is available.\n"
                f"Plan: {parsed.detail}"
            )

        if parsed.risk_level == "high":
            reply += (
                "\n\nImportant: high-risk commerce flows stay guarded. "
                "This queues the browser workflow, but checkout or payment can still require a visible final confirmation."
            )

        return CommandResult(
            reply=reply,
            provider="agent-automation",
            handled_as_agent_command=True,
        )

    @classmethod
    def _parse_request(cls, db: Session, text: str) -> tuple[ParsedAutomationRequest | None, str | None]:
        urls = [match.rstrip(").,") for match in cls.URL_PATTERN.findall(text)]
        has_url = bool(urls)
        looks_like_crawl = bool(cls.CRAWL_PATTERN.search(text))
        looks_like_open = bool(cls.OPEN_PATTERN.search(text))
        looks_like_automation = bool(cls.AUTOMATION_PATTERN.search(text))

        if not has_url and not looks_like_automation and not looks_like_crawl and not looks_like_open:
            return None, None

        AgentService.mark_stale_agents(db)
        agents = AgentService.list_agents(db)
        matched_agents = cls._match_agents_in_text(text, agents)
        has_agent_context = bool(matched_agents) or bool(cls.AGENT_CONTEXT_PATTERN.search(text))

        if has_url and not (looks_like_automation or looks_like_crawl or looks_like_open):
            return None, None
        if (looks_like_crawl or looks_like_open) and not has_agent_context and not looks_like_automation:
            return None, None

        action_kind = "browser_crawl" if looks_like_crawl else "browser_open"
        agent, error = cls._resolve_agent(agents, matched_agents)
        if error:
            return None, error
        if agent is None:
            return None, None

        url = urls[0] if urls else None
        if action_kind == "browser_crawl" and not url:
            return None, (
                "I need a full website URL to crawl on the agent.\n\n"
                "Example: `ask DESKTOP-0112K9I to crawl https://example.com`"
            )
        if cls.HIGH_RISK_PATTERN.search(text) and not url:
            return None, "For guarded shopping automations, I need the exact product or checkout URL first."

        scheduled_for = cls._parse_schedule_datetime(text)
        risk_level = cls._classify_risk(text)
        workflow_goal = cls._extract_goal(text)
        summary = cls._build_task_title(action_kind, workflow_goal, url)
        detail = cls._build_detail(action_kind, workflow_goal, url, scheduled_for, risk_level)
        requires_confirmation = risk_level == "high"

        return (
            ParsedAutomationRequest(
                agent=agent,
                action_kind=action_kind,
                risk_level=risk_level,
                url=url,
                scheduled_for=scheduled_for,
                summary=summary,
                detail=detail,
                workflow_goal=workflow_goal,
                requires_confirmation=requires_confirmation,
            ),
            None,
        )

    @classmethod
    def _resolve_agent(cls, agents: list[Agent], matched_agents: list[Agent]) -> tuple[Agent | None, str | None]:
        if not agents:
            return None, "No agents are registered yet."
        if len(matched_agents) == 1:
            return matched_agents[0], None
        if len(matched_agents) > 1:
            names = ", ".join(agent.name for agent in matched_agents)
            return None, f"I found multiple matching agents: {names}. Please name one device explicitly."

        online_agents = [agent for agent in agents if agent.status == AgentStatus.online]
        if len(online_agents) == 1:
            return online_agents[0], None
        if len(agents) == 1:
            return agents[0], None

        names = ", ".join(agent.name for agent in agents)
        return None, f"I found multiple agents: {names}. Please include the target agent name."

    @staticmethod
    def _match_agents_in_text(text: str, agents: list[Agent]) -> list[Agent]:
        normalized_text = re.sub(r"[^a-z0-9]", "", text.lower())
        matches: dict[str, Agent] = {}
        for agent in agents:
            if re.search(rf"(?<![\w.-]){re.escape(agent.name)}(?![\w.-])", text, re.IGNORECASE):
                matches[agent.name] = agent
                continue
            normalized_name = re.sub(r"[^a-z0-9]", "", agent.name.lower())
            if normalized_name and normalized_name in normalized_text:
                matches[agent.name] = agent
        return list(matches.values())

    @classmethod
    def _classify_risk(cls, text: str) -> str:
        if cls.HIGH_RISK_PATTERN.search(text):
            return "high"
        if cls.MEDIUM_RISK_PATTERN.search(text):
            return "medium"
        return "low"

    @classmethod
    def _parse_schedule_datetime(cls, text: str) -> datetime | None:
        lower = text.lower()
        if not cls.TIME_HINT_PATTERN.search(lower):
            return None

        tz = ZoneInfo(settings.timezone)
        now_local = datetime.now(tz)
        date_ref = CalendarService._parse_date_reference(lower, now_local.date())
        hour, minute, explicit_time = CalendarService._parse_time_reference(lower)

        if date_ref is None and not explicit_time:
            return None

        target_date = date_ref or now_local.date()
        target_time = datetime.combine(target_date, datetime.min.time(), tzinfo=tz).replace(
            hour=hour if explicit_time else now_local.hour,
            minute=minute if explicit_time else now_local.minute,
            second=0,
            microsecond=0,
        )
        if date_ref is None and target_time <= now_local:
            target_time = target_time + timedelta(days=1)
        return target_time

    @staticmethod
    def _command_type_for_action(action_kind: str) -> str:
        if action_kind == "browser_crawl":
            return "browser_crawl"
        return "app_action"

    @classmethod
    def _build_command_payload(cls, parsed: ParsedAutomationRequest) -> dict:
        if parsed.action_kind == "browser_crawl":
            return {
                "url": parsed.url,
                "goal": parsed.workflow_goal,
                "max_chars": 3200,
                "max_links": 10,
                "include_links": True,
            }
        return {
            "action": "browser_open_url",
            "url": parsed.url,
            "goal": parsed.workflow_goal,
        }

    @classmethod
    def _build_task_title(cls, action_kind: str, workflow_goal: str, url: str | None) -> str:
        if action_kind == "browser_crawl":
            target = url or workflow_goal or "website"
            return TaskService.build_title_from_text(f"Crawl website: {target}")
        target = workflow_goal or url or "browser workflow"
        return TaskService.build_title_from_text(f"Browser automation: {target}")

    @classmethod
    def _build_detail(
        cls,
        action_kind: str,
        workflow_goal: str,
        url: str | None,
        scheduled_for: datetime | None,
        risk_level: str,
    ) -> str:
        if action_kind == "browser_crawl":
            detail = f"Crawl {url} and summarize the important page content on the selected agent."
        else:
            detail = f"Open {url or 'the requested target'} in the browser and continue toward: {workflow_goal}."
            if risk_level == "high":
                detail += " Keep payment or checkout guarded so the final visible confirmation can still be reviewed."
        if scheduled_for is not None:
            detail += f" Scheduled for {cls._format_schedule(scheduled_for)}."
        return detail

    @classmethod
    def _extract_goal(cls, text: str) -> str:
        cleaned = text.strip()
        cleaned = re.sub(cls.URL_PATTERN, "", cleaned).strip()
        cleaned = re.sub(r"\b(on|for|using|with)\s+[\w.-]+\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
        return cleaned or "Complete the requested browser workflow"

    @staticmethod
    def _format_schedule(value: datetime | None) -> str:
        if value is None:
            return ""
        return value.strftime("%Y-%m-%d %I:%M %p %Z")

    @staticmethod
    def _parse_iso_datetime(value: str) -> datetime | None:
        text = value.strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=ZoneInfo(settings.timezone))
        return parsed

    @staticmethod
    def _wait_for_task(db: Session, task_id: str, timeout_seconds: int) -> tuple[object | None, str | None]:
        deadline = time_module.monotonic() + max(timeout_seconds, 5)
        while time_module.monotonic() < deadline:
            db.expire_all()
            current = TaskService.get_task_by_task_id(db, task_id)
            if current and current.status in {TaskStatus.completed, TaskStatus.failed}:
                return current, None
            time_module.sleep(1.0)

        db.expire_all()
        current = TaskService.get_task_by_task_id(db, task_id)
        if current and current.status in {TaskStatus.completed, TaskStatus.failed}:
            return current, None
        return current, f"Queued automation task `{task_id}`, but it is still running. Check `status {task_id}` shortly."
