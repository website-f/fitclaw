from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import re
import secrets
import threading
from typing import Any

import httpx
from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.base import utcnow
from app.models.finance import FinanceEntry, FinanceRule, FinanceRuleKind
from app.models.uploaded_asset import UploadedAsset, UploadedAssetKind
from app.schemas.finance import FinanceOverviewResponse
from app.services.attachment_service import AttachmentService
from app.services.command_result import CommandResult
from app.services.llm_service import LLMService

settings = get_settings()


class FinanceService:
    _fx_lock = threading.Lock()
    _fx_rates_cache: dict[str, Any] = {"rates": {}, "as_of": None, "fetched_at": None}
    _fx_cache_ttl_seconds = 900
    # Fallback rates (base USD) used when live FX API is unavailable.
    _fx_fallback_rates: dict[str, float] = {
        "USD": 1.0,
        "MYR": 3.95,
        "SGD": 1.35,
        "EUR": 0.92,
        "GBP": 0.79,
        "JPY": 153.0,
    }

    @staticmethod
    def _normalize_fx_rates(raw_rates: dict[str, Any]) -> dict[str, float]:
        normalized: dict[str, float] = {"USD": 1.0}
        for code, value in (raw_rates or {}).items():
            code_upper = str(code).upper().strip()
            if not code_upper:
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if numeric > 0:
                normalized[code_upper] = numeric
        return normalized
    RECEIPT_HINT_PATTERN = re.compile(
        r"\b(receipt|expense|expenses|spending|spent|purchase|bill|invoice|finance|budget|track this|log this)\b",
        re.IGNORECASE,
    )
    SPENDING_SUMMARY_PATTERN = re.compile(
        r"\b(spending|expenses?|budget|finance report|spent)\b",
        re.IGNORECASE,
    )
    RECENT_EXPENSES_PATTERN = re.compile(
        r"\b(list|show|recent|latest)\b.*\b(expenses?|receipts?|spending)\b",
        re.IGNORECASE,
    )
    CATEGORY_RULE_PATTERN = re.compile(
        r"(?:when|if)\s+(?:merchant|shop|vendor)\s+contains\s+(?P<keyword>[a-z0-9 .&'_-]+)\s+(?:set|mark)\s+(?:the\s+)?category\s+(?:to|as)\s+(?P<category>[a-z0-9 &/_-]+)",
        re.IGNORECASE,
    )
    THRESHOLD_RULE_PATTERN = re.compile(
        r"(?:alert|warn)\s+me\s+(?:when|if)\s+(?:(?P<scope>daily|weekly|monthly)\s+)?(?:spending|expenses?)"
        r"(?:\s+for\s+(?P<category>[a-z0-9 &/_-]+))?\s+(?:goes\s+)?(?:above|over|beyond)\s+(?P<amount>(?:rm|myr)?\s*[\d,]+(?:\.\d{1,2})?)",
        re.IGNORECASE,
    )
    DELETE_RULE_PATTERN = re.compile(r"\bdelete\b.*\brule\b.*\b(?P<rule_id>fr_[a-z0-9]+)\b", re.IGNORECASE)
    DELETE_ENTRY_PATTERN = re.compile(r"\bdelete\b.*\b(?:expense|entry|receipt)\b.*\b(?P<entry_id>fe_[a-z0-9]+)\b", re.IGNORECASE)

    @staticmethod
    def _make_entry_id() -> str:
        return f"fe_{secrets.token_hex(6)}"

    @staticmethod
    def _make_rule_id() -> str:
        return f"fr_{secrets.token_hex(6)}"

    @staticmethod
    def list_entries(
        db: Session,
        *,
        user_id: str | None,
        limit: int = 50,
        category: str | None = None,
        period: str | None = None,
    ) -> list[FinanceEntry]:
        stmt = select(FinanceEntry)
        if user_id:
            stmt = stmt.where(FinanceEntry.platform_user_id == user_id)
        if category:
            stmt = stmt.where(func.lower(FinanceEntry.category) == category.strip().lower())
        start = FinanceService._period_start(period)
        if start is not None:
            stmt = stmt.where(FinanceEntry.occurred_at >= start)
        stmt = stmt.order_by(FinanceEntry.occurred_at.desc(), FinanceEntry.created_at.desc()).limit(limit)
        return list(db.scalars(stmt).all())

    @staticmethod
    def list_rules(db: Session, *, user_id: str | None, active_only: bool = False) -> list[FinanceRule]:
        stmt = select(FinanceRule)
        if user_id:
            stmt = stmt.where(FinanceRule.platform_user_id == user_id)
        stmt = stmt.order_by(FinanceRule.updated_at.desc())
        if active_only:
            stmt = stmt.where(FinanceRule.is_active.is_(True))
        return list(db.scalars(stmt).all())

    @staticmethod
    def create_rule(
        db: Session,
        *,
        user_id: str,
        name: str,
        kind: FinanceRuleKind,
        criteria_json: dict[str, Any],
        action_json: dict[str, Any],
        is_active: bool = True,
    ) -> FinanceRule:
        rule = FinanceRule(
            rule_id=FinanceService._make_rule_id(),
            platform_user_id=user_id,
            name=name.strip(),
            kind=kind,
            is_active=bool(is_active),
            criteria_json=criteria_json or {},
            action_json=action_json or {},
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return rule

    @staticmethod
    def delete_rule(db: Session, *, user_id: str | None, rule_id: str) -> bool:
        stmt = sa_delete(FinanceRule).where(FinanceRule.rule_id == rule_id.strip())
        if user_id:
            stmt = stmt.where(FinanceRule.platform_user_id == user_id)
        result = db.execute(stmt)
        db.commit()
        return bool(result.rowcount)

    @staticmethod
    def delete_entry(db: Session, *, user_id: str | None, entry_id: str) -> bool:
        stmt = sa_delete(FinanceEntry).where(FinanceEntry.entry_id == entry_id.strip())
        if user_id:
            stmt = stmt.where(FinanceEntry.platform_user_id == user_id)
        result = db.execute(stmt)
        db.commit()
        return bool(result.rowcount)

    @staticmethod
    def build_overview(db: Session, *, user_id: str | None, display_currency: str | None = None) -> FinanceOverviewResponse:
        now = utcnow()
        month_start = now.astimezone(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        today_start = now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        base_month_total_stmt = (
            select(FinanceEntry.currency, func.coalesce(func.sum(FinanceEntry.amount_cents), 0))
            .where(FinanceEntry.occurred_at >= month_start)
            .group_by(FinanceEntry.currency)
        )
        base_today_total_stmt = (
            select(FinanceEntry.currency, func.coalesce(func.sum(FinanceEntry.amount_cents), 0))
            .where(FinanceEntry.occurred_at >= today_start)
            .group_by(FinanceEntry.currency)
        )
        base_month_count_stmt = select(func.count(FinanceEntry.id)).where(FinanceEntry.occurred_at >= month_start)
        if user_id:
            base_month_total_stmt = base_month_total_stmt.where(FinanceEntry.platform_user_id == user_id)
            base_today_total_stmt = base_today_total_stmt.where(FinanceEntry.platform_user_id == user_id)
            base_month_count_stmt = base_month_count_stmt.where(FinanceEntry.platform_user_id == user_id)
        recent_entries = FinanceService.list_entries(db, user_id=user_id, limit=12)
        fallback_currency = recent_entries[0].currency if recent_entries else settings.finance_default_currency
        target_currency = (display_currency or fallback_currency or settings.finance_default_currency or "MYR").upper()
        fx_rates, fx_as_of = FinanceService.get_current_fx_rates()

        month_total = 0
        for source_currency, amount_cents in db.execute(base_month_total_stmt).all():
            month_total += FinanceService._convert_amount_cents(
                int(amount_cents or 0),
                source_currency=source_currency,
                target_currency=target_currency,
                fx_rates=fx_rates,
            )
        today_total = 0
        for source_currency, amount_cents in db.execute(base_today_total_stmt).all():
            today_total += FinanceService._convert_amount_cents(
                int(amount_cents or 0),
                source_currency=source_currency,
                target_currency=target_currency,
                fx_rates=fx_rates,
            )
        month_count = int(
            db.scalar(base_month_count_stmt)
            or 0
        )
        return FinanceOverviewResponse(
            user_id=user_id or "all",
            default_currency=settings.finance_default_currency,
            display_currency=target_currency,
            today_total_cents=today_total,
            month_total_cents=month_total,
            month_entry_count=month_count,
            fx_rates=fx_rates,
            fx_as_of=fx_as_of,
            recent_entries=recent_entries,
            active_rules=FinanceService.list_rules(db, user_id=user_id, active_only=True),
        )

    @staticmethod
    def get_current_fx_rates() -> tuple[dict[str, float], str | None]:
        now = utcnow()
        with FinanceService._fx_lock:
            cached_rates = dict(FinanceService._fx_rates_cache.get("rates") or {})
            fetched_at = FinanceService._fx_rates_cache.get("fetched_at")
            if cached_rates and isinstance(fetched_at, datetime):
                age_seconds = (now - fetched_at).total_seconds()
                if age_seconds <= FinanceService._fx_cache_ttl_seconds:
                    return cached_rates, FinanceService._fx_rates_cache.get("as_of")

        providers: list[tuple[str, str]] = [
            ("frankfurter", "https://api.frankfurter.app/latest?from=USD"),
            ("open-er-api", "https://open.er-api.com/v6/latest/USD"),
            ("currency-api-pages", "https://latest.currency-api.pages.dev/v1/currencies/usd.json"),
        ]
        try:
            with httpx.Client(timeout=12.0) as client:
                for provider_name, url in providers:
                    try:
                        response = client.get(url)
                        if response.status_code != 200:
                            continue
                        payload = response.json()
                        raw_rates: dict[str, Any] = {}
                        as_of = ""
                        if provider_name == "frankfurter":
                            raw_rates = payload.get("rates", {})
                            as_of = str(payload.get("date") or "").strip()
                        elif provider_name == "open-er-api":
                            raw_rates = payload.get("rates", {})
                            as_of = str(payload.get("time_last_update_utc") or "").strip()
                        elif provider_name == "currency-api-pages":
                            raw_rates = payload.get("usd", {})
                            as_of = str(payload.get("date") or "").strip()

                        rates = FinanceService._normalize_fx_rates(raw_rates)
                        if len(rates) <= 1:
                            continue
                        stamp = f"{as_of} via {provider_name}".strip() if as_of else f"live via {provider_name}"
                        with FinanceService._fx_lock:
                            FinanceService._fx_rates_cache = {"rates": rates, "as_of": stamp, "fetched_at": now}
                        return rates, stamp
                    except Exception:
                        continue
        except Exception:
            pass

        with FinanceService._fx_lock:
            cached_rates = dict(FinanceService._fx_rates_cache.get("rates") or {})
            if cached_rates:
                return cached_rates, FinanceService._fx_rates_cache.get("as_of")
        return dict(FinanceService._fx_fallback_rates), "fallback"

    @staticmethod
    def _convert_amount_cents(
        amount_cents: int,
        *,
        source_currency: str | None,
        target_currency: str | None,
        fx_rates: dict[str, float],
    ) -> int:
        source = (source_currency or settings.finance_default_currency or "MYR").upper()
        target = (target_currency or settings.finance_default_currency or "MYR").upper()
        if source == target:
            return int(amount_cents)
        source_rate = fx_rates.get(source)
        target_rate = fx_rates.get(target)
        if not source_rate or not target_rate:
            return int(amount_cents)
        usd_value = float(amount_cents) / float(source_rate)
        target_value = usd_value * float(target_rate)
        return int(round(target_value))

    @staticmethod
    def try_handle(
        db: Session,
        *,
        user_id: str,
        session_id: str,
        text: str,
        assets: list[UploadedAsset] | None = None,
        prompt_messages: list[dict[str, str]] | None = None,
        active_provider: str | None = None,
        active_model: str | None = None,
    ) -> CommandResult | None:
        normalized = " ".join(text.strip().split())
        if assets:
            capture_result = FinanceService._try_capture_receipt(
                db=db,
                user_id=user_id,
                session_id=session_id,
                text=normalized,
                assets=assets,
                prompt_messages=prompt_messages or [],
                active_provider=active_provider,
                active_model=active_model,
            )
            if capture_result is not None:
                return capture_result

        if not normalized:
            return None

        delete_rule = FinanceService.DELETE_RULE_PATTERN.search(normalized)
        if delete_rule:
            rule_id = delete_rule.group("rule_id").strip()
            deleted = FinanceService.delete_rule(db, user_id=user_id, rule_id=rule_id)
            if deleted:
                return CommandResult(reply=f"Deleted finance rule `{rule_id}`.", provider="finance")
            return CommandResult(reply=f"I could not find finance rule `{rule_id}`.", provider="finance")

        delete_entry = FinanceService.DELETE_ENTRY_PATTERN.search(normalized)
        if delete_entry:
            entry_id = delete_entry.group("entry_id").strip()
            deleted = FinanceService.delete_entry(db, user_id=user_id, entry_id=entry_id)
            if deleted:
                return CommandResult(reply=f"Deleted finance entry `{entry_id}`.", provider="finance")
            return CommandResult(reply=f"I could not find finance entry `{entry_id}`.", provider="finance")

        category_rule = FinanceService.CATEGORY_RULE_PATTERN.search(normalized)
        if category_rule:
            keyword = category_rule.group("keyword").strip().strip("'\"")
            category = category_rule.group("category").strip().title()
            rule = FinanceService.create_rule(
                db,
                user_id=user_id,
                name=f"Auto category: {keyword} -> {category}",
                kind=FinanceRuleKind.category_keyword,
                criteria_json={"merchant_keyword": keyword},
                action_json={"set_category": category},
            )
            return CommandResult(
                reply=(
                    f"Saved finance rule `{rule.rule_id}`.\n"
                    f"When merchant or title contains `{keyword}`, I will categorize it as `{category}`."
                ),
                provider="finance",
            )

        threshold_rule = FinanceService.THRESHOLD_RULE_PATTERN.search(normalized)
        if threshold_rule:
            amount_cents = FinanceService._money_to_cents(threshold_rule.group("amount"))
            if amount_cents is None:
                return CommandResult(reply="I could not understand the alert amount for that finance rule.", provider="finance")
            scope = (threshold_rule.group("scope") or "monthly").strip().lower()
            category = (threshold_rule.group("category") or "").strip().title() or None
            label = f"{scope.title()} spending alert"
            if category:
                label += f" for {category}"
            rule = FinanceService.create_rule(
                db,
                user_id=user_id,
                name=f"{label} above {FinanceService._format_currency(amount_cents)}",
                kind=FinanceRuleKind.threshold,
                criteria_json={"scope": scope, "category": category, "threshold_cents": amount_cents},
                action_json={"type": "warn"},
            )
            return CommandResult(
                reply=(
                    f"Saved finance rule `{rule.rule_id}`.\n"
                    f"I will warn you when {scope} spending"
                    f"{f' for {category}' if category else ''} goes above {FinanceService._format_currency(amount_cents)}."
                ),
                provider="finance",
            )

        if FinanceService.RECENT_EXPENSES_PATTERN.search(normalized):
            entries = FinanceService.list_entries(db, user_id=user_id, limit=8)
            if not entries:
                return CommandResult(reply="I don't have any saved expenses yet. Send me a receipt and I can store it.", provider="finance")
            lines = ["Recent spending:"]
            for item in entries:
                lines.append(f"- {FinanceService._format_entry_line(item)}")
            return CommandResult(reply="\n".join(lines), provider="finance")

        if FinanceService.SPENDING_SUMMARY_PATTERN.search(normalized):
            category = FinanceService._extract_category_filter(normalized)
            period = FinanceService._extract_period(normalized)
            entries = FinanceService.list_entries(db, user_id=user_id, limit=100, category=category, period=period)
            if not entries:
                scope_label = FinanceService._period_label(period)
                category_label = f" in {category.title()}" if category else ""
                return CommandResult(
                    reply=f"I don't have any saved spending{category_label} for {scope_label} yet.",
                    provider="finance",
                )
            total = sum(item.amount_cents for item in entries)
            lines = [
                f"Spending summary for {FinanceService._period_label(period)}{f' in {category.title()}' if category else ''}:",
                f"- Total: {FinanceService._format_currency(total, entries[0].currency if entries else settings.finance_default_currency)}",
                f"- Entries: {len(entries)}",
            ]
            by_category: dict[str, int] = {}
            for item in entries:
                bucket = (item.category or "Uncategorized").strip()
                by_category[bucket] = by_category.get(bucket, 0) + item.amount_cents
            top_categories = sorted(by_category.items(), key=lambda pair: pair[1], reverse=True)[:5]
            if top_categories and not category:
                lines.append("")
                lines.append("Top categories:")
                for name, amount_cents in top_categories:
                    lines.append(f"- {name}: {FinanceService._format_currency(amount_cents)}")
            lines.append("")
            lines.append("Recent entries:")
            for item in entries[:5]:
                lines.append(f"- {FinanceService._format_entry_line(item)}")
            return CommandResult(reply="\n".join(lines), provider="finance")

        return None

    @staticmethod
    def _try_capture_receipt(
        db: Session,
        *,
        user_id: str,
        session_id: str,
        text: str,
        assets: list[UploadedAsset],
        prompt_messages: list[dict[str, str]],
        active_provider: str | None,
        active_model: str | None,
    ) -> CommandResult | None:
        if not assets:
            return None
        if not settings.finance_auto_capture_receipts and not FinanceService.RECEIPT_HINT_PATTERN.search(text):
            return None

        source_asset = assets[0]
        filename_lower = source_asset.original_filename.lower()
        hinted = bool(FinanceService.RECEIPT_HINT_PATTERN.search(text)) or any(
            token in filename_lower for token in ("receipt", "invoice", "bill", "order")
        )
        if not hinted and text and len(text.split()) > 2:
            return None

        parsed = FinanceService._extract_receipt_candidate(
            source_asset=source_asset,
            prompt_messages=prompt_messages,
            active_provider=active_provider,
            active_model=active_model,
        )
        if not parsed or not parsed.get("is_receipt"):
            return None
        parsed = FinanceService._sanitize_receipt_payload(parsed)

        amount_cents = FinanceService._money_to_cents(parsed.get("total"))
        if amount_cents is None or amount_cents <= 0:
            return None

        rules = FinanceService.list_rules(db, user_id=user_id, active_only=True)
        title = FinanceService._clean_title(str(parsed.get("title") or parsed.get("merchant_name") or "Receipt"))
        merchant_name = FinanceService._clean_title(str(parsed.get("merchant_name") or title))
        category = FinanceService._apply_category_rules(
            merchant_name=merchant_name,
            title=title,
            rules=rules,
        ) or FinanceService._guess_category(merchant_name, title)
        occurred_at = FinanceService._parse_date_value(parsed.get("date"))
        currency = FinanceService._clean_currency(parsed.get("currency")) or settings.finance_default_currency
        payment_method = str(parsed.get("payment_method") or "").strip() or None
        notes = str(parsed.get("notes") or "").strip() or None
        metadata_json = {
            "asset_id": source_asset.asset_id,
            "filename": source_asset.original_filename,
            "raw_receipt_data": parsed,
            "line_items": list(parsed.get("line_items") or [])[:20],
        }
        entry = FinanceEntry(
            entry_id=FinanceService._make_entry_id(),
            platform_user_id=user_id,
            session_id=session_id,
            source="receipt",
            title=title,
            merchant_name=merchant_name,
            category=category,
            currency=currency,
            amount_cents=amount_cents,
            occurred_at=occurred_at or utcnow(),
            payment_method=payment_method,
            notes=notes,
            metadata_json=metadata_json,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)

        triggered = FinanceService._evaluate_threshold_rules(db, user_id=user_id, entry=entry, rules=rules)

        lines = [
            "Saved this receipt to Finance.",
            f"- Entry: `{entry.entry_id}`",
            f"- Merchant: {entry.merchant_name or entry.title}",
            f"- Total: {FinanceService._format_currency(entry.amount_cents, entry.currency)}",
            f"- Category: {entry.category or 'Uncategorized'}",
            f"- Date: {FinanceService._format_datetime(entry.occurred_at)}",
        ]
        if entry.payment_method:
            lines.append(f"- Payment: {entry.payment_method}")
        if triggered:
            lines.append("")
            lines.append("Finance automation alerts:")
            for item in triggered:
                lines.append(f"- {item}")

        return CommandResult(reply="\n".join(lines), provider="finance")

    @staticmethod
    def _extract_receipt_candidate(
        *,
        source_asset: UploadedAsset,
        prompt_messages: list[dict[str, str]],
        active_provider: str | None,
        active_model: str | None,
    ) -> dict[str, Any] | None:
        if source_asset.kind == UploadedAssetKind.image:
            return FinanceService._extract_receipt_from_image(
                source_asset=source_asset,
                prompt_messages=prompt_messages,
                active_provider=active_provider,
                active_model=active_model,
            )
        return FinanceService._extract_receipt_from_document(
            source_asset=source_asset,
            active_provider=active_provider,
            active_model=active_model,
        )

    @staticmethod
    def _extract_receipt_from_image(
        *,
        source_asset: UploadedAsset,
        prompt_messages: list[dict[str, str]],
        active_provider: str | None,
        active_model: str | None,
    ) -> dict[str, Any] | None:
        extraction_messages = [
            {
                "role": "system",
                "content": (
                    "You extract structured receipt data. "
                    "Return strict JSON only with keys: "
                    "is_receipt, confidence, merchant_name, title, total, currency, date, payment_method, notes, line_items. "
                    "Do not invent missing details. If the store name is not clearly visible, set merchant_name to null and title to 'Receipt'. "
                    "Do not use purchased item names as the merchant unless it is clearly the business name. "
                    "Use the grand total / total amount only, not item prices or years."
                ),
            },
            {"role": "user", "content": "Analyze the uploaded image carefully."},
        ]
        prompt_variants = [
            (
                "Decide whether this image is a purchase receipt or invoice. "
                "If it is, extract the merchant, total, currency, date, payment method, short title, optional notes, "
                "and a small line_items array. Return JSON only. "
                "Be conservative: if a field is unclear, leave it null. "
                "Never guess a merchant from a purchased item line."
            ),
            (
                "Read this printed receipt carefully from top to bottom. "
                "Focus especially on the final TOTAL / GRAND TOTAL amount, date, and any clearly visible store name. "
                "If the store name is not clearly visible, set merchant_name to null and title to 'Receipt'. "
                "Do not invent values. Return JSON only."
            ),
        ]

        best_payload: dict[str, Any] | None = None
        best_score = -1.0
        for prompt_text in prompt_variants:
            try:
                reply, _provider = LLMService.generate_vision_reply(
                    prompt_messages=extraction_messages,
                    prompt_text=prompt_text,
                    image_assets=[source_asset],
                    active_provider=active_provider,
                    active_model=active_model,
                )
            except Exception:
                continue
            payload = FinanceService._extract_json_object(reply)
            if not isinstance(payload, dict):
                continue
            payload = FinanceService._sanitize_receipt_payload(payload)
            score = FinanceService._score_receipt_payload(payload)
            if score > best_score:
                best_payload = payload
                best_score = score
            if score >= 5.5:
                break

        if not isinstance(best_payload, dict):
            return None
        confidence = float(best_payload.get("confidence", 0) or 0)
        if not best_payload.get("is_receipt") and confidence < 0.55:
            return None
        return best_payload

    @staticmethod
    def _extract_receipt_from_document(
        *,
        source_asset: UploadedAsset,
        active_provider: str | None,
        active_model: str | None,
    ) -> dict[str, Any] | None:
        extracted_text = AttachmentService.extract_text(source_asset)
        if not extracted_text.strip():
            return None
        try:
            reply, _provider = LLMService.generate_reply(
                [
                    {
                        "role": "system",
                        "content": (
                            "You extract structured receipt data. Return strict JSON only with keys: "
                            "is_receipt, confidence, merchant_name, title, total, currency, date, payment_method, notes, line_items."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "Analyze this extracted text from a possible receipt or invoice. "
                            "If it is not a receipt, set is_receipt to false.\n\n"
                            f"{extracted_text[:16000]}"
                        ),
                    },
                ],
                active_provider=active_provider,
                active_model=active_model,
            )
            payload = FinanceService._extract_json_object(reply)
            if isinstance(payload, dict):
                confidence = float(payload.get("confidence", 0) or 0)
                if payload.get("is_receipt") or confidence >= 0.55:
                    return payload
        except Exception:
            pass
        return FinanceService._fallback_receipt_parse(extracted_text)

    @staticmethod
    def _fallback_receipt_parse(text: str) -> dict[str, Any] | None:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return None
        lowered = text.lower()
        if not any(token in lowered for token in ("total", "invoice", "receipt", "subtotal", "amount", "tax", "cash")):
            return None

        amount = FinanceService._extract_total_from_text(text)
        if amount is None:
            return None
        merchant = FinanceService._clean_title(lines[0])
        return {
            "is_receipt": True,
            "confidence": 0.62,
            "merchant_name": merchant,
            "title": merchant,
            "total": amount,
            "currency": FinanceService._extract_currency_from_text(text) or settings.finance_default_currency,
            "date": FinanceService._extract_date_from_text(text),
            "payment_method": FinanceService._extract_payment_method(text),
            "notes": None,
            "line_items": [],
        }

    @staticmethod
    def _extract_total_from_text(text: str) -> str | None:
        patterns = [
            r"(?im)^\s*(?:grand\s+total|total|amount\s+due|jumlah|balance\s+due)\s*[:\-]?\s*(rm|myr|\$)?\s*([\d,]+(?:\.\d{1,2})?)\s*$",
            r"(?im)(?:grand\s+total|total|amount\s+due|jumlah|balance\s+due)[^\d]{0,12}(rm|myr|\$)?\s*([\d,]+(?:\.\d{1,2})?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                prefix = (match.group(1) or "").strip()
                number = (match.group(2) or "").strip()
                return f"{prefix} {number}".strip()
        candidates = re.findall(r"(?:rm|myr|\$)?\s*([\d,]+(?:\.\d{1,2})?)", text, flags=re.IGNORECASE)
        if candidates:
            return candidates[-1]
        return None

    @staticmethod
    def _extract_currency_from_text(text: str) -> str | None:
        match = re.search(r"\b(MYR|RM|USD|SGD|EUR|GBP)\b", text, flags=re.IGNORECASE)
        if not match:
            return None
        return FinanceService._clean_currency(match.group(1))

    @staticmethod
    def _extract_payment_method(text: str) -> str | None:
        match = re.search(r"\b(cash|visa|mastercard|debit|credit|duitnow|tng|touch\s*n\s*go|grabpay)\b", text, flags=re.IGNORECASE)
        if not match:
            return None
        return match.group(1).strip().title()

    @staticmethod
    def _extract_date_from_text(text: str) -> str | None:
        patterns = [
            r"\b(\d{4}-\d{2}-\d{2})\b",
            r"\b(\d{2}/\d{2}/\d{4})\b",
            r"\b(\d{2}-\d{2}-\d{4})\b",
            r"\b([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def _extract_json_object(text: str) -> dict[str, Any] | None:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        candidates = [cleaned]
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            candidates.append(cleaned[start : end + 1])
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except Exception:
                continue
            if isinstance(parsed, dict):
                return parsed
        return None

    @staticmethod
    def _sanitize_receipt_payload(payload: dict[str, Any]) -> dict[str, Any]:
        cleaned = dict(payload)
        merchant = FinanceService._clean_title(str(cleaned.get("merchant_name") or "")).strip()
        title = FinanceService._clean_title(str(cleaned.get("title") or merchant or "Receipt")).strip()
        raw_line_items = list(cleaned.get("line_items") or [])
        line_item_names = {
            FinanceService._clean_title(str(item.get("item") or "")).strip().lower()
            for item in raw_line_items
            if isinstance(item, dict) and str(item.get("item") or "").strip()
        }

        suspicious_names = {"receipt", "invoice", "total", "subtotal", "tax", "cash", "change"}
        if merchant.lower() in suspicious_names:
            merchant = ""
        if title.lower() in suspicious_names:
            title = "Receipt"

        # If the model picked a purchased item line as the merchant, fall back to
        # a neutral receipt title instead of storing misleading merchant data.
        if merchant and merchant.lower() in line_item_names and len(line_item_names) >= 2:
            merchant = ""
        if title and title.lower() in line_item_names and len(line_item_names) >= 2:
            title = merchant or "Receipt"

        cleaned["merchant_name"] = merchant or None
        cleaned["title"] = title or merchant or "Receipt"
        return cleaned

    @staticmethod
    def _score_receipt_payload(payload: dict[str, Any]) -> float:
        score = 0.0
        if payload.get("is_receipt"):
            score += 1.0
        confidence = float(payload.get("confidence", 0) or 0)
        score += max(0.0, min(confidence, 1.0))
        amount_cents = FinanceService._money_to_cents(payload.get("total"))
        if amount_cents and amount_cents > 0:
            score += 2.5
        if str(payload.get("date") or "").strip():
            score += 0.8
        merchant = str(payload.get("merchant_name") or "").strip()
        if merchant:
            score += 0.5
        line_items = list(payload.get("line_items") or [])
        if line_items:
            score += min(1.2, 0.3 * len(line_items))
        return score

    @staticmethod
    def _money_to_cents(value: Any) -> int | None:
        if value is None:
            return None
        raw = str(value).strip().upper().replace("MYR", "").replace("RM", "").replace("$", "").replace(",", "")
        match = re.search(r"(-?\d+(?:\.\d{1,2})?)", raw)
        if not match:
            return None
        try:
            number = float(match.group(1))
        except ValueError:
            return None
        return int(round(number * 100))

    @staticmethod
    def _clean_currency(value: str | None) -> str:
        raw = (value or "").strip().upper()
        if raw in {"RM", "MYR"}:
            return "MYR"
        return raw or settings.finance_default_currency

    @staticmethod
    def _clean_title(value: str) -> str:
        cleaned = " ".join(str(value or "").split()).strip(" -:_")
        if not cleaned:
            return "Receipt"
        if len(cleaned) > 120:
            cleaned = cleaned[:117].rstrip() + "..."
        return cleaned[0].upper() + cleaned[1:] if cleaned else "Receipt"

    @staticmethod
    def _parse_date_value(value: Any) -> datetime | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%b %d, %Y", "%B %d, %Y"):
            try:
                parsed = datetime.strptime(raw, fmt)
                return parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _apply_category_rules(*, merchant_name: str, title: str, rules: list[FinanceRule]) -> str | None:
        haystack = f"{merchant_name} {title}".lower()
        for rule in rules:
            if rule.kind != FinanceRuleKind.category_keyword or not rule.is_active:
                continue
            keyword = str((rule.criteria_json or {}).get("merchant_keyword", "")).strip().lower()
            category = str((rule.action_json or {}).get("set_category", "")).strip()
            if keyword and category and keyword in haystack:
                return category.title()
        return None

    @staticmethod
    def _guess_category(merchant_name: str, title: str) -> str:
        haystack = f"{merchant_name} {title}".lower()
        keyword_map = {
            "Shopping": ("shopee", "lazada", "amazon", "uniqlo", "zara", "watsons"),
            "Groceries": ("jaya grocer", "aeon", "lotus", "tesco", "village grocer", "mercato"),
            "Food": ("restaurant", "restoran", "cafe", "grabfood", "foodpanda", "mcd", "kfc", "tealive", "starbucks"),
            "Transport": ("grab", "lrt", "mrt", "ktm", "petrol", "petronas", "shell", "caltex"),
            "Bills": ("tnb", "water", "internet", "maxis", "celcom", "unifi"),
            "Health": ("clinic", "hospital", "pharmacy", "guardian"),
        }
        for category, keywords in keyword_map.items():
            if any(keyword in haystack for keyword in keywords):
                return category
        return "Uncategorized"

    @staticmethod
    def _evaluate_threshold_rules(
        db: Session,
        *,
        user_id: str,
        entry: FinanceEntry,
        rules: list[FinanceRule],
    ) -> list[str]:
        alerts: list[str] = []
        for rule in rules:
            if rule.kind != FinanceRuleKind.threshold or not rule.is_active:
                continue
            criteria = rule.criteria_json or {}
            threshold_cents = int(criteria.get("threshold_cents", 0) or 0)
            if threshold_cents <= 0:
                continue
            category = str(criteria.get("category", "") or "").strip()
            scope = str(criteria.get("scope", "monthly") or "monthly").strip().lower()
            start = FinanceService._period_start(scope)
            stmt = select(func.coalesce(func.sum(FinanceEntry.amount_cents), 0)).where(FinanceEntry.platform_user_id == user_id)
            if start is not None:
                stmt = stmt.where(FinanceEntry.occurred_at >= start)
            if category:
                stmt = stmt.where(func.lower(FinanceEntry.category) == category.lower())
            total_cents = int(db.scalar(stmt) or 0)
            if total_cents > threshold_cents:
                alerts.append(
                    f"{rule.name}: {FinanceService._format_currency(total_cents, entry.currency)} is above your threshold of {FinanceService._format_currency(threshold_cents, entry.currency)}."
                )
        return alerts

    @staticmethod
    def _period_start(period: str | None) -> datetime | None:
        scope = (period or "").strip().lower()
        now = utcnow().astimezone(timezone.utc)
        if scope in {"today", "daily", "day"}:
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        if scope in {"week", "weekly", "this week"}:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return start - timedelta(days=start.weekday())
        if scope in {"month", "monthly", "this month"}:
            return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return None

    @staticmethod
    def _extract_period(text: str) -> str | None:
        lowered = text.lower()
        if "today" in lowered:
            return "today"
        if "this week" in lowered or "weekly" in lowered:
            return "week"
        if "this month" in lowered or "monthly" in lowered:
            return "month"
        return None

    @staticmethod
    def _period_label(period: str | None) -> str:
        normalized = (period or "all time").strip().lower()
        labels = {
            "today": "today",
            "week": "this week",
            "month": "this month",
            "all time": "all time",
        }
        return labels.get(normalized, normalized or "all time")

    @staticmethod
    def _extract_category_filter(text: str) -> str | None:
        lowered = text.lower()
        for category in ("food", "groceries", "shopping", "transport", "bills", "health"):
            if re.search(rf"\b{re.escape(category)}\b", lowered):
                return category
        category_match = re.search(r"\bcategory\s+([a-z0-9 &/_-]+)", lowered)
        if category_match:
            return category_match.group(1).strip()
        return None

    @staticmethod
    def _format_currency(amount_cents: int, currency: str | None = None) -> str:
        resolved = (currency or settings.finance_default_currency or "MYR").upper()
        amount = amount_cents / 100
        prefix = "RM" if resolved == "MYR" else resolved
        return f"{prefix} {amount:,.2f}"

    @staticmethod
    def _format_datetime(value: datetime | None) -> str:
        if value is None:
            return "Unknown"
        return value.astimezone().strftime("%Y-%m-%d %I:%M %p %Z")

    @staticmethod
    def _format_entry_line(entry: FinanceEntry) -> str:
        return (
            f"{entry.title} | {FinanceService._format_currency(entry.amount_cents, entry.currency)} | "
            f"{entry.category or 'Uncategorized'} | {FinanceService._format_datetime(entry.occurred_at)}"
        )
