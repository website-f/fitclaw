from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.core.database import session_scope
from app.models.agent import Agent, AgentStatus
from app.services.agent_service import AgentService
from app.services.report_service import ReportService
from app.services.telegram_service import TelegramService
from app.services.whatsapp_service import WhatsAppBetaService
from sqlalchemy import select

settings = get_settings()


@celery_app.task(name="app.workers.jobs.generate_daily_report")
def generate_daily_report() -> dict:
    with session_scope() as db:
        report = ReportService.generate_daily_report(db)
        delivered = False
        whatsapp_delivered = False
        if settings.report_chat_enabled:
            delivered = TelegramService.send_message(settings.default_report_chat_id, report.content)
            report.delivered = delivered
        whatsapp_delivered = WhatsAppBetaService.queue_daily_report(db, report.content)
        db.commit()
        return {
            "report_id": report.report_id,
            "delivered": delivered,
            "whatsapp_queued": whatsapp_delivered,
        }


@celery_app.task(name="app.workers.jobs.capture_health_snapshot")
def capture_health_snapshot() -> dict:
    with session_scope() as db:
        report = ReportService.capture_health_snapshot(db)
        return {"report_id": report.report_id, "status": report.metadata_json.get("status", "unknown")}


@celery_app.task(name="app.workers.jobs.mark_stale_agents")
def mark_stale_agents() -> dict:
    with session_scope() as db:
        cutoff_agents = list(
            db.scalars(
                select(Agent).where(Agent.last_heartbeat_at < (AgentService._stale_cutoff())).where(Agent.status != AgentStatus.offline)
            ).all()
        )
        marked = AgentService.mark_stale_agents(db)
        if marked:
            for agent in cutoff_agents:
                WhatsAppBetaService.queue_agent_alert(
                    db,
                    agent.name,
                    "offline",
                    "Heartbeat expired. The platform marked this agent offline.",
                )
        return {"marked_offline": marked}


@celery_app.task(name="app.workers.jobs.poll_whatsapp_inbox")
def poll_whatsapp_inbox() -> dict:
    with session_scope() as db:
        result = WhatsAppBetaService.process_inbound_messages(db)
        return result


@celery_app.task(name="app.workers.jobs.process_whatsapp_inbound_message")
def process_whatsapp_inbound_message(
    message_id: str,
    chat_jid: str,
    sender: str,
    content: str,
    media_type: str = "",
    filename: str = "",
) -> dict:
    with session_scope() as db:
        result = WhatsAppBetaService.process_inbound_message(
            db,
            message_id=message_id,
            chat_jid=chat_jid,
            sender=sender,
            content=content,
            media_type=media_type,
            filename=filename,
        )
        return result


@celery_app.task(name="app.workers.jobs.send_whatsapp_message")
def send_whatsapp_message(
    recipient: str,
    message: str,
    category: str = "general",
    bypass_cooldown: bool = False,
) -> dict:
    with session_scope() as db:
        success, detail = WhatsAppBetaService.send_message_now(
            db,
            recipient=recipient,
            message=message,
            category=category,
            bypass_cooldown=bypass_cooldown,
        )
        return {
            "success": success,
            "recipient": recipient,
            "category": category,
            "detail": detail,
        }


# ===========================================================================
# Smart-automation tasks (LEARN.md §15)
# ===========================================================================

import json
import time

import httpx
from datetime import datetime, timedelta, timezone

import redis as _redis_lib

from app.modules.memorycore.models import MemoryUsage


_THRESHOLD_REDIS_KEY = "vps_stats:last_alert"


def _redis_client():
    return _redis_lib.Redis.from_url(settings.redis_url, decode_responses=True)


@celery_app.task(name="app.workers.jobs.host_threshold_alert")
def host_threshold_alert() -> dict:
    """LEARN.md §15 #15 — alert via Telegram when CPU/mem/disk crosses 80/85/90%.

    Pulls /stats from vps_stats, checks thresholds, sends a Telegram message
    at most once per hour per metric (Redis throttle).
    """
    url = f"{settings.vps_stats_internal_url.rstrip('/')}/stats"
    headers = {}
    if settings.vps_stats_token:
        headers["Authorization"] = f"Bearer {settings.vps_stats_token}"
    try:
        response = httpx.get(url, headers=headers, timeout=5.0)
        response.raise_for_status()
        snap = response.json()
    except httpx.HTTPError as exc:
        return {"ok": False, "error": str(exc)}

    THRESHOLDS = {
        "cpu_percent": 90.0,
        "mem_percent": 90.0,
        "disk_percent": 85.0,
    }
    breached = []
    for key, limit in THRESHOLDS.items():
        value = float(snap.get(key) or 0)
        if value >= limit:
            breached.append((key, value, limit))

    if not breached:
        return {"ok": True, "breached": []}

    redis = _redis_client()
    now = int(time.time())
    sent = []
    for key, value, limit in breached:
        last = redis.hget(_THRESHOLD_REDIS_KEY, key)
        if last and now - int(last) < 3600:  # already alerted this hour
            continue
        text = (
            f"⚠️ Host threshold breach\n"
            f"{key}: {value:.1f}% (limit {limit:.0f}%)\n"
            f"hostname: {snap.get('hostname', '?')}"
        )
        if settings.report_chat_enabled and settings.default_report_chat_id:
            TelegramService.send_message(settings.default_report_chat_id, text)
        redis.hset(_THRESHOLD_REDIS_KEY, key, now)
        sent.append(key)
    return {"ok": True, "breached": [b[0] for b in breached], "alerted": sent}


@celery_app.task(name="app.workers.jobs.daily_standup_digest")
def daily_standup_digest() -> dict:
    """LEARN.md §15 #28 — every morning, summarize yesterday's activity.

    Combines: MemoryUsage rows (LLM cost & calls) + Task completions, posts
    a single formatted Telegram message.
    """
    if not (settings.report_chat_enabled and settings.default_report_chat_id):
        return {"ok": False, "reason": "no report chat configured"}

    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=1)

    with session_scope() as db:
        from app.models.task import Task

        usage_rows = list(db.execute(
            select(MemoryUsage).where(
                MemoryUsage.created_at >= start, MemoryUsage.created_at < end
            )
        ).scalars().all())
        completed_tasks = list(db.execute(
            select(Task).where(Task.completed_at >= start, Task.completed_at < end)
        ).scalars().all())

    total_in = sum(r.input_tokens for r in usage_rows)
    total_out = sum(r.output_tokens for r in usage_rows)
    total_cost = sum(float(r.cost_usd or 0) for r in usage_rows)

    by_tool: dict[str, int] = {}
    for r in usage_rows:
        by_tool[r.tool] = by_tool.get(r.tool, 0) + 1

    lines = [
        f"☀️ Daily standup — {start.date()}",
        "",
        f"AI usage: {len(usage_rows)} sessions, in={total_in:,} out={total_out:,}, cost=${total_cost:.4f}",
    ]
    if by_tool:
        lines.append("  by tool: " + ", ".join(f"{k}={v}" for k, v in sorted(by_tool.items())))
    lines.append("")
    lines.append(f"Tasks completed: {len(completed_tasks)}")
    for task in completed_tasks[:10]:
        lines.append(f"  • {task.title}")
    if len(completed_tasks) > 10:
        lines.append(f"  …and {len(completed_tasks) - 10} more")

    text = "\n".join(lines)
    delivered = TelegramService.send_message(settings.default_report_chat_id, text)
    return {"ok": True, "delivered": delivered, "usage_rows": len(usage_rows), "completed_tasks": len(completed_tasks)}
