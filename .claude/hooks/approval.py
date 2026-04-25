#!/usr/bin/env python3
"""Claude Code PreToolUse hook — Telegram-gated approval for risky actions.

Called by Claude Code before every tool invocation. For actions deemed
"risky" by the local policy (see _needs_approval below), we:

1. POST /api/v1/approvals to create a pending record on the server.
   The server sends a Telegram message with Approve/Deny buttons.
2. Poll GET /api/v1/approvals/<id> every POLL_SECONDS for up to
   TIMEOUT_SECONDS.
3. Exit 0 if approved → Claude Code proceeds.
   Exit 2 if denied / timeout → Claude Code blocks the action.

For non-risky actions we exit 0 immediately (no server round-trip).

Configuration via env vars:
  MEMORYCORE_SERVER_URL   base URL to the cloud API (default http://localhost:8000)
  MEMORYCORE_USER_ID      (default fitclaw)
  APPROVAL_TIMEOUT_SEC    seconds to wait for a human (default 300)
  APPROVAL_POLL_SEC       polling interval (default 3)
  APPROVAL_ALLOWED_TOOLS  comma-separated tool names to auto-approve
                          (default: Read,Grep,Glob — read-only by nature)

Never raises. Exit codes are the contract with Claude Code:
  0  = allow
  2  = block (message on stderr is shown to Claude)
  other = Claude Code treats it as non-blocking error
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

SERVER_URL = os.environ.get("MEMORYCORE_SERVER_URL", "http://localhost:8000").rstrip("/")
USER_ID = os.environ.get("MEMORYCORE_USER_ID", "fitclaw")
TIMEOUT_SECONDS = int(os.environ.get("APPROVAL_TIMEOUT_SEC", "300"))
POLL_SECONDS = int(os.environ.get("APPROVAL_POLL_SEC", "3"))
ALLOWED_TOOLS = set(
    t.strip()
    for t in os.environ.get("APPROVAL_ALLOWED_TOOLS", "Read,Grep,Glob,Notebook,ToolSearch").split(",")
    if t.strip()
)

# Bash commands that never need approval — common read-only probes.
SAFE_BASH_PATTERNS = (
    "ls ", "ls\n", "pwd", "whoami", "date", "echo ", "cat ", "head ", "tail ",
    "wc ", "grep ", "rg ", "find ", "which ", "type ", "git status", "git diff",
    "git log", "git branch", "docker ps", "docker images", "docker logs",
    "kubectl get", "kubectl describe",
)

DANGEROUS_BASH_PATTERNS = (
    "rm -rf", "rm -r ", "mkfs", "dd if=", "chmod 777", "chown -R", "> /dev/",
    "systemctl stop", "systemctl disable", "systemctl restart",
    "docker rm", "docker kill", "docker system prune", "kubectl delete",
    "git push --force", "git reset --hard", "git clean -f",
    "sudo ", "curl | sh", "wget | sh", "| bash", "| sh",
)


def _needs_approval(tool_name: str, tool_input: dict) -> tuple[bool, str]:
    """Return (needs_approval, human_summary)."""
    if tool_name in ALLOWED_TOOLS:
        return False, ""

    if tool_name == "Bash":
        cmd = str(tool_input.get("command", "")).strip()
        summary = cmd[:200]
        low = cmd.lower()
        for pat in DANGEROUS_BASH_PATTERNS:
            if pat in low:
                return True, f"Bash: {summary}"
        # Small safe probes auto-approved:
        for pat in SAFE_BASH_PATTERNS:
            if low.startswith(pat):
                return False, ""
        # Unknown Bash → require approval (fail-closed).
        return True, f"Bash: {summary}"

    if tool_name in {"Write", "Edit", "NotebookEdit"}:
        path = tool_input.get("file_path") or tool_input.get("path") or "?"
        # Always approve if file is under the project; reject path climbing.
        if isinstance(path, str) and (".." in path or path.startswith("/etc") or path.startswith("/usr")):
            return True, f"{tool_name}: {path}"
        return False, ""

    # Unknown tool: fail-closed.
    return True, f"{tool_name}: {json.dumps(tool_input)[:180]}"


def _post_json(path: str, body: dict) -> dict | None:
    url = f"{SERVER_URL}{path}"
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def _get_json(path: str) -> dict | None:
    url = f"{SERVER_URL}{path}"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def main() -> int:
    try:
        payload_in = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # can't parse — don't block work

    tool_name = str(payload_in.get("tool_name") or "")
    tool_input = payload_in.get("tool_input") or {}
    session_id = str(payload_in.get("session_id") or "")

    if not tool_name:
        return 0

    needs, summary = _needs_approval(tool_name, tool_input)
    if not needs:
        return 0

    # Create the pending approval.
    created = _post_json(
        f"/api/v1/approvals?user_id={USER_ID}",
        {
            "source": "claude_code",
            "session_id": session_id,
            "tool_name": tool_name,
            "action_summary": summary[:500],
            "action_detail": {"tool_input": tool_input},
        },
    )
    if not created or "approval_id" not in created:
        # Server unreachable — fail OPEN so Claude isn't bricked offline.
        # Tradeoff: offline = no approval check. Flip this to `return 2`
        # if you want fail-closed paranoia.
        print(f"[approval] server unreachable — allowing {tool_name}", file=sys.stderr)
        return 0

    approval_id = created["approval_id"]
    print(f"[approval] waiting on human decision for {tool_name} (id={approval_id})", file=sys.stderr)

    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)
        row = _get_json(f"/api/v1/approvals/{approval_id}")
        if not row:
            continue
        status = row.get("status")
        if status == "approved":
            return 0
        if status == "denied":
            print(f"[approval] DENIED by {row.get('decided_by') or 'human'}", file=sys.stderr)
            return 2

    # Timeout → treat as denied.
    print(f"[approval] TIMEOUT after {TIMEOUT_SECONDS}s — blocking", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
