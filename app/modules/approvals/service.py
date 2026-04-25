from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.approvals.models import PendingApproval
from app.modules.approvals.schemas import ApprovalCreate

logger = logging.getLogger(__name__)


def _build_keyboard(approval_id: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Approve", "callback_data": f"app_approve:{approval_id}"},
                {"text": "🚫 Deny", "callback_data": f"app_deny:{approval_id}"},
            ]
        ]
    }


def _send_telegram(approval: PendingApproval) -> tuple[str | None, int | None]:
    settings = get_settings()
    token = settings.telegram_bot_token
    chat_id = settings.default_report_chat_id
    if not token or not chat_id:
        logger.warning("no telegram_bot_token / default_report_chat_id — approval unreachable by chat")
        return None, None
    text = (
        f"⚠️ Approval needed — {approval.source}\n"
        f"Tool: {approval.tool_name}\n"
        f"Action: {approval.action_summary}\n"
        f"Session: {approval.session_id or '-'}"
    )
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "reply_markup": _build_keyboard(approval.approval_id),
            },
            timeout=5.0,
        )
        data = resp.json()
        if data.get("ok"):
            msg = data.get("result", {})
            return str(chat_id), int(msg.get("message_id"))
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("telegram send failed: %s", exc)
    return str(chat_id), None


def _edit_telegram(approval: PendingApproval) -> None:
    settings = get_settings()
    token = settings.telegram_bot_token
    if not token or not approval.telegram_chat_id or not approval.telegram_message_id:
        return
    status_icon = "✅ APPROVED" if approval.status == "approved" else "🚫 DENIED"
    text = (
        f"{status_icon} — {approval.source}\n"
        f"Tool: {approval.tool_name}\n"
        f"Action: {approval.action_summary}\n"
        f"Decided: {approval.decided_at.isoformat() if approval.decided_at else '-'}"
    )
    try:
        httpx.post(
            f"https://api.telegram.org/bot{token}/editMessageText",
            json={
                "chat_id": approval.telegram_chat_id,
                "message_id": approval.telegram_message_id,
                "text": text,
            },
            timeout=5.0,
        )
    except httpx.HTTPError as exc:
        logger.warning("telegram edit failed: %s", exc)


class ApprovalService:
    @staticmethod
    def create(db: Session, user_id: str, payload: ApprovalCreate) -> PendingApproval:
        row = PendingApproval(
            user_id=user_id,
            source=payload.source,
            session_id=payload.session_id,
            tool_name=payload.tool_name,
            action_summary=payload.action_summary,
            action_detail=dict(payload.action_detail),
            status="pending",
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        chat_id, message_id = _send_telegram(row)
        if chat_id or message_id:
            row.telegram_chat_id = chat_id
            row.telegram_message_id = message_id
            db.commit()
            db.refresh(row)
        return row

    @staticmethod
    def get(db: Session, approval_id: str) -> PendingApproval | None:
        return db.execute(
            select(PendingApproval).where(PendingApproval.approval_id == approval_id)
        ).scalar_one_or_none()

    @staticmethod
    def decide(
        db: Session, approval_id: str, approved: bool, decided_by: str | None
    ) -> PendingApproval | None:
        row = ApprovalService.get(db, approval_id)
        if row is None or row.status != "pending":
            return row
        row.status = "approved" if approved else "denied"
        row.decided_at = datetime.now(timezone.utc)
        row.decided_by = decided_by
        db.commit()
        db.refresh(row)
        _edit_telegram(row)
        return row
