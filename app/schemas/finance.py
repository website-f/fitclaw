from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.finance import FinanceRuleKind


class FinanceEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entry_id: str
    title: str
    merchant_name: str | None = None
    category: str | None = None
    currency: str
    amount_cents: int
    occurred_at: datetime | None = None
    payment_method: str | None = None
    notes: str | None = None
    source: str
    metadata_json: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class FinanceRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rule_id: str
    name: str
    kind: FinanceRuleKind
    is_active: bool
    criteria_json: dict = Field(default_factory=dict)
    action_json: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class FinanceRuleCreateRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=160)
    kind: FinanceRuleKind
    is_active: bool = True
    criteria_json: dict = Field(default_factory=dict)
    action_json: dict = Field(default_factory=dict)


class FinanceOverviewResponse(BaseModel):
    user_id: str
    default_currency: str
    display_currency: str
    today_total_cents: int
    month_total_cents: int
    month_entry_count: int
    fx_rates: dict[str, float] = Field(default_factory=dict)
    fx_as_of: str | None = None
    recent_entries: list[FinanceEntryResponse] = Field(default_factory=list)
    active_rules: list[FinanceRuleResponse] = Field(default_factory=list)
