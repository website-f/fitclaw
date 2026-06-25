"""Static per-model USD pricing table (per 1M tokens).

`None` rates mean "unknown" — UsageService stores `cost_cents = None` so a
missing price stays loud rather than getting silently zeroed.
"""
from __future__ import annotations

# (input_usd_per_million, output_usd_per_million)
MODEL_PRICING: dict[str, tuple[float | None, float | None]] = {
    # Claude (Anthropic) — public list rates as of 2026.
    "claude-opus-4-7": (15.0, 75.0),
    "claude-opus-4-6": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (0.8, 4.0),
    "claude-haiku-4-5-20251001": (0.8, 4.0),
    # OpenAI
    "gpt-5": (5.0, 15.0),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    # Google
    "gemini-2.0-flash": (0.075, 0.3),
    "gemini-1.5-pro": (1.25, 5.0),
    # Local Ollama models — free at point of use.
    "qwen2.5:3b": (0.0, 0.0),
    "qwen2.5-coder:7b": (0.0, 0.0),
    "qwen3-coder:30b": (0.0, 0.0),
    "deepseek-r1:1.5b": (0.0, 0.0),
    "gemma3:4b": (0.0, 0.0),
}


def lookup(model: str) -> tuple[float | None, float | None]:
    if not model:
        return (None, None)
    key = model.strip().lower()
    if key in MODEL_PRICING:
        return MODEL_PRICING[key]
    # Try matching by prefix so "claude-opus-4-7-20260101" still resolves.
    for prefix, rates in MODEL_PRICING.items():
        if key.startswith(prefix.lower()):
            return rates
    if key.startswith("ollama:") or key.startswith("ollama/"):
        return (0.0, 0.0)
    return (None, None)


def cost_cents(model: str, input_tokens: int, output_tokens: int) -> int | None:
    """Returns the cost in USD cents, or `None` if the model is unpriced."""
    rate_in, rate_out = lookup(model)
    if rate_in is None or rate_out is None:
        return None
    usd = (input_tokens / 1_000_000.0) * rate_in + (output_tokens / 1_000_000.0) * rate_out
    return max(0, int(round(usd * 100)))
