"""Business logic for the memorycore module."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.memorycore.models import DesignReference, MemoryUsage
from app.modules.memorycore.pricing import estimate_cost_usd
from app.modules.memorycore.schemas import (
    DesignUpsert,
    UsageBreakdown,
    UsageLogRequest,
    UsageSummaryResponse,
)

logger = logging.getLogger(__name__)


def notify_telegram_usage(row: MemoryUsage) -> None:
    """Send a best-effort Telegram message about a completed session.

    Fails silently — telemetry never blocks the real call path.
    """
    settings = get_settings()
    token = settings.telegram_bot_token
    chat_id = settings.default_report_chat_id
    if not token or not chat_id:
        return

    cost_text = f"${row.cost_usd:.4f}" if row.cost_usd is not None else "(unknown)"
    header = (
        f"✅ {row.tool} session done\n"
        f"model: {row.model}\n"
        f"session: {row.session_id or '-'}\n"
        f"in={row.input_tokens:,}  out={row.output_tokens:,}  "
        f"cache_read={row.cache_read_tokens:,}\n"
        f"cost: {cost_text}"
    )
    body = (row.note or "").strip()
    if body and body != "auto-logged by Stop hook":
        # Telegram message limit is 4096 chars; keep some headroom.
        text = f"{header}\n\n{body[:3500]}"
    else:
        text = header
    try:
        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=5.0,
        )
    except httpx.HTTPError as exc:
        logger.warning("telegram notify failed: %s", exc)


def _empty_breakdown() -> UsageBreakdown:
    return UsageBreakdown(
        input_tokens=0,
        output_tokens=0,
        cache_read_tokens=0,
        cache_write_tokens=0,
        cost_usd=0.0,
        calls=0,
    )


def _accumulate(b: UsageBreakdown, row: MemoryUsage) -> UsageBreakdown:
    return UsageBreakdown(
        input_tokens=b.input_tokens + row.input_tokens,
        output_tokens=b.output_tokens + row.output_tokens,
        cache_read_tokens=b.cache_read_tokens + row.cache_read_tokens,
        cache_write_tokens=b.cache_write_tokens + row.cache_write_tokens,
        cost_usd=round(b.cost_usd + (row.cost_usd or 0.0), 6),
        calls=b.calls + 1,
    )


class UsageService:
    @staticmethod
    def log(db: Session, user_id: str, payload: UsageLogRequest) -> MemoryUsage:
        cost = estimate_cost_usd(payload.model, payload.input_tokens, payload.output_tokens)
        row = MemoryUsage(
            user_id=user_id,
            tool=payload.tool,
            model=payload.model,
            session_id=payload.session_id,
            project_key=payload.project_key,
            input_tokens=payload.input_tokens,
            output_tokens=payload.output_tokens,
            cache_read_tokens=payload.cache_read_tokens,
            cache_write_tokens=payload.cache_write_tokens,
            cost_usd=cost,
            note=payload.note,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def summary(
        db: Session, user_id: str, period: Literal["today", "week", "month"]
    ) -> UsageSummaryResponse:
        now = datetime.now(timezone.utc)
        if period == "today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "week":
            start = now - timedelta(days=7)
        else:
            start = now - timedelta(days=30)

        rows = (
            db.execute(
                select(MemoryUsage).where(
                    MemoryUsage.user_id == user_id,
                    MemoryUsage.created_at >= start,
                )
            )
            .scalars()
            .all()
        )

        total = _empty_breakdown()
        by_tool: dict[str, UsageBreakdown] = {}
        by_model: dict[str, UsageBreakdown] = {}
        for row in rows:
            total = _accumulate(total, row)
            by_tool[row.tool] = _accumulate(by_tool.get(row.tool, _empty_breakdown()), row)
            by_model[row.model] = _accumulate(by_model.get(row.model, _empty_breakdown()), row)

        return UsageSummaryResponse(
            period=period,
            range_start=start,
            range_end=now,
            total=total,
            by_tool=by_tool,
            by_model=by_model,
        )

    @staticmethod
    def list_for_session(db: Session, user_id: str, session_id: str) -> list[MemoryUsage]:
        return list(
            db.execute(
                select(MemoryUsage)
                .where(
                    MemoryUsage.user_id == user_id,
                    MemoryUsage.session_id == session_id,
                )
                .order_by(MemoryUsage.created_at.asc())
            )
            .scalars()
            .all()
        )


class DesignService:
    @staticmethod
    def upsert(db: Session, user_id: str, payload: DesignUpsert) -> DesignReference:
        existing = db.execute(
            select(DesignReference).where(
                DesignReference.user_id == user_id,
                DesignReference.name == payload.name,
            )
        ).scalar_one_or_none()

        if existing is None:
            row = DesignReference(
                user_id=user_id,
                name=payload.name,
                title=payload.title,
                prompt=payload.prompt,
                description=payload.description,
                tags=list(payload.tags),
                image_paths=list(payload.image_paths),
                source_url=payload.source_url,
                project_key=payload.project_key,
            )
            db.add(row)
        else:
            existing.title = payload.title
            existing.prompt = payload.prompt
            existing.description = payload.description
            existing.tags = list(payload.tags)
            existing.image_paths = list(payload.image_paths)
            existing.source_url = payload.source_url
            existing.project_key = payload.project_key
            row = existing

        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def get(db: Session, user_id: str, name: str) -> DesignReference | None:
        return db.execute(
            select(DesignReference).where(
                DesignReference.user_id == user_id,
                DesignReference.name == name,
            )
        ).scalar_one_or_none()

    @staticmethod
    def list(
        db: Session,
        user_id: str,
        query: str | None = None,
        tag: str | None = None,
    ) -> list[DesignReference]:
        stmt = select(DesignReference).where(DesignReference.user_id == user_id)
        if query:
            like = f"%{query.lower()}%"
            from sqlalchemy import func, or_

            stmt = stmt.where(
                or_(
                    func.lower(DesignReference.name).like(like),
                    func.lower(DesignReference.title).like(like),
                    func.lower(DesignReference.prompt).like(like),
                )
            )
        rows = list(db.execute(stmt.order_by(DesignReference.updated_at.desc())).scalars().all())
        if tag:
            tag_l = tag.lower()
            rows = [r for r in rows if any(tag_l == (t or "").lower() for t in (r.tags or []))]
        return rows

    @staticmethod
    def delete(db: Session, user_id: str, name: str) -> bool:
        row = DesignService.get(db, user_id, name)
        if row is None:
            return False
        db.delete(row)
        db.commit()
        return True
