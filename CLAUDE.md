# CLAUDE.md

**Read [AGENTS.md](AGENTS.md) first.** It is the single source of truth
for project context — layout, conventions, how to log token usage,
everything. This file only contains Claude-specific notes that don't
belong in the universal file.

## Claude-specific

- A `Stop` hook at [.claude/hooks/log-usage.py](.claude/hooks/log-usage.py)
  auto-logs every session's token usage to the MemoryCore ledger. No
  action required from you — just do the work. Before your first
  session, make sure the stack is up (`docker compose ps` should show
  `api` healthy).
- If you want to disable auto-logging temporarily, comment out the
  `Stop` entry in [.claude/settings.json](.claude/settings.json).
- The user reads your text output, not your tool calls. Keep updates
  concise.

## Quick commands

```bash
# See what you spent today (and other agents' spend)
curl -s "http://localhost:8000/api/v1/memorycore/usage/summary?user_id=fitclaw&period=today" | python -m json.tool

# Or via Telegram: /usage
```

_Everything else: AGENTS.md._
