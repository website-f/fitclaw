from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.modules.router.models import RoutingDecision
from app.modules.router.schemas import RouteIntent
from app.services.llm_service import LLMService, LLMServiceError

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are an intent classifier for an AI-ops platform.
You receive one user message and must classify it into one of these categories:

- fix: user wants AI to fix a bug/issue in a known project. Look for bug words ("broken", "doesn't work", "crash"), reports about behavior, mentions of UI elements, mentions of project names.
- push: user wants to push pending git changes for a project.
- deploy: user wants to redeploy a project on the VPS.
- query: user is asking for information about the system: "what's my RAM", "show usage today", "list projects", "what sessions are open". Read-only.
- finance: anything about money — receipt photos, "paid X for Y", "send invoice to Z", expense entries, P&L questions.
- crm: anything about leads, customers, contacts — "new lead from John", "follow up with ACME", contact intake.
- calendar: scheduling, meetings, reminders for specific dates/times — "book Friday 3pm with X".
- task: generic todos that aren't tied to a date — "remind me to do X" without a specific time.
- chat: fallback. The message is conversational, vague, or doesn't fit any category.

Output STRICT JSON only, with these fields:
- category: one of the 9 above
- confidence: float 0.0–1.0 (how sure you are)
- params: object with extracted fields (project name, amount, who, when, what — whatever applies)
- reasoning: one short sentence why you chose this category

Examples:
Input: "the /usage button doesn't respond on iOS in fitclaw"
Output: {"category":"fix","confidence":0.95,"params":{"project":"fitclaw","issue":"the /usage button doesn't respond on iOS"},"reasoning":"user reports a UI bug in named project"}

Input: "what's my disk usage"
Output: {"category":"query","confidence":0.9,"params":{"target":"disks"},"reasoning":"information request, read-only"}

Input: "paid 250 for ad spend on facebook"
Output: {"category":"finance","confidence":0.85,"params":{"amount":250,"vendor":"facebook","note":"ad spend"},"reasoning":"expense entry"}

Input: "deploy fitclaw to dev"
Output: {"category":"deploy","confidence":0.95,"params":{"project":"fitclaw","branch":"dev"},"reasoning":"deploy command with project + branch"}

Input: "hi how are you"
Output: {"category":"chat","confidence":0.7,"params":{},"reasoning":"conversational, no actionable intent"}
"""


class RouterService:
    @staticmethod
    def classify(db: Session, user_id: str, text: str, source: str = "telegram") -> tuple[RouteIntent, RoutingDecision]:
        intent = _classify_with_llm(text)
        row = RoutingDecision(
            user_id=user_id,
            source=source,
            raw_text=text,
            category=intent.category,
            confidence=intent.confidence,
            params=dict(intent.params),
            reasoning=intent.reasoning,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return intent, row

    @staticmethod
    def mark_dispatched(db: Session, decision_id: int, action: str) -> None:
        row = db.get(RoutingDecision, decision_id)
        if row is None:
            return
        row.dispatched = True
        row.dispatch_action = action
        db.commit()


def _classify_with_llm(text: str) -> RouteIntent:
    """Call the local LLM with a structured prompt, parse JSON, return intent.

    Failure modes (silently fall through to "chat"):
      - LLM unreachable → category=chat, confidence=0
      - LLM returns non-JSON → same
      - LLM returns valid JSON but wrong category → same
    """
    fallback = RouteIntent(category="chat", confidence=0.0, params={}, reasoning="classifier unavailable")
    if not text or not text.strip():
        return fallback

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": text.strip()},
    ]
    try:
        # generate_reply returns (reply_text, resolved_model). Use defaults
        # so the classifier follows the user's currently active model.
        reply, _ = LLMService.generate_reply(messages=messages)
    except LLMServiceError as exc:
        logger.warning("router LLM failed: %s", exc)
        return fallback
    except Exception as exc:  # any unexpected — never propagate
        logger.exception("router LLM unexpected error: %s", exc)
        return fallback

    json_blob = _extract_json(reply)
    if not json_blob:
        logger.warning("router LLM did not return JSON: %s", reply[:200])
        return fallback

    try:
        data = json.loads(json_blob)
    except json.JSONDecodeError:
        logger.warning("router LLM JSON parse failed: %s", json_blob[:200])
        return fallback

    category = (data.get("category") or "chat").strip().lower()
    valid = {"fix", "push", "deploy", "query", "finance", "crm", "calendar", "task", "chat"}
    if category not in valid:
        category = "chat"

    confidence = data.get("confidence")
    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence = 0.0

    params = data.get("params") or {}
    if not isinstance(params, dict):
        params = {}

    return RouteIntent(
        category=category,  # type: ignore[arg-type]
        confidence=confidence,
        params=params,
        reasoning=str(data.get("reasoning") or "")[:300],
    )


def _extract_json(text: str) -> str | None:
    """Find the first JSON object in text. Handles models that wrap output in
    markdown code fences or chatty preamble.
    """
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    # Strip ```json ... ``` fences
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            stripped = part.strip()
            if stripped.startswith("json"):
                stripped = stripped[4:].strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                return stripped
    # Last resort: find first { … last }
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return None
