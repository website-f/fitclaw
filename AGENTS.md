# AGENTS.md — universal project context for AI coding agents

This file is the **single source of truth** that any AI coding agent
(Claude Code, OpenAI Codex CLI, Cursor, Aider, Gemini, etc.) should read
**before** exploring the codebase. It exists to save you (and its user)
tokens and time.

If you are an agent reading this, start with the [Initialization
prompt](#initialization-prompt-for-agents) section below.

---

## Project snapshot

- **Name:** Personal AI Ops Platform (`personal-ai-ops-platform`)
- **Owner:** fitclaw (`desamurniluqman@gmail.com`)
- **Purpose:** Self-hosted AI operations brain running on a VPS. Talks
  to the user via Telegram (and a WhatsApp bridge), coordinates device
  agents (home PC, office PC, cloud workers), tracks tasks, runs
  reports, captures memory.
- **Repo:** https://github.com/website-f/fitclaw.git
- **Primary language:** Python 3.12 (FastAPI). One Go microservice
  (`services/vps_stats`) and one Go CLI (`memorycore_cli`).
- **Deployment unit:** Docker Compose. Optional Kubernetes manifests in
  [`deploy/k8s/`](deploy/k8s/) for learning.

## Architecture (what lives where)

```
personal-ai-ops-platform/
├── app/                         # Python monolith (FastAPI + Celery + PTB)
│   ├── core/                    # db, config, celery, security
│   ├── models/                  # legacy SQLAlchemy ORM (pre-module split)
│   ├── modules/                 # new plugin-style modules — see below
│   │   └── memorycore/          # usage ledger + design library
│   ├── contracts/               # shared types between modules
│   ├── routers/                 # legacy FastAPI routers
│   ├── services/                # legacy service layer
│   ├── bot/                     # Telegram bot handlers
│   ├── middleware/
│   ├── ui/                      # PWA frontend
│   └── main.py                  # FastAPI entrypoint
├── services/                    # real microservices (separate images)
│   ├── vps_stats/               # Go — host metrics
│   └── ml/                      # Python — TensorFlow/OpenCV placeholder
├── whatsapp_bridge/             # Go — WhatsApp via whatsmeow
├── memorycore_cli/              # Go CLI (tool, not service)
├── alembic/                     # db migrations — single source of truth
├── deploy/
│   ├── k8s/                     # kustomize-bundled vps_stats manifests
│   └── observability/           # Prometheus + Grafana config
├── docker-compose.yml
├── Dockerfile                   # builds python api + memorycore_cli Go
├── AGENTS.md                    # this file
├── CLAUDE.md                    # pointer to AGENTS.md + Claude-specific notes
├── LEARN.md                     # teaching journal, 11 sections, exercises
└── MIGRATE_TO_POSTGRES.md       # one-time Postgres setup runbook
```

## Stack at a glance

| Layer | Tech |
|---|---|
| API | FastAPI + uvicorn |
| DB | PostgreSQL 16 + SQLAlchemy 2.0 + psycopg3 |
| Migrations | Alembic (autogenerate from models) |
| Async tasks | Celery + Redis |
| LLMs | Ollama (local) + Gemini (cloud fallback) |
| Bot | python-telegram-bot v21 |
| Metrics service | Go stdlib + gopsutil + prometheus/client_golang |
| Observability | Prometheus + Grafana (behind `--profile observability`) |
| Optional ML | FastAPI scaffold at `services/ml/` (behind `--profile ml`) |

## Conventions and discipline

These are NOT negotiable — reading and following them saves everyone
tokens:

1. **Modular monolith, not microservices.** New features go into
   `app/modules/<name>/` with its own `register(app)`, models, schemas,
   service, api. Modules never `import` each other directly — use
   `app.contracts/`.
2. **Alembic is the sole schema authority.** Never call
   `Base.metadata.create_all()` at startup. If you change a model, run
   `alembic revision --autogenerate -m "msg"`, review the file, commit.
3. **Every table has a `user_id` column.** The app is multi-user ready
   from day one.
4. **Unknown costs store NULL.** See
   [app/modules/memorycore/pricing.py](app/modules/memorycore/pricing.py)
   — a missing price is louder than a wrong price.
5. **Ports bound to 127.0.0.1 by default.** Public exposure is opt-in
   via env vars. See `.env.example`.
6. **Migrations run before app start** in the compose `api` command
   (`sh -c "alembic upgrade head && uvicorn …"`). Don't call `init_db`
   in `@app.on_event("startup")`.
7. **Secrets are never in git.** `.gitignore` covers `.env`,
   `deploy/k8s/*secret.yaml`.

## Key commands

```bash
# Bring up the stack (from repo root)
docker compose up -d

# Generate a new DB migration after model changes
docker compose run --rm -v "/c/.../alembic/versions:/app/alembic/versions" \
  api alembic revision --autogenerate -m "describe the change"

# Build the Go CLI / services locally
cd memorycore_cli && go build -o memorycore .
cd services/vps_stats && go build -o vps_stats .

# View logs
docker compose logs -f api

# Observability stack (optional)
docker compose --profile observability up -d

# ML service (optional)
docker compose --profile ml up -d ml

# Full teardown + volumes (only if you need a clean DB)
docker compose down -v
```

## Token usage tracking (what makes this project "universal")

There's a ledger table `memory_usage` and a REST API for it. **Any
agent, any medium, any model can log usage to it.** You (the agent)
should log every significant session when you finish. The user inspects
via Telegram `/usage` command, directly via curl, or the Go CLI.

### REST endpoint (any HTTP client)

```bash
curl -X POST "http://localhost:8000/api/v1/memorycore/usage?user_id=fitclaw" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "claude_code",       // or "codex", "cursor", "aider", "api", "other"
    "model": "claude-opus-4-7",  // the exact model id
    "session_id": "abc123",      // your session id if you have one
    "input_tokens": 12000,
    "output_tokens": 800,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "note": "adding the new feature X"
  }'
```

Server auto-computes `cost_usd` from
[pricing.py](app/modules/memorycore/pricing.py).

### Go CLI

```bash
./memorycore_cli usage log --tool claude_code --model claude-opus-4-7 \
  --session abc123 --in 12000 --out 800
./memorycore_cli usage today
./memorycore_cli usage week
./memorycore_cli usage session abc123
```

### Claude Code auto-capture

[.claude/settings.json](.claude/settings.json) registers a `Stop` hook
that runs [.claude/hooks/log-usage.py](.claude/hooks/log-usage.py)
after every session — reads the transcript, sums token usage, POSTs to
the endpoint. Zero manual work.

### Codex CLI auto-capture

[scripts/codex-with-usage.sh](scripts/codex-with-usage.sh) wraps the
`codex` CLI and logs the session's usage from its own telemetry file.
If you use Codex directly, call this wrapper instead.

### Other agents

Aider: add a post-commit hook that POSTs.
Cursor: manual logging via the Go CLI at the end of a session.
Gemini / generic: manual via the REST endpoint above.

## Initialization prompt for agents

**Copy-paste this to any coding agent on your first message of a new
session. It tells the agent how to use this project's context.**

---

> **You are working in a repository at
> `c:/Users/admin/Desktop/FitriClaw/personal-ai-ops-platform` (or the
> equivalent Linux path on the VPS). Before doing anything:**
>
> 1. **Read `AGENTS.md` first.** It is the single source of truth for
>    project layout, conventions, and the token-logging protocol. Every
>    file path and module boundary you need to know about is described
>    there — use it instead of exploring the tree blindly. This saves
>    tokens.
>
> 2. **Then read `CLAUDE.md`** (if you are Claude Code) or check for
>    your agent's specific notes.
>
> 3. **If you're about to make a code change**, consult `LEARN.md` for
>    the "what was built and why" context on the relevant subsystem.
>    Sections 1–11 map directly to subsystems. Don't read it end to end
>    — jump to the section for the area you're modifying.
>
> 4. **Don't duplicate setup steps** already completed. The Postgres
>    migration has been run, initial tables exist, stack is operational.
>    Check `docker compose ps` if unsure.
>
> 5. **When your session ends, log your token usage** to the MemoryCore
>    ledger. If the system's Stop/end hook is wired for your agent,
>    this happens automatically. Otherwise POST once with:
>
>    ```
>    curl -X POST "http://localhost:8000/api/v1/memorycore/usage?user_id=fitclaw" \
>      -H "Content-Type: application/json" \
>      -d '{"tool": "<your-tool-name>", "model": "<model-id>", "session_id": "<session>", "input_tokens": <n>, "output_tokens": <n>, "note": "<one-line-summary>"}'
>    ```
>
> 6. **Respect the conventions.** If you're adding a feature, it goes
>    into `app/modules/<name>/`. If you're changing schema, you run
>    Alembic autogenerate. If you skip these, you're creating churn
>    someone (the user, or future-you) has to untangle. Don't.
>
> **Begin by reading `AGENTS.md` now. Then describe what you understand
> about this project and the task in 3 bullet points, and ask any
> clarifying questions before making changes.**

---

## Common tasks (what to do when the user asks for X)

| User asks for | You do |
|---|---|
| "add a new Telegram command" | Edit [app/bot/handlers.py](app/bot/handlers.py), add `CommandHandler(...)` + a handler fn + a `BotCommand(...)` in `post_init`. |
| "add a new API route for feature X" | Prefer creating `app/modules/x/` over adding to `app/routers/`. Follow the memorycore module shape. |
| "change the DB schema" | Edit the model → `docker compose run --rm -v "…" api alembic revision --autogenerate -m "msg"` → review + commit + `alembic upgrade head`. |
| "the bot should do something with VPS" | Use `app/services/vps_stats_service.py`. It's the only thing that should talk to the Go service. |
| "log an LLM call for tracking" | POST to `/api/v1/memorycore/usage`. See example above. |
| "save a design reference" | PUT to `/api/v1/memorycore/designs/{name}`. Image paths can be local paths or URLs. |

## How the user asks things

The user is **fitclaw**. Preferences learned from past sessions:

- Prefers terse answers. Long essays annoy him.
- Treats this as a side project and learning opportunity — don't gate-keep.
- Okay with breaking things if it teaches something; expects a short
  "report" in LEARN.md when significant surgery happens.
- Writes in mixed English and Malay sometimes. Parse charitably; ask
  if truly ambiguous.
- Wants to learn Go and Kubernetes alongside shipping features. Don't
  shy away from them when they fit.

## Testing reality

- Unit tests: sparse. Where they exist, they live alongside the code or
  in `tests/`. Growing over time.
- Integration: manual via curl / Telegram. See LEARN.md §11 for a full
  bring-up smoke-test transcript.
- Load/perf: none yet.

If you add tests, put them near the code they test (`app/modules/x/tests/`
or adjacent `_test.go` for Go).

---

_If you updated any architecture, file layout, or convention, update
this file in the same change. This file drifting from reality is how
agents start making bad decisions again._
