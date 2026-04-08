from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.base import utcnow
from app.models.setting import AppSetting

settings = get_settings()


class ChatApprovalService:
    KEY_PREFIX = "pending_chat_approval:"

    @staticmethod
    def build_key(user_id: str, session_id: str) -> str:
        return f"{ChatApprovalService.KEY_PREFIX}{user_id}:{session_id}"

    @staticmethod
    def get_pending(db: Session, user_id: str, session_id: str) -> dict | None:
        record = db.scalar(select(AppSetting).where(AppSetting.key == ChatApprovalService.build_key(user_id, session_id)))
        if record is None:
            return None

        payload = record.value_json or {}
        expires_at_raw = str(payload.get("expires_at", "")).strip()
        if expires_at_raw:
            try:
                expires_at = _parse_iso_datetime(expires_at_raw)
            except ValueError:
                expires_at = None
            if expires_at and expires_at <= utcnow():
                db.delete(record)
                db.commit()
                return None
        return payload

    @staticmethod
    def set_pending(db: Session, user_id: str, session_id: str, payload: dict) -> dict:
        key = ChatApprovalService.build_key(user_id, session_id)
        record = db.scalar(select(AppSetting).where(AppSetting.key == key))
        issued_at = utcnow()
        expires_at = issued_at + timedelta(seconds=settings.chat_high_risk_confirmation_ttl_seconds)
        value = {
            **payload,
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        if record is None:
            record = AppSetting(key=key, value_json=value)
            db.add(record)
        else:
            record.value_json = value
        db.commit()
        return value

    @staticmethod
    def clear_pending(db: Session, user_id: str, session_id: str) -> bool:
        record = db.scalar(select(AppSetting).where(AppSetting.key == ChatApprovalService.build_key(user_id, session_id)))
        if record is None:
            return False
        db.delete(record)
        db.commit()
        return True


def _parse_iso_datetime(value: str):
    from datetime import datetime

    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Naive datetime is not allowed.")
    return parsed
