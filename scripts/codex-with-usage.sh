#!/usr/bin/env bash
# Wrapper around `codex` CLI that logs session token usage to MemoryCore
# after the command exits.
#
# Usage:
#   scripts/codex-with-usage.sh [any codex args ...]
#
# Codex CLI (OpenAI) writes session info under ~/.codex/. We read the
# latest session log after the command finishes and POST its usage to
# /api/v1/memorycore/usage. If parsing fails, we log a zero-usage row
# with a note so you know a session happened.

set -euo pipefail

SERVER_URL="${MEMORYCORE_SERVER_URL:-http://localhost:8000}"
USER_ID="${MEMORYCORE_USER_ID:-fitclaw}"
CODEX_DIR="${CODEX_HOME:-$HOME/.codex}"

codex "$@"
status=$?

# Codex stores session transcripts under ~/.codex/sessions/ (format:
# rollout-<timestamp>-<uuid>.jsonl). Pick the most recently modified.
latest=""
if [ -d "$CODEX_DIR/sessions" ]; then
  latest=$(ls -t "$CODEX_DIR/sessions"/*.jsonl 2>/dev/null | head -n 1 || true)
fi

in_tokens=0
out_tokens=0
model="unknown"
session_id="codex-$(date -u +%s)"

if [ -n "$latest" ] && [ -f "$latest" ]; then
  # jq is the natural tool but it's not universally installed. Use a
  # tiny python one-liner to parse the JSONL stream for usage fields.
  read -r in_tokens out_tokens model < <(python - "$latest" <<'PY'
import json, sys
total_in = total_out = 0
model = "unknown"
with open(sys.argv[1], "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        try:
            entry = json.loads(line)
        except Exception:
            continue
        usage = entry.get("usage") or (entry.get("message") or {}).get("usage") or {}
        total_in += int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
        total_out += int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
        m = entry.get("model") or (entry.get("message") or {}).get("model")
        if m:
            model = m
print(total_in, total_out, model)
PY
)
  session_id="$(basename "$latest" .jsonl)"
fi

body=$(python - <<PY
import json
print(json.dumps({
    "tool": "codex",
    "model": "$model",
    "session_id": "$session_id",
    "input_tokens": int("$in_tokens"),
    "output_tokens": int("$out_tokens"),
    "note": "auto-logged by codex-with-usage.sh",
}))
PY
)

curl -fsS --max-time 5 \
  -X POST "$SERVER_URL/api/v1/memorycore/usage?user_id=$USER_ID" \
  -H "Content-Type: application/json" \
  -d "$body" >/dev/null || true

exit $status
