from datetime import datetime

from pydantic import BaseModel, Field


class WhatsAppStatusResponse(BaseModel):
    enabled: bool
    bridge_reachable: bool
    bridge_connected: bool = False
    bridge_pairing_required: bool = False
    bridge_qr_available: bool = False
    inbound_enabled: bool
    blasting_enabled: bool
    warning: str
    bridge_base_url: str
    sender_phone: str | None = None
    sender_label: str | None = None
    connected_sender_phone: str | None = None
    connected_sender_jid: str | None = None
    allowlisted_senders: list[str] = Field(default_factory=list)
    allowlisted_recipients: list[str] = Field(default_factory=list)
    default_recipient: str | None = None
    recent_events: list[dict] = Field(default_factory=list)


class WhatsAppProfileUpdateRequest(BaseModel):
    sender_phone: str = Field(default="", max_length=120)
    sender_label: str = Field(default="WhatsApp beta sender", max_length=120)
    default_recipient: str = Field(default="", max_length=120)
    allowed_senders: list[str] = Field(default_factory=list)
    allowed_recipients: list[str] = Field(default_factory=list)


class WhatsAppSendRequest(BaseModel):
    recipient: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=4000)
    warning_acknowledged: bool = False


class WhatsAppBlastRequest(BaseModel):
    recipients: list[str] = Field(default_factory=list)
    message: str = Field(min_length=1, max_length=4000)
    warning_acknowledged: bool = False


class WhatsAppQueuedSendResponse(BaseModel):
    queued: bool
    message: str
    scheduled_count: int = 0
    delays_seconds: list[int] = Field(default_factory=list)


class WhatsAppEventLogEntry(BaseModel):
    kind: str
    status: str
    recipient: str | None = None
    detail: str
    created_at: datetime
