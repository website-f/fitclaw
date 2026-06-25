"""RBAC + human handoff orchestration."""
from __future__ import annotations

import re
import secrets
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.modules.governance.models import HandoffRequest, UserRole

HANDOFF_TRIGGER = re.compile(
    r"\b(talk to (?:a )?human|speak (?:to|with) (?:a )?human|human agent|escalate to (?:a )?human|need (?:a )?human|sensitive issue)\b",
    re.IGNORECASE,
)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


class RoleService:
    DEFAULT = {
        "role": "staff",
        "department": None,
        "allowed_departments": [],
        "can_resolve_handoffs": False,
    }

    @staticmethod
    def get(db: Session, user_id: str) -> dict[str, Any]:
        row = db.execute(select(UserRole).where(UserRole.user_id == user_id)).scalar_one_or_none()
        if row is None:
            return {**RoleService.DEFAULT, "user_id": user_id}
        return RoleService.serialize(row)

    @staticmethod
    def upsert(
        db: Session,
        *,
        user_id: str,
        role: str = "staff",
        department: str | None = None,
        allowed_departments: list[str] | None = None,
        can_resolve_handoffs: bool = False,
        metadata_json: dict[str, Any] | None = None,
    ) -> UserRole:
        row = db.execute(select(UserRole).where(UserRole.user_id == user_id)).scalar_one_or_none()
        now = utcnow()
        if row is None:
            row = UserRole(
                user_id=user_id,
                role=role,
                department=department,
                allowed_departments=list(allowed_departments or []),
                can_resolve_handoffs=1 if can_resolve_handoffs else 0,
                metadata_json=metadata_json or {},
                created_at=now,
                updated_at=now,
            )
            db.add(row)
        else:
            row.role = role
            row.department = department
            row.allowed_departments = list(allowed_departments or [])
            row.can_resolve_handoffs = 1 if can_resolve_handoffs else 0
            row.metadata_json = metadata_json or {}
            row.updated_at = now
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def list(db: Session) -> list[UserRole]:
        return list(db.execute(select(UserRole).order_by(UserRole.user_id)).scalars().all())

    @staticmethod
    def allowed_departments(db: Session, user_id: str) -> list[str] | None:
        """Returns the list of departments this user may read.

        `None` means "all" (admin or no role row). Empty list means "their
        own department only". Used by the knowledge base to scope search.
        """
        row = db.execute(select(UserRole).where(UserRole.user_id == user_id)).scalar_one_or_none()
        if row is None or row.role == "admin":
            return None
        allowed = list(row.allowed_departments or [])
        if row.department and row.department not in allowed:
            allowed.append(row.department)
        return allowed

    @staticmethod
    def serialize(row: UserRole) -> dict[str, Any]:
        return {
            "user_id": row.user_id,
            "role": row.role,
            "department": row.department,
            "allowed_departments": list(row.allowed_departments or []),
            "can_resolve_handoffs": bool(row.can_resolve_handoffs),
            "metadata_json": dict(row.metadata_json or {}),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }


class HandoffService:
    @staticmethod
    def open(
        db: Session,
        *,
        user_id: str,
        question: str,
        session_id: str | None = None,
        message_id: int | None = None,
        reason: str = "manual",
        department: str | None = None,
        context_excerpt: str | None = None,
    ) -> HandoffRequest:
        row = HandoffRequest(
            handoff_id=_new_id("ho"),
            user_id=user_id,
            session_id=session_id,
            message_id=message_id,
            reason=reason,
            department=department,
            question=question[:4000],
            context_excerpt=(context_excerpt or None),
            status="open",
            created_at=utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        HandoffService._announce(row)
        return row

    @staticmethod
    def _announce(row: HandoffRequest) -> None:
        """Best-effort Telegram ping when a handoff lands."""
        try:
            from app.core.config import get_settings
            from app.services.telegram_service import TelegramService
            settings = get_settings()
            if not (settings.report_chat_enabled and settings.default_report_chat_id):
                return
            text = (
                f"\U0001f198 Human handoff requested\n"
                f"Handoff `{row.handoff_id}` from user `{row.user_id}`\n"
                f"Reason: {row.reason}{f' \u00b7 dept {row.department}' if row.department else ''}\n\n"
                f"Question: {row.question[:600]}"
            )
            TelegramService.send_message(settings.default_report_chat_id, text)
        except Exception:
            return

    @staticmethod
    def claim(db: Session, *, handoff_id: str, assignee: str) -> HandoffRequest | None:
        row = db.execute(
            select(HandoffRequest).where(HandoffRequest.handoff_id == handoff_id)
        ).scalar_one_or_none()
        if row is None or row.status != "open":
            return None
        row.status = "claimed"
        row.assignee = assignee
        row.claimed_at = utcnow()
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def resolve(
        db: Session,
        *,
        handoff_id: str,
        assignee: str | None,
        reply: str,
    ) -> HandoffRequest | None:
        row = db.execute(
            select(HandoffRequest).where(HandoffRequest.handoff_id == handoff_id)
        ).scalar_one_or_none()
        if row is None or row.status == "resolved":
            return None
        row.status = "resolved"
        if assignee:
            row.assignee = assignee
        row.reply = reply
        row.resolved_at = utcnow()
        db.commit()
        db.refresh(row)

        # Publish the human reply back into the user's chat session so they
        # see a continuous thread instead of a dangling "we'll get back".
        if row.session_id:
            try:
                from app.models.conversation import MessageRole
                from app.services.memory_service import MemoryService
                MemoryService.add_message(
                    db=db,
                    session_id=row.session_id,
                    platform_user_id=row.user_id,
                    role=MessageRole.assistant,
                    content=f"\U0001f464 Human reply ({assignee or 'team'}):\n\n{reply}",
                    provider="human-handoff",
                    metadata_json={"handoff_id": row.handoff_id, "assignee": assignee},
                )
            except Exception:
                pass
        return row

    @staticmethod
    def list(
        db: Session,
        *,
        status: str | None = None,
        user_id: str | None = None,
        limit: int = 100,
    ) -> list[HandoffRequest]:
        stmt = select(HandoffRequest).order_by(HandoffRequest.created_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(HandoffRequest.status == status)
        if user_id:
            stmt = stmt.where(HandoffRequest.user_id == user_id)
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def serialize(row: HandoffRequest) -> dict[str, Any]:
        return {
            "handoff_id": row.handoff_id,
            "user_id": row.user_id,
            "session_id": row.session_id,
            "message_id": row.message_id,
            "reason": row.reason,
            "department": row.department,
            "question": row.question,
            "context_excerpt": row.context_excerpt,
            "status": row.status,
            "assignee": row.assignee,
            "reply": row.reply,
            "created_at": row.created_at,
            "claimed_at": row.claimed_at,
            "resolved_at": row.resolved_at,
        }

    @staticmethod
    def should_handoff(text: str) -> bool:
        if not text:
            return False
        return bool(HANDOFF_TRIGGER.search(text))
