from __future__ import annotations

import base64
import hashlib
import mimetypes
import random
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.base import utcnow
from app.models.setting import AppSetting
from app.models.uploaded_asset import UploadedAsset
from app.services.upload_service import UploadService

settings = get_settings()


class WhatsAppBetaService:
    EVENT_LOG_KEY = "whatsapp_beta:event_log"
    CURSOR_KEY = "whatsapp_beta:cursor"
    PROCESSED_KEYS = "whatsapp_beta:processed_keys"
    MESSAGE_CLAIM_PREFIX = "whatsapp_beta:msgclaim:"
    PROCESS_LOCK_PREFIX = "whatsapp_beta:processlock:"
    PROFILE_KEY = "whatsapp_beta:profile"
    SEND_STATE_PREFIX = "whatsapp_beta:send_state:"
    MAX_EVENT_LOG_ITEMS = 80
    MAX_PROCESSED_KEYS = 500
    DIRECT_CHAT_SUFFIX = "@s.whatsapp.net"
    GROUP_CHAT_SUFFIX = "@g.us"
    WARNING_TEXT = (
        "WhatsApp blasting is a beta feature. Your number may be limited or banned if you automate too aggressively. "
        "Do not use your main personal number, keep recipients allowlisted and opt-in only, and prefer low-volume alerts or digests."
    )

    @staticmethod
    def is_enabled() -> bool:
        return bool(settings.whatsapp_beta_enabled and settings.whatsapp_beta_bridge_base_url.strip())

    @staticmethod
    def bridge_headers() -> dict[str, str]:
        headers = {"Accept": "application/json"}
        token = settings.whatsapp_beta_bridge_api_token.strip()
        if token:
            headers["X-API-Key"] = token
        return headers

    @staticmethod
    def bridge_base_url() -> str:
        return settings.whatsapp_beta_bridge_base_url.rstrip("/")

    @staticmethod
    def normalize_recipient(value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        if "@" in raw:
            return raw.lower()
        digits = re.sub(r"[^\d]", "", raw)
        if digits.startswith("00"):
            digits = digits[2:]
        # Assume Malaysia local mobile formatting when the user enters a local number like 011xxxxxxx.
        if digits.startswith("0") and len(digits) >= 9:
            digits = f"60{digits[1:]}"
        return digits

    @staticmethod
    def normalize_sender_key(value: str) -> str:
        normalized = WhatsAppBetaService.normalize_recipient(value)
        if normalized.endswith(WhatsAppBetaService.DIRECT_CHAT_SUFFIX):
            return normalized.removesuffix(WhatsAppBetaService.DIRECT_CHAT_SUFFIX)
        return normalized

    @staticmethod
    def _get_setting(db: Session, key: str) -> AppSetting | None:
        return db.scalar(select(AppSetting).where(AppSetting.key == key))

    @staticmethod
    def _get_setting_value(db: Session, key: str, default):
        record = WhatsAppBetaService._get_setting(db, key)
        if record is None:
            return default
        return record.value_json

    @staticmethod
    def _set_setting_value(db: Session, key: str, value: dict | list) -> None:
        record = WhatsAppBetaService._get_setting(db, key)
        if record is None:
            db.add(AppSetting(key=key, value_json=value))
        else:
            record.value_json = value
            record.updated_at = utcnow()
        db.commit()

    @staticmethod
    def _normalize_phone_list(items: list[str] | None) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in items or []:
            cleaned = WhatsAppBetaService.normalize_recipient(item)
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            normalized.append(cleaned)
        return normalized

    @staticmethod
    def _apply_profile_defaults(payload: dict[str, Any]) -> dict[str, Any]:
        sender_phone = WhatsAppBetaService.normalize_sender_key(str(payload.get("sender_phone") or ""))
        default_recipient = WhatsAppBetaService.normalize_recipient(str(payload.get("default_recipient") or ""))
        allowed_senders = WhatsAppBetaService._normalize_phone_list(payload.get("allowed_senders") or [])
        allowed_recipients = WhatsAppBetaService._normalize_phone_list(payload.get("allowed_recipients") or [])

        if default_recipient and default_recipient not in allowed_recipients:
            allowed_recipients.insert(0, default_recipient)
        if sender_phone and sender_phone not in allowed_senders:
            allowed_senders.insert(0, sender_phone)
        # Treat the default recipient as the owner chat number by default so that
        # notification recipients can also talk back to the bot without extra setup.
        if default_recipient and default_recipient not in allowed_senders:
            allowed_senders.insert(0, default_recipient)

        payload["sender_phone"] = sender_phone
        payload["default_recipient"] = default_recipient or None
        payload["allowed_senders"] = allowed_senders
        payload["allowed_recipients"] = allowed_recipients
        return payload

    @staticmethod
    def get_profile(db: Session) -> dict[str, Any]:
        stored = WhatsAppBetaService._get_setting_value(db, WhatsAppBetaService.PROFILE_KEY, {})
        stored = dict(stored) if isinstance(stored, dict) else {}
        default_recipient = WhatsAppBetaService.normalize_recipient(
            str(stored.get("default_recipient") or settings.whatsapp_beta_default_recipient or "").strip()
        )
        sender_phone = WhatsAppBetaService.normalize_sender_key(
            str(stored.get("sender_phone") or settings.whatsapp_beta_sender_phone or "").strip()
        )
        sender_label = str(stored.get("sender_label") or settings.whatsapp_beta_sender_label or "WhatsApp beta sender").strip()
        allowed_senders = WhatsAppBetaService._normalize_phone_list(
            stored.get("allowed_senders") or sorted(settings.whatsapp_beta_sender_allowlist)
        )
        allowed_recipients = WhatsAppBetaService._normalize_phone_list(
            stored.get("allowed_recipients") or sorted(settings.whatsapp_beta_recipient_allowlist)
        )
        return WhatsAppBetaService._apply_profile_defaults({
            "sender_phone": sender_phone,
            "sender_label": sender_label,
            "default_recipient": default_recipient or None,
            "allowed_senders": allowed_senders,
            "allowed_recipients": allowed_recipients,
        })

    @staticmethod
    def update_profile(
        db: Session,
        *,
        sender_phone: str,
        sender_label: str,
        default_recipient: str,
        allowed_senders: list[str],
        allowed_recipients: list[str],
    ) -> dict[str, Any]:
        payload = {
            "sender_phone": WhatsAppBetaService.normalize_sender_key(sender_phone),
            "sender_label": " ".join((sender_label or "").split()).strip() or "WhatsApp beta sender",
            "default_recipient": WhatsAppBetaService.normalize_recipient(default_recipient),
            "allowed_senders": WhatsAppBetaService._normalize_phone_list(allowed_senders),
            "allowed_recipients": WhatsAppBetaService._normalize_phone_list(allowed_recipients),
        }
        payload = WhatsAppBetaService._apply_profile_defaults(payload)
        WhatsAppBetaService._set_setting_value(db, WhatsAppBetaService.PROFILE_KEY, payload)
        return payload

    @staticmethod
    def append_event(
        db: Session,
        *,
        kind: str,
        status: str,
        detail: str,
        recipient: str | None = None,
    ) -> None:
        items = list(WhatsAppBetaService._get_setting_value(db, WhatsAppBetaService.EVENT_LOG_KEY, []))
        items.insert(
            0,
            {
                "kind": kind,
                "status": status,
                "detail": detail,
                "recipient": recipient or "",
                "created_at": utcnow().isoformat(),
            },
        )
        WhatsAppBetaService._set_setting_value(db, WhatsAppBetaService.EVENT_LOG_KEY, items[: WhatsAppBetaService.MAX_EVENT_LOG_ITEMS])

    @staticmethod
    def get_event_log(db: Session) -> list[dict]:
        return list(WhatsAppBetaService._get_setting_value(db, WhatsAppBetaService.EVENT_LOG_KEY, []))

    @staticmethod
    def bridge_health() -> dict[str, Any]:
        if not WhatsAppBetaService.is_enabled():
            return {
                "reachable": False,
                "connected": False,
                "message": "WhatsApp beta is disabled.",
                "connected_sender_jid": None,
                "connected_sender_phone": None,
                "pairing_required": False,
                "qr_available": False,
            }
        try:
            with httpx.Client(timeout=10.0, headers=WhatsAppBetaService.bridge_headers()) as client:
                response = client.get(f"{WhatsAppBetaService.bridge_base_url()}/health")
            if response.status_code == 200:
                payload = response.json()
                connected = bool(payload.get("connected", False))
                connected_sender_jid = str(payload.get("connected_sender_jid") or "").strip() or None
                connected_sender_phone = WhatsAppBetaService.normalize_sender_key(str(payload.get("connected_sender_phone") or connected_sender_jid or ""))
                pairing_required = bool(payload.get("pairing_required", False))
                return {
                    "reachable": True,
                    "connected": connected,
                    "message": str(payload.get("message", "Bridge reachable")).strip() or "Bridge reachable",
                    "connected_sender_jid": connected_sender_jid,
                    "connected_sender_phone": connected_sender_phone or None,
                    "pairing_required": pairing_required,
                    "qr_available": bool(payload.get("qr_available", False)),
                }
            return {
                "reachable": False,
                "connected": False,
                "message": f"Bridge HTTP {response.status_code}",
                "connected_sender_jid": None,
                "connected_sender_phone": None,
                "pairing_required": False,
                "qr_available": False,
            }
        except Exception as exc:
            return {
                "reachable": False,
                "connected": False,
                "message": str(exc),
                "connected_sender_jid": None,
                "connected_sender_phone": None,
                "pairing_required": False,
                "qr_available": False,
            }

    @staticmethod
    def status(db: Session) -> dict[str, Any]:
        bridge = WhatsAppBetaService.bridge_health()
        profile = WhatsAppBetaService.get_profile(db)
        return {
            "enabled": WhatsAppBetaService.is_enabled(),
            "bridge_reachable": bridge["reachable"],
            "bridge_connected": bridge["connected"],
            "bridge_message": bridge["message"],
            "bridge_pairing_required": bridge["pairing_required"],
            "bridge_qr_available": bridge["qr_available"],
            "inbound_enabled": bool(settings.whatsapp_beta_allow_inbound),
            "blasting_enabled": bool(settings.whatsapp_beta_allow_blasting),
            "warning": WhatsAppBetaService.WARNING_TEXT,
            "bridge_base_url": settings.whatsapp_beta_bridge_base_url,
            "sender_phone": profile["sender_phone"] or None,
            "sender_label": profile["sender_label"],
            "connected_sender_phone": bridge["connected_sender_phone"],
            "connected_sender_jid": bridge["connected_sender_jid"],
            "allowlisted_senders": profile["allowed_senders"],
            "allowlisted_recipients": profile["allowed_recipients"],
            "default_recipient": profile["default_recipient"],
            "recent_events": WhatsAppBetaService.get_event_log(db)[:20],
        }

    @staticmethod
    def fetch_bridge_qr() -> tuple[bytes, str]:
        if not WhatsAppBetaService.is_enabled():
            raise RuntimeError("WhatsApp beta is disabled.")
        with httpx.Client(timeout=15.0, headers=WhatsAppBetaService.bridge_headers()) as client:
            response = client.get(f"{WhatsAppBetaService.bridge_base_url()}/qr")
        if response.status_code != 200:
            detail = f"Bridge HTTP {response.status_code}"
            try:
                payload = response.json()
                detail = str(payload.get("message") or payload.get("detail") or detail)
            except Exception:
                text = response.text.strip()
                if text:
                    detail = text
            raise RuntimeError(detail)
        content_type = response.headers.get("content-type", "image/png")
        return response.content, content_type

    @staticmethod
    def is_allowed_sender(db: Session, sender: str) -> bool:
        allowlist = set(WhatsAppBetaService.get_profile(db).get("allowed_senders") or [])
        if not allowlist:
            return False
        normalized_sender = WhatsAppBetaService.normalize_sender_key(sender)
        if normalized_sender in allowlist:
            return True
        direct_jid = f"{normalized_sender}{WhatsAppBetaService.DIRECT_CHAT_SUFFIX}"
        return direct_jid in allowlist

    @staticmethod
    def is_allowed_recipient(db: Session, recipient: str) -> bool:
        normalized = WhatsAppBetaService.normalize_recipient(recipient)
        if not normalized:
            return False
        profile = WhatsAppBetaService.get_profile(db)
        default_recipient = WhatsAppBetaService.normalize_recipient(profile.get("default_recipient") or "")
        recipient_phone = WhatsAppBetaService.normalize_sender_key(recipient)
        allowlist = set(profile.get("allowed_recipients") or [])
        if (
            default_recipient
            and (
                normalized == default_recipient
                or recipient_phone == default_recipient
                or normalized == f"{default_recipient}{WhatsAppBetaService.DIRECT_CHAT_SUFFIX}"
            )
        ):
            return True
        if not allowlist:
            return False
        if normalized in allowlist or recipient_phone in allowlist:
            return True
        direct_jid = f"{recipient_phone}{WhatsAppBetaService.DIRECT_CHAT_SUFFIX}" if recipient_phone else ""
        return bool(direct_jid and direct_jid in allowlist)

    @staticmethod
    def _send_state_key(recipient: str) -> str:
        normalized = WhatsAppBetaService.normalize_recipient(recipient)
        return f"{WhatsAppBetaService.SEND_STATE_PREFIX}{normalized}"

    @staticmethod
    def _get_send_state(db: Session, recipient: str) -> dict[str, Any]:
        value = WhatsAppBetaService._get_setting_value(db, WhatsAppBetaService._send_state_key(recipient), {})
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _set_send_state(db: Session, recipient: str, value: dict[str, Any]) -> None:
        WhatsAppBetaService._set_setting_value(db, WhatsAppBetaService._send_state_key(recipient), value)

    @staticmethod
    def _message_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]

    @staticmethod
    def _effective_cooldown_seconds(category: str) -> int:
        if category == "reply":
            return max(6, settings.whatsapp_beta_reply_min_seconds)
        return max(6, settings.whatsapp_beta_recipient_cooldown_seconds)

    @staticmethod
    def _duplicate_window_seconds(category: str) -> int:
        if category == "reply":
            return max(180, settings.whatsapp_beta_recipient_cooldown_seconds)
        return max(600, settings.whatsapp_beta_recipient_cooldown_seconds)

    @staticmethod
    def _sanitize_reply_for_whatsapp(message: str, *, provider: str | None = None) -> str:
        trimmed = " ".join((message or "").split()).strip()
        lowered = trimmed.lower()
        if not trimmed:
            return "I hit a temporary WhatsApp issue just now. Please try again in a moment."

        looks_like_model_error = (
            provider in {"attachment-error", "llm-error"}
            or "http://ollama:" in lowered
            or "503 service unavailable" in lowered
            or "/api/chat failed" in lowered
            or "/api/generate failed" in lowered
            or "/v1/chat/completions failed" in lowered
            or "for more information check" in lowered
            or "timed out" in lowered
        )
        if looks_like_model_error:
            if "uploaded image" in lowered or "uploaded file" in lowered or "analyze" in lowered:
                return (
                    "I couldn't analyze that file cleanly right now because the AI model is temporarily busy. "
                    "Please try again in a minute."
                )
            return (
                "I hit a temporary AI model issue while handling your WhatsApp request. "
                "Please try again in a minute."
            )

        if len(trimmed) > 1200:
            trimmed = trimmed[:1190].rstrip() + "..."
        return trimmed

    @staticmethod
    def send_message_now(
        db: Session,
        *,
        recipient: str,
        message: str,
        category: str = "general",
        bypass_cooldown: bool = False,
    ) -> tuple[bool, str]:
        if not WhatsAppBetaService.is_enabled():
            return False, "WhatsApp beta is disabled."

        normalized_recipient = WhatsAppBetaService.normalize_recipient(recipient)
        if not WhatsAppBetaService.is_allowed_recipient(db, normalized_recipient):
            return False, f"Recipient `{recipient}` is not allowlisted for WhatsApp beta."

        trimmed = " ".join(message.strip().split())
        if not trimmed:
            return False, "Message body is empty."
        if len(trimmed) > 3500:
            trimmed = trimmed[:3490].rstrip() + "..."

        now = utcnow()
        state = WhatsAppBetaService._get_send_state(db, normalized_recipient)
        cooldown_seconds = WhatsAppBetaService._effective_cooldown_seconds(category)
        last_sent_raw = str(state.get("last_sent_at", "")).strip()
        last_hash = str(state.get("last_hash", "")).strip()
        last_category = str(state.get("last_category", "")).strip()
        last_sent_at = WhatsAppBetaService._parse_iso_datetime(last_sent_raw)
        message_hash = WhatsAppBetaService._message_hash(trimmed)

        if not bypass_cooldown and last_sent_at:
            earliest = last_sent_at + timedelta(seconds=cooldown_seconds)
            if earliest > now:
                return False, f"Recipient cooldown active until {earliest.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}."

        if last_hash == message_hash and last_category == category and last_sent_at:
            duplicate_until = last_sent_at + timedelta(seconds=WhatsAppBetaService._duplicate_window_seconds(category))
            if duplicate_until > now:
                return False, "A matching WhatsApp reply was already sent recently."

        today = now.astimezone(timezone.utc).strftime("%Y-%m-%d")
        daily_bucket = str(state.get("daily_bucket", "")).strip()
        daily_count = int(state.get("daily_count", 0) or 0)
        if daily_bucket != today:
            daily_bucket = today
            daily_count = 0
        if daily_count >= settings.whatsapp_beta_daily_limit_per_recipient:
            return False, f"Daily WhatsApp limit reached for `{normalized_recipient}`."

        payload = {"recipient": normalized_recipient, "message": trimmed}
        try:
            with httpx.Client(timeout=20.0, headers=WhatsAppBetaService.bridge_headers()) as client:
                response = client.post(f"{WhatsAppBetaService.bridge_base_url()}/send", json=payload)
            if response.status_code != 200:
                WhatsAppBetaService.append_event(
                    db,
                    kind="send",
                    status="failed",
                    recipient=normalized_recipient,
                    detail=f"Bridge HTTP {response.status_code}: {response.text[:240]}",
                )
                return False, f"Bridge HTTP {response.status_code}: {response.text[:240]}"
            result = response.json()
        except Exception as exc:
            WhatsAppBetaService.append_event(
                db,
                kind="send",
                status="failed",
                recipient=normalized_recipient,
                detail=str(exc),
            )
            return False, str(exc)

        success = bool(result.get("success", False))
        status_message = str(result.get("message", "Unknown response")).strip()
        if not success:
            WhatsAppBetaService.append_event(
                db,
                kind="send",
                status="failed",
                recipient=normalized_recipient,
                detail=status_message,
            )
            return False, status_message

        state.update(
            {
                "last_sent_at": now.isoformat(),
                "last_hash": message_hash,
                "last_category": category,
                "daily_bucket": daily_bucket,
                "daily_count": daily_count + 1,
            }
        )
        WhatsAppBetaService._set_send_state(db, normalized_recipient, state)
        WhatsAppBetaService.append_event(
            db,
            kind="send",
            status="sent",
            recipient=normalized_recipient,
            detail=status_message,
        )
        return True, status_message

    @staticmethod
    def _queue_task(name: str, kwargs: dict[str, Any], countdown: int = 0) -> None:
        from app.core.celery_app import celery_app

        celery_app.send_task(name, kwargs=kwargs, countdown=max(0, countdown))

    @staticmethod
    def queue_message(
        recipient: str,
        message: str,
        *,
        category: str = "general",
        countdown: int | None = None,
        bypass_cooldown: bool = False,
    ) -> int:
        if countdown is None:
            if category == "reply":
                countdown = random.randint(
                    max(0, settings.whatsapp_beta_reply_min_seconds),
                    max(settings.whatsapp_beta_reply_min_seconds, settings.whatsapp_beta_reply_max_seconds),
                )
            else:
                countdown = random.randint(
                    max(0, settings.whatsapp_beta_jitter_min_seconds),
                    max(settings.whatsapp_beta_jitter_min_seconds, settings.whatsapp_beta_jitter_max_seconds),
                )
        WhatsAppBetaService._queue_task(
            "app.workers.jobs.send_whatsapp_message",
            {
                "recipient": recipient,
                "message": message,
                "category": category,
                "bypass_cooldown": bypass_cooldown,
            },
            countdown=countdown,
        )
        return countdown

    @staticmethod
    def queue_blast(
        *,
        recipients: list[str],
        message: str,
    ) -> list[int]:
        delays: list[int] = []
        cursor = 0
        for recipient in recipients:
            step = random.randint(
                max(6, settings.whatsapp_beta_jitter_min_seconds),
                max(max(6, settings.whatsapp_beta_jitter_min_seconds), settings.whatsapp_beta_jitter_max_seconds),
            )
            cursor += step
            delays.append(cursor)
            WhatsAppBetaService.queue_message(recipient, message, category="blast", countdown=cursor)
        return delays

    @staticmethod
    def _get_cursor(db: Session) -> str:
        value = WhatsAppBetaService._get_setting_value(db, WhatsAppBetaService.CURSOR_KEY, {})
        if isinstance(value, dict):
            return str(value.get("since", "")).strip()
        return ""

    @staticmethod
    def _set_cursor(db: Session, since: str) -> None:
        WhatsAppBetaService._set_setting_value(db, WhatsAppBetaService.CURSOR_KEY, {"since": since})

    @staticmethod
    def _get_processed_keys(db: Session) -> list[str]:
        value = WhatsAppBetaService._get_setting_value(db, WhatsAppBetaService.PROCESSED_KEYS, [])
        return [str(item) for item in value if str(item).strip()]

    @staticmethod
    def _remember_processed_key(db: Session, key: str) -> None:
        keys = WhatsAppBetaService._get_processed_keys(db)
        if key in keys:
            return
        keys.insert(0, key)
        WhatsAppBetaService._set_setting_value(db, WhatsAppBetaService.PROCESSED_KEYS, keys[: WhatsAppBetaService.MAX_PROCESSED_KEYS])

    @staticmethod
    def _message_claim_key(message_key: str) -> str:
        digest = hashlib.sha1(message_key.encode("utf-8")).hexdigest()[:32]
        return f"{WhatsAppBetaService.MESSAGE_CLAIM_PREFIX}{digest}"

    @staticmethod
    def _claim_message_once(db: Session, message_key: str) -> bool:
        claim_key = WhatsAppBetaService._message_claim_key(message_key)
        if WhatsAppBetaService._get_setting(db, claim_key) is not None:
            return False
        try:
            db.add(
                AppSetting(
                    key=claim_key,
                    value_json={
                        "message_key": message_key,
                        "claimed_at": utcnow().isoformat(),
                    },
                )
            )
            db.commit()
            return True
        except IntegrityError:
            db.rollback()
            return False

    @staticmethod
    def _process_lock_key(message_key: str) -> str:
        digest = hashlib.sha1(message_key.encode("utf-8")).hexdigest()[:32]
        return f"{WhatsAppBetaService.PROCESS_LOCK_PREFIX}{digest}"

    @staticmethod
    def _acquire_process_lock(db: Session, message_key: str) -> bool:
        lock_key = WhatsAppBetaService._process_lock_key(message_key)
        if WhatsAppBetaService._get_setting(db, lock_key) is not None:
            return False
        try:
            db.add(
                AppSetting(
                    key=lock_key,
                    value_json={
                        "message_key": message_key,
                        "locked_at": utcnow().isoformat(),
                    },
                )
            )
            db.commit()
            return True
        except IntegrityError:
            db.rollback()
            return False

    @staticmethod
    def fetch_recent_messages(db: Session, limit: int = 40) -> list[dict[str, Any]]:
        if not WhatsAppBetaService.is_enabled():
            return []
        since = WhatsAppBetaService._get_cursor(db)
        params = {"limit": max(1, min(limit, 100))}
        if since:
            params["since"] = since
        try:
            with httpx.Client(timeout=20.0, headers=WhatsAppBetaService.bridge_headers()) as client:
                response = client.get(f"{WhatsAppBetaService.bridge_base_url()}/recent-messages", params=params)
            if response.status_code != 200:
                WhatsAppBetaService.append_event(
                    db,
                    kind="poll",
                    status="failed",
                    detail=f"Bridge HTTP {response.status_code}: {response.text[:200]}",
                )
                return []
            payload = response.json()
            items = payload.get("messages", [])
            if not isinstance(items, list):
                return []
            return [item for item in items if isinstance(item, dict)]
        except Exception as exc:
            WhatsAppBetaService.append_event(db, kind="poll", status="failed", detail=str(exc))
            return []

    @staticmethod
    def _download_media_asset(
        db: Session,
        *,
        user_id: str,
        session_id: str,
        message_id: str,
        chat_jid: str,
        media_type: str,
        filename: str,
    ) -> UploadedAsset | None:
        try:
            with httpx.Client(timeout=30.0, headers=WhatsAppBetaService.bridge_headers()) as client:
                response = client.post(
                    f"{WhatsAppBetaService.bridge_base_url()}/download",
                    json={"message_id": message_id, "chat_jid": chat_jid},
                )
        except Exception as exc:
            WhatsAppBetaService.append_event(
                db,
                kind="media",
                status="failed",
                recipient=chat_jid,
                detail=f"Could not download WhatsApp media: {exc}",
            )
            return None

        if response.status_code != 200:
            detail = f"Bridge HTTP {response.status_code}: {response.text[:220]}"
            WhatsAppBetaService.append_event(
                db,
                kind="media",
                status="failed",
                recipient=chat_jid,
                detail=detail,
            )
            return None

        try:
            payload = response.json()
        except Exception as exc:
            WhatsAppBetaService.append_event(
                db,
                kind="media",
                status="failed",
                recipient=chat_jid,
                detail=f"Invalid media download payload: {exc}",
            )
            return None

        if not payload.get("success"):
            WhatsAppBetaService.append_event(
                db,
                kind="media",
                status="failed",
                recipient=chat_jid,
                detail=str(payload.get("message") or "Unknown WhatsApp media download failure."),
            )
            return None

        content_base64 = str(payload.get("content_base64") or "").strip()
        if not content_base64:
            WhatsAppBetaService.append_event(
                db,
                kind="media",
                status="failed",
                recipient=chat_jid,
                detail="WhatsApp media download returned no file bytes.",
            )
            return None

        try:
            raw_bytes = base64.b64decode(content_base64)
        except Exception as exc:
            WhatsAppBetaService.append_event(
                db,
                kind="media",
                status="failed",
                recipient=chat_jid,
                detail=f"Could not decode WhatsApp media bytes: {exc}",
            )
            return None

        def sniff_document_extension_and_mime(filename_hint: str, mime_hint: str, data: bytes) -> tuple[str, str]:
            resolved_name = str(filename_hint or "").strip() or "whatsapp-document"
            resolved_mime = str(mime_hint or "").strip() or "application/octet-stream"

            suffix = Path(resolved_name).suffix.lower()
            if suffix:
                guessed = mimetypes.guess_type(resolved_name)[0]
                return resolved_name, resolved_mime if resolved_mime not in {"document", "application/octet-stream"} else (guessed or resolved_mime)

            # Magic-byte sniffing for the common cases we see in WhatsApp document uploads.
            if data.startswith(b"%PDF-"):
                return f"{resolved_name}.pdf", "application/pdf"
            if data.startswith(b"\xFF\xD8\xFF"):
                return f"{resolved_name}.jpg", "image/jpeg"
            if data.startswith(b"\x89PNG\r\n\x1a\n"):
                return f"{resolved_name}.png", "image/png"

            # Default fallback
            return resolved_name, resolved_mime if resolved_mime != "document" else "application/octet-stream"

        resolved_filename = str(payload.get("filename") or filename or "").strip()
        if not resolved_filename:
            extension = mimetypes.guess_extension(str(payload.get("media_type") or media_type or "").strip()) or ".bin"
            resolved_filename = f"whatsapp-media-{message_id}{extension}"
        mime_type = (
            str(payload.get("media_type") or media_type or "").strip()
            or mimetypes.guess_type(resolved_filename)[0]
            or "application/octet-stream"
        )
        if str(media_type or "").strip().lower() == "document" or str(mime_type).strip().lower() in {"document", "application/octet-stream"}:
            resolved_filename, mime_type = sniff_document_extension_and_mime(resolved_filename, mime_type, raw_bytes)

        try:
            asset = UploadService.create_asset_from_bytes(
                db=db,
                platform_user_id=user_id,
                session_id=session_id,
                source="whatsapp",
                original_filename=Path(resolved_filename).name,
                mime_type=mime_type,
                raw_bytes=raw_bytes,
                metadata_json={
                    "chat_jid": chat_jid,
                    "message_id": message_id,
                    "source": "whatsapp-beta",
                },
            )
        except Exception as exc:
            WhatsAppBetaService.append_event(
                db,
                kind="media",
                status="failed",
                recipient=chat_jid,
                detail=f"Could not store WhatsApp media as an asset: {exc}",
            )
            return None

        WhatsAppBetaService.append_event(
            db,
            kind="media",
            status="stored",
            recipient=chat_jid,
            detail=f"Stored WhatsApp media as asset `{asset.asset_id}`.",
        )
        return asset

    @staticmethod
    def process_inbound_messages(db: Session) -> dict[str, int]:
        if not WhatsAppBetaService.is_enabled() or not settings.whatsapp_beta_allow_inbound:
            return {"processed": 0, "ignored": 0}

        items = WhatsAppBetaService.fetch_recent_messages(db, limit=60)
        if not items:
            return {"processed": 0, "ignored": 0}

        items = sorted(items, key=lambda item: str(item.get("timestamp", "")).strip())
        processed_keys = set(WhatsAppBetaService._get_processed_keys(db))
        processed = 0
        ignored = 0
        latest_seen = WhatsAppBetaService._get_cursor(db)

        for item in items:
            message_id = str(item.get("id", "")).strip()
            chat_jid = str(item.get("chat_jid", "")).strip()
            key = f"{chat_jid}:{message_id}"
            timestamp = str(item.get("timestamp", "")).strip()
            if timestamp and timestamp > latest_seen:
                latest_seen = timestamp
            if not message_id or not chat_jid or key in processed_keys:
                continue
            if not WhatsAppBetaService._claim_message_once(db, key):
                continue

            is_from_me = bool(item.get("is_from_me", False))
            content = str(item.get("content", "")).strip()
            sender = str(item.get("sender", "")).strip()
            media_type = str(item.get("media_type", "")).strip()
            if is_from_me or (not content and not media_type):
                WhatsAppBetaService._remember_processed_key(db, key)
                processed_keys.add(key)
                continue
            if chat_jid.endswith(WhatsAppBetaService.GROUP_CHAT_SUFFIX):
                ignored += 1
                WhatsAppBetaService._remember_processed_key(db, key)
                processed_keys.add(key)
                WhatsAppBetaService.append_event(
                    db,
                    kind="inbound",
                    status="ignored",
                    recipient=chat_jid,
                    detail="Ignored group message for safety.",
                )
                continue
            if not WhatsAppBetaService.is_allowed_sender(db, sender or chat_jid):
                ignored += 1
                WhatsAppBetaService._remember_processed_key(db, key)
                processed_keys.add(key)
                WhatsAppBetaService.append_event(
                    db,
                    kind="inbound",
                    status="ignored",
                    recipient=chat_jid,
                    detail=f"Sender `{sender or chat_jid}` is not in the inbound allowlist.",
                )
                continue

            try:
                WhatsAppBetaService._queue_task(
                    "app.workers.jobs.process_whatsapp_inbound_message",
                    {
                        "message_id": message_id,
                        "chat_jid": chat_jid,
                        "sender": sender or chat_jid,
                        "content": content,
                        "media_type": media_type,
                        "filename": str(item.get("filename", "")).strip(),
                    },
                )
            except Exception as exc:
                WhatsAppBetaService.append_event(
                    db,
                    kind="inbound",
                    status="failed",
                    recipient=chat_jid,
                    detail=f"Could not queue inbound WhatsApp processing: {exc}",
                )
                continue

            processed += 1
            WhatsAppBetaService._remember_processed_key(db, key)
            processed_keys.add(key)
            WhatsAppBetaService.append_event(
                db,
                kind="inbound",
                status="queued",
                recipient=chat_jid,
                detail=f"Queued inbound WhatsApp processing for `{WhatsAppBetaService.normalize_sender_key(sender or chat_jid)}`.",
            )

        if latest_seen:
            WhatsAppBetaService._set_cursor(db, latest_seen)

        return {"processed": processed, "ignored": ignored}

    @staticmethod
    def process_inbound_message(
        db: Session,
        *,
        message_id: str,
        chat_jid: str,
        sender: str,
        content: str,
        media_type: str = "",
        filename: str = "",
    ) -> dict[str, Any]:
        from app.services.message_service import MessageService

        message_key = f"{chat_jid}:{message_id}"
        if not WhatsAppBetaService._acquire_process_lock(db, message_key):
            return {
                "success": False,
                "duplicate": True,
                "reply_recipient": WhatsAppBetaService.normalize_sender_key(sender or chat_jid),
                "provider": "whatsapp-deduped",
                "asset_ids": [],
            }

        sender_key = WhatsAppBetaService.normalize_sender_key(sender or chat_jid)
        session_id = f"whatsapp:{chat_jid}"
        user_id = f"whatsapp:{sender_key}"
        attachment_asset_ids: list[str] = []
        if media_type:
            asset = WhatsAppBetaService._download_media_asset(
                db,
                user_id=user_id,
                session_id=session_id,
                message_id=message_id,
                chat_jid=chat_jid,
                media_type=media_type,
                filename=filename,
            )
            if asset is not None:
                attachment_asset_ids.append(asset.asset_id)

        result = MessageService.process_user_message(
            db=db,
            user_id=user_id,
            text=content,
            username=sender_key,
            session_id=session_id,
            attachment_asset_ids=attachment_asset_ids,
        )
        reply = WhatsAppBetaService._sanitize_reply_for_whatsapp(result.reply, provider=result.provider)
        if result.attachments:
            urls = [att.explicit_public_url for att in result.attachments if getattr(att, "explicit_public_url", None)]
            lowered = (content or "").lower()
            if urls and ("invoice" in lowered or "inv" in lowered) and len(urls) == 1:
                reply = f"Here’s the PDF link:\n{urls[0]}"
            elif urls:
                reply = f"{reply}\n\nFiles:\n" + "\n".join(f"- {url}" for url in urls)
        reply_recipient = sender_key or sender or chat_jid
        WhatsAppBetaService.queue_message(reply_recipient, reply, category="reply")
        WhatsAppBetaService.append_event(
            db,
            kind="inbound",
            status="processed",
            recipient=reply_recipient,
            detail=f"Processed inbound chat from `{sender_key}`.",
        )
        return {
            "success": True,
            "reply_recipient": reply_recipient,
            "provider": result.provider,
            "asset_ids": attachment_asset_ids,
        }

    @staticmethod
    def queue_daily_report(db: Session, report_text: str) -> bool:
        recipient = str(WhatsAppBetaService.get_profile(db).get("default_recipient") or "").strip()
        if not recipient or not WhatsAppBetaService.is_enabled():
            return False
        WhatsAppBetaService.queue_message(recipient, report_text, category="daily_report")
        return True

    @staticmethod
    def queue_agent_alert(db: Session, agent_name: str, status: str, detail: str) -> bool:
        recipient = str(WhatsAppBetaService.get_profile(db).get("default_recipient") or "").strip()
        if not recipient or not WhatsAppBetaService.is_enabled():
            return False
        title = f"Agent update: {agent_name} is now {status}"
        body = f"{title}\n{detail}"
        WhatsAppBetaService.queue_message(recipient, body, category=f"agent_{status}")
        return True

    @staticmethod
    def _parse_iso_datetime(value: str) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
