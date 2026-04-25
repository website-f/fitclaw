"""Token pricing table.

Values are USD per 1,000,000 tokens, as (input_rate, output_rate).
These will go stale. Update freely — they're just reference data.

Models not in this table return None cost and the ledger row stores NULL.
That's intentional: a missing price is louder than a wrong price.
"""
from __future__ import annotations

MODEL_PRICING: dict[str, tuple[float, float]] = {
    # Anthropic Claude
    "claude-opus-4-7": (15.0, 75.0),
    "claude-opus-4-7[1m]": (15.0, 75.0),
    "claude-opus-4-6": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    # OpenAI / Codex
    "gpt-5": (10.0, 30.0),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "gpt-4": (30.0, 60.0),
    # Local / Ollama — free by design
    "ollama": (0.0, 0.0),
}


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        return None
    in_cost = (input_tokens / 1_000_000) * pricing[0]
    out_cost = (output_tokens / 1_000_000) * pricing[1]
    return round(in_cost + out_cost, 6)
