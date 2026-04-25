#!/usr/bin/env python3
"""Claude Code Stop hook — logs session token usage to MemoryCore.

Called by Claude Code at the end of every session. Reads the session's
transcript file, sums token usage across all assistant turns, POSTs a
single row to /api/v1/memorycore/usage.

Never blocks Claude Code: network errors fail silently, non-zero exit
codes would annoy the user. Exit 0 always.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

SERVER_URL = os.environ.get("MEMORYCORE_SERVER_URL", "http://localhost:8000")
USER_ID = os.environ.get("MEMORYCORE_USER_ID", "fitclaw")
TIMEOUT_SECONDS = 5


def _read_stdin_json() -> dict:
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, OSError):
        return {}


def _extract_text(content) -> str:
    """Pull plain text out of a Claude message content (str or list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text") or ""
                if text:
                    chunks.append(text)
        return "\n".join(chunks)
    return ""


def _sum_transcript_usage(transcript_path: str) -> tuple[int, int, int, int, str, str, str]:
    """Return (input, output, cache_read, cache_write, last_model, last_user, last_assistant)."""
    total_in = total_out = cache_read = cache_write = 0
    last_model = ""
    last_user_text = ""
    last_assistant_text = ""
    path = Path(transcript_path)
    if not transcript_path or not path.exists():
        return total_in, total_out, cache_read, cache_write, last_model, last_user_text, last_assistant_text
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                message = entry.get("message") or {}
                role = message.get("role") or entry.get("role")
                content = message.get("content")
                usage = message.get("usage") or entry.get("usage") or {}
                if usage:
                    total_in += int(usage.get("input_tokens") or 0)
                    total_out += int(usage.get("output_tokens") or 0)
                    cache_read += int(usage.get("cache_read_input_tokens") or 0)
                    cache_write += int(usage.get("cache_creation_input_tokens") or 0)
                    if message.get("model"):
                        last_model = str(message["model"])
                if role == "user":
                    text = _extract_text(content)
                    if text and not text.startswith("<"):  # skip system reminders / tool results
                        last_user_text = text
                elif role == "assistant":
                    text = _extract_text(content)
                    if text:
                        last_assistant_text = text
    except OSError:
        pass
    return total_in, total_out, cache_read, cache_write, last_model, last_user_text, last_assistant_text


def main() -> int:
    data = _read_stdin_json()
    session_id = str(data.get("session_id") or "")
    transcript_path = str(data.get("transcript_path") or "")

    (
        total_in,
        total_out,
        cache_read,
        cache_write,
        model,
        last_user,
        last_assistant,
    ) = _sum_transcript_usage(transcript_path)

    if total_in == 0 and total_out == 0:
        return 0  # nothing meaningful to log

    # Pack a structured note so the Telegram notification can quote what
    # the user asked + what Claude said (truncated). Keep total under ~1500
    # chars so the Telegram message fits easily.
    note_parts = []
    if last_user:
        note_parts.append(f"Q: {last_user.strip()[:400]}")
    if last_assistant:
        note_parts.append(f"A: {last_assistant.strip()[:800]}")
    note = "\n\n".join(note_parts) if note_parts else "auto-logged by Stop hook"

    body = {
        "tool": "claude_code",
        "model": model or "unknown",
        "session_id": session_id,
        "input_tokens": total_in,
        "output_tokens": total_out,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "note": note,
    }

    notify_flag = os.environ.get("MEMORYCORE_NOTIFY_ON_FINISH", "1") not in ("0", "false", "no")
    notify_qs = "&notify=true" if notify_flag else ""
    url = f"{SERVER_URL.rstrip('/')}/api/v1/memorycore/usage?user_id={USER_ID}{notify_qs}"
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS):
            pass
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        pass  # never block Claude Code on a logging failure

    return 0


if __name__ == "__main__":
    sys.exit(main())
