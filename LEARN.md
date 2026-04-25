# LEARN.md — your side-project learning log

A running journal of what we've built in this project, **why** we built it that
way, and hands-on exercises for you. Each entry is self-contained — read in
order the first time, then jump around as a reference.

When you see 💡 **Try it** blocks, stop reading and actually run the commands.
When you see 🏋️ **Homework** blocks, those are bigger tasks — do them between
sessions.

---

## Index

1. [Postgres + Alembic migration](#1-postgres--alembic-migration) — done ✅
2. [Project restructure → `app/modules/` modular monolith](#2-project-restructure--appmodules-modular-monolith) — done ✅
3. [MemoryCore v2 — usage ledger + design library (server side)](#3-memorycore-v2--usage-ledger--design-library-server-side) — done ✅
4. [Go intro — extending `memorycore_cli` with `usage` + `design` commands](#4-go-intro--extending-memorycore_cli) — done ✅
5. [Your first Go service from scratch — `vps_stats`](#5-your-first-go-service-from-scratch--vps_stats) — done ✅
6. [Telegram → `vps_stats` — first cross-service call](#6-telegram--vps_stats--first-cross-service-call) — done ✅
7. [Read-only VPS action endpoints + safe write-action design](#7-read-only-vps-action-endpoints--safe-write-action-design) — done ✅
8. [Kubernetes on k3d — porting `vps_stats` to manifests](#8-kubernetes-on-k3d--porting-vps_stats-to-manifests) — done ✅
9. [ML service scaffold — TensorFlow/OpenCV placeholder](#9-ml-service-scaffold--tensorflowopencv-placeholder) — done ✅
10. [Observability — Prometheus + Grafana across the stack](#10-observability--prometheus--grafana-across-the-stack) — done ✅
11. [Bring-up report — bugs we hit and fixed](#11-bring-up-report--bugs-we-hit-and-fixed) — done ✅
12. [Universal agent context + token auto-capture from any medium](#12-universal-agent-context--token-auto-capture-from-any-medium) — done ✅
13. [OpenClaw-style — /claude command + session pings + approval round-trip](#13-openclaw-style--claude-command--session-pings--approval-round-trip) — done ✅
14. [Multi-project fix-and-deploy loop — registry + /fix + /push + /deploy](#14-multi-project-fix-and-deploy-loop--registry--fix--push--deploy) — done ✅

**Appendix: [📚 Sandbox & learning resources](#-sandbox--learning-resources)** — Go, Python, FastAPI, Django, Docker, Kubernetes, ML, Postgres, and more.

---

## 1. Postgres + Alembic migration

### What we changed

- Swapped SQLite → Postgres 16 as the app database.
- Added **Alembic** as the schema migration tool.
- Added **psycopg3** as the Postgres driver (not the older psycopg2).
- Removed the `init_db()` / `Base.metadata.create_all()` call from app startup
  — Alembic is now the only thing that creates/alters tables.
- The `api` container now runs `alembic upgrade head` before `uvicorn`.

Files touched: [docker-compose.yml](docker-compose.yml),
[.env.example](.env.example), [app/core/config.py](app/core/config.py),
[app/main.py](app/main.py), [requirements.txt](requirements.txt),
**new**: [alembic.ini](alembic.ini), [alembic/env.py](alembic/env.py),
[alembic/script.py.mako](alembic/script.py.mako),
[MIGRATE_TO_POSTGRES.md](MIGRATE_TO_POSTGRES.md).

### Concept 1 — Why Postgres over SQLite

SQLite is a **file-based embedded database**. One process writes at a time.
Great for single-user CLIs, prototypes, mobile apps. Weak when 4 processes
(api, bot, worker, beat) all want to write simultaneously — you get
`database is locked` errors under load.

Postgres is a **server database**. Multiple clients over TCP, real
concurrency, JSONB columns, full-text search, the `pgvector` extension for
semantic search later.

**Rule of thumb:** if more than one process needs to write, don't use SQLite.

### Concept 2 — Why psycopg3 over psycopg2

Both are Python drivers for Postgres. psycopg2 (2012-ish) is what every
tutorial shows. psycopg3 (2021+) is the rewrite — better async support,
cleaner API, actively developed. We chose psycopg3 because there's no reason
to adopt a 10-year-old library in a new project. SQLAlchemy supports both.

The URL scheme `postgresql+psycopg://…` tells SQLAlchemy to use psycopg3.
`postgresql://…` or `postgresql+psycopg2://…` would use psycopg2.

### Concept 3 — What Alembic actually does

Your SQLAlchemy models in `app/models/*.py` describe what tables *should*
look like. But the database has its own copy. Alembic closes that gap.

It keeps a folder of **migration files** — each one a small Python script
describing a change:

```python
def upgrade():
    op.add_column("tasks", sa.Column("priority", sa.Integer))

def downgrade():
    op.drop_column("tasks", "priority")
```

Alembic writes the current revision hash into a tiny table called
`alembic_version` in your database. That's how it knows which migrations
have already been applied.

### Concept 4 — The autogenerate magic (and its limits)

`alembic revision --autogenerate -m "msg"` compares your SQLAlchemy models
against the live DB and writes a migration describing the diff. Fast,
usually correct.

**What it catches:** new tables, new columns, new indexes, column type
changes, foreign keys.

**What it misses (you must hand-edit):**
- Column renames — shows up as `drop_column` + `add_column` (data loss!).
  Rename manually: `op.alter_column("table", "old", new_column_name="new")`.
- Check constraints.
- Server-side defaults like `now()`.
- Enum value additions.
- Data migrations (copying data from one column to another).

**Always open the generated file before committing.**

### 💡 Try it — run the Postgres migration

You haven't actually run this yet. Open
[MIGRATE_TO_POSTGRES.md](MIGRATE_TO_POSTGRES.md) and go through steps 1–7.
Watch the logs as each service comes up.

Then:

```bash
docker compose exec postgres psql -U aiops -d aiops
```

You're now inside Postgres. Useful commands:

| psql command | What it does |
|---|---|
| `\l` | list databases |
| `\c dbname` | connect to a different database |
| `\dt` | list tables in current database |
| `\d tablename` | describe a table's columns + indexes |
| `\du` | list users |
| `SELECT * FROM alembic_version;` | see current migration revision |
| `\q` | quit |

Poke around. Look at the structure of a few tables. Check
`alembic_version` matches the hash of your baseline migration file.

### 🏋️ Homework 1.1 — Make a tiny schema change end-to-end

Goal: feel the full Alembic loop yourself.

1. Open [app/models/task.py](app/models/task.py).
2. Add a new column: `priority: Mapped[int] = mapped_column(default=0)`.
   (Don't worry about semantics — you'll delete it after.)
3. Run: `docker compose run --rm api alembic revision --autogenerate -m "add task priority"`.
4. Open the new file in `alembic/versions/`. Read it. Understand each line.
5. Run: `docker compose run --rm api alembic upgrade head`.
6. Verify in psql: `\d tasks` — should show the new column.
7. Now roll it back: `docker compose run --rm api alembic downgrade -1`.
8. Verify: column is gone.
9. Finally, undo your model change and delete the migration file.

You've just done what you'll do every time you change schema for the rest
of this project.

### 🏋️ Homework 1.2 — Break something on purpose

1. Stop Postgres: `docker compose stop postgres`.
2. Try to hit the API. Watch it fail. Read the error.
3. Start Postgres again. Watch the API recover (the `pool_pre_ping=True` in
   [app/core/database.py](app/core/database.py) is why — it checks
   connections before handing them out).

Understanding failure modes > understanding success paths.

### 🏋️ Homework 1.3 — Read about these when you have 15 minutes each

- **JSONB in Postgres** — https://www.postgresql.org/docs/current/datatype-json.html
  (we'll use this for tags/preferences columns in MemoryCore v2)
- **Connection pooling** — why PgBouncer exists:
  https://www.pgbouncer.org/usage.html (you'll want this when you have
  real traffic)
- **Alembic autogenerate limitations** —
  https://alembic.sqlalchemy.org/en/latest/autogenerate.html#what-does-autogenerate-detect-and-what-does-it-not-detect

### Gotchas I almost hit

- **Driver name.** `postgresql+psycopg://` means psycopg3. `postgresql://`
  defaults to psycopg2 if both are installed. We pin explicitly.
- **`create_all` + Alembic together = confusion.** If you keep both, Alembic
  thinks the DB schema matches a revision that doesn't exist yet, and the
  next `revision --autogenerate` wants to re-create every table. We removed
  `create_all` from startup. Alembic is the *only* source of truth now.
- **Don't commit `.env`.** It's already in `.gitignore`. The password you
  put in there is real.

### What's next (section 2 preview)

We'll create the new `app/modules/` layout, move nothing yet, and build
`app/modules/memorycore/` as the **reference module**. After that, every
feature we touch gets moved into a module opportunistically. No big-bang
refactor.

---

## 2. Project restructure → `app/modules/` modular monolith

### What we changed

- Created [app/contracts/](app/contracts/) — place for typed payloads shared
  between modules.
- Created [app/modules/](app/modules/) — each subpackage is a module with a
  single `register(app)` entry point.
- Created [app/modules/memorycore/](app/modules/memorycore/) as the **first**
  module following this pattern. We'll extract others opportunistically over
  time, not in a big-bang rewrite.
- Wired [app/main.py](app/main.py) to call `register_all_modules(app)` after
  all legacy routers are included.
- Updated [alembic/env.py](alembic/env.py) to also `import app.modules` so
  Alembic autogenerate sees module-owned tables.

### Concept 1 — Monolith vs microservices vs modular monolith

There are three architectures in play. Forget buzzwords and focus on the
actual trade:

| Shape | What you pay | What you get |
|---|---|---|
| **Big-ball-of-mud monolith** | Everything tangled; changing A breaks B | One deploy, shared DB transaction, fast dev |
| **Microservices** | Network hops, distributed transactions, 10× infra | Independent scaling + independent deploys |
| **Modular monolith** | Self-discipline (no sneaky cross-imports) | 90% of monolith's speed + 80% of microservices' clarity |

We chose **modular monolith** — one app, one deploy, one DB — but with **hard
internal boundaries** so a module could be extracted into a microservice
later with cheap work, not a rewrite. This is what most "microservices" teams
should have built before scaling up.

### Concept 2 — Why each module is a package with a `register(app)` function

Two reasons:

1. **Central wiring.** [app/modules/__init__.py](app/modules/__init__.py) has
   one line per module. To disable a module in a branch, comment one line.
   To add one, write one. No hunting through `main.py`.
2. **Uniform shape.** Every module exposes the same contract:
   `register(app: FastAPI) -> None`. Future modules can also attach celery
   beat schedules, startup hooks, Telegram command handlers — the signature
   can evolve, and every module evolves together.

Look at [app/modules/memorycore/__init__.py](app/modules/memorycore/__init__.py):

```python
def register(app: FastAPI) -> None:
    app.include_router(router)
```

That's the whole glue. No imports from `app.routers.*`, no global state, no
magic.

### Concept 3 — The "contracts" boundary rule

This is the load-bearing discipline. **Modules never import from each other
directly.**

```python
# BAD — tight coupling, A "knows" how B works inside
from app.modules.tasks.service import TaskService
TaskService.create(db, ...)

# GOOD — loose coupling, A only knows B's contract
from app.contracts.task import TaskCreationRequest
# ...somehow get a reference to a task-creator dependency...
task_creator.create(TaskCreationRequest(...))
```

Three ways modules can talk, in increasing looseness:

1. **Shared types + injected dependency** (what we'll usually do). Contract
   defines the types, FastAPI's `Depends(...)` injects a concrete
   implementation, the module being called exposes that implementation.
2. **Celery events.** Fire-and-forget messages. Module A pushes to a queue,
   module B consumes. No synchronous link at all.
3. **HTTP over localhost.** Last resort inside a monolith — use this only
   when you're about to split a module into its own service.

For now MemoryCore has no cross-module dependencies, so we haven't had to
exercise this. When we add the next module (chat linking to usage rows by
session_id), we'll introduce the first contract. I'll narrate that when it
happens.

### Concept 4 — Why the module owns its own models

[app/modules/memorycore/models.py](app/modules/memorycore/models.py) holds
`MemoryUsage` and `DesignReference`. They live *inside the module*, not in
the global `app/models/` directory.

Why: if one day we split MemoryCore into a separate service, the entire
module folder moves as one. Its models, schemas, service, and routes are all
right there. No hunting.

The legacy models in [app/models/](app/models/) stay where they are for now.
As we migrate modules, each module takes its models with it. Eventually
`app/models/` is empty and we delete it.

**One Alembic wrinkle:** Alembic autogenerate only sees tables whose classes
are imported at the time `alembic revision --autogenerate` runs. We fixed
this by adding `import app.modules` to [alembic/env.py](alembic/env.py) —
which transitively imports every module's `models.py`. Whenever you add a
new module, this Just Works; you don't have to remember anything.

### 💡 Try it — verify the restructure

From the project root:

```bash
tree app/modules app/contracts -L 2
# or, if you don't have tree:
find app/modules app/contracts -maxdepth 2
```

You should see the scaffolding and the populated `memorycore` module.

Then, assuming Postgres is up from section 1:

```bash
docker compose restart api
docker compose logs api --tail 50
```

You should see uvicorn boot with no import errors. If it imports, the
wiring is correct.

### 🏋️ Homework 2.1 — Make a stub module

Goal: feel the module pattern by adding one yourself.

1. Create `app/modules/hello/` with:
   - `__init__.py` exposing `register(app)` that includes a router
   - `api.py` with a router exposing `GET /api/v1/hello` → returns `{"ok": true}`
2. Add `_hello` to the tuple in
   [app/modules/__init__.py](app/modules/__init__.py).
3. Restart the api container.
4. `curl http://localhost:8000/api/v1/hello` — should return your payload.
5. Remove the module (delete folder + remove from tuple). Restart. Confirm
   route is gone.

This is the drill you'll repeat every time we add a module.

### 🏋️ Homework 2.2 — Read about the pattern

- **Shopify's modular monolith write-up** —
  https://shopify.engineering/shopify-monolith — how they handle module
  boundaries at massive scale without splitting into microservices.
- **The "Majestic Monolith"** — https://signalvnoise.com/svn3/the-majestic-monolith/
  — short, opinionated, worth 10 minutes.

### Gotchas I almost hit

- **Forgetting to import module models in Alembic env.py.** If you skip this,
  autogenerate thinks your new tables don't exist and generates a migration
  that drops them. The `import app.modules` line in env.py prevents this.
- **Module importing from another module directly.** The first time this
  happens, the rule is violated and never gets fixed. I'll catch it in code
  review. You should too.
- **Circular imports.** `app/modules/__init__.py` imports submodules; if a
  submodule tries to `from app.modules import something` at import time,
  Python explodes. Submodules only import from `app.contracts`, `app.core`,
  `app.models` (legacy), or standard libs.

### What's next (section 3 preview)

Section 3 explains what's actually *in* the memorycore module — the token
ledger and design library. Section 4 (next session) will be your first Go
lesson: extending [memorycore_cli/main.go](memorycore_cli/main.go) to call
these endpoints.

---

## 3. MemoryCore v2 — usage ledger + design library (server side)

### What we built

Two new SQL tables and a small API, scoped to exactly what you asked for:

1. **`memory_usage`** — one row per LLM call. Tracks user, tool
   (claude_code / codex / api), model, session, project, input/output/cache
   tokens, cost in USD, optional note, timestamp.
2. **`memory_design`** — one row per frontend design reference. Unique per
   `(user_id, name)`. Holds prompt, title, description, tags (JSONB), image
   paths (JSONB), optional source URL + project key.

API endpoints (all under `/api/v1/memorycore/`):

| Method | Path | Purpose |
|---|---|---|
| POST | `/usage?user_id=…` | Log a single LLM call |
| GET | `/usage/summary?user_id=…&period=today\|week\|month` | Aggregated totals |
| GET | `/usage/sessions/{session_id}?user_id=…` | All rows for one session |
| PUT | `/designs/{name}?user_id=…` | Create or update a design |
| GET | `/designs?user_id=…&q=…&tag=…` | List / search |
| GET | `/designs/{name}?user_id=…` | Fetch one by name |
| DELETE | `/designs/{name}?user_id=…` | Remove |

Files:
- [app/modules/memorycore/models.py](app/modules/memorycore/models.py) — ORM
- [app/modules/memorycore/schemas.py](app/modules/memorycore/schemas.py) — Pydantic
- [app/modules/memorycore/service.py](app/modules/memorycore/service.py) — business logic
- [app/modules/memorycore/api.py](app/modules/memorycore/api.py) — FastAPI router
- [app/modules/memorycore/pricing.py](app/modules/memorycore/pricing.py) — pricing table

### Concept 1 — Why cost can be `NULL`

[pricing.py](app/modules/memorycore/pricing.py) has a small dict of model →
(input_rate, output_rate) per 1M tokens. Unknown models return `None`, which
becomes SQL `NULL` in the cost column.

This is on purpose: a missing price is louder than a wrong price. If you see
`NULL` in the summary's total cost, you know to add the model to the pricing
table. If we faked it with `0.0`, the silent-wrong bug would live forever.

**Rule I want you to internalize:** when you don't know something, store
`NULL`, not a fake sentinel. SQL has nullability for a reason; use it.

### Concept 2 — Why the usage ledger is append-only

Every `POST /usage` creates a new row. We never UPDATE or DELETE usage
rows. Reasons:

1. **Audit.** If cost reconciliation disagrees with an invoice later, you
   want raw history.
2. **Simpler code.** No update logic = no race conditions = no "what if two
   writers update the same row" edge cases.
3. **Cheap writes.** Inserts are fast; Postgres does ~30k inserts/sec on
   modest hardware. You will not outrun this.

Aggregations happen at read time (`/usage/summary`). Postgres is good at
this. If it gets slow later (tens of millions of rows), we add a daily
rollup table maintained by Celery beat. Don't optimize until you see the
number.

### Concept 3 — Why `tags` is JSONB, not a join table

Two options for "a design has many tags":

- **Normalized:** separate `design_tags` table with `(design_id, tag)` rows
  and a join.
- **Denormalized:** `tags` column as a JSON array on the `memory_design`
  row.

Normalized is textbook-correct. We chose denormalized because:

1. Tags aren't first-class entities. There's no page listing "all tags" with
   metadata. They're just labels.
2. JSONB on Postgres is indexed (`GIN` index if needed later). Search works.
3. One fewer table = less cognitive load for you.

If tags ever become first-class (e.g., "rename the tag `dark` everywhere"),
we migrate to a join table. Until then, YAGNI.

### Concept 4 — The upsert pattern

[service.py](app/modules/memorycore/service.py) `DesignService.upsert` does
this:

```python
existing = db.execute(select(...).where(user_id=..., name=...)).scalar_one_or_none()
if existing is None:
    row = DesignReference(...)
    db.add(row)
else:
    existing.field = new_value
    # ...
    row = existing
db.commit()
db.refresh(row)
return row
```

This is naive — there's a race: two concurrent PUTs with the same name can
both see `existing is None` and both INSERT. The second INSERT violates the
unique constraint and errors out.

For your single-user side project this is fine — you won't have two writers
racing. If it ever matters, Postgres has native `INSERT … ON CONFLICT
… DO UPDATE` (upsert), and SQLAlchemy 2.0 supports it via
`sqlalchemy.dialects.postgresql.insert`. We'll swap to that the day two
callers start fighting.

### Concept 5 — Why `user_id` is on every row and every query

The app is built for one user today, but every table has `user_id` because
multi-user is always a later regret-free addition if you start with it.
Adding `user_id` to a table later is a painful migration; having it from
day one costs nothing.

Every query filters `WHERE user_id = ?`. Even for your single-user setup
this prevents nothing-sees-nothing bugs from becoming everyone-sees-everyone
bugs on day one of multi-user.

### 💡 Try it — poke the API

Assuming the stack is up from section 1 and section 2 wiring is in place:

```bash
# Generate a new migration that includes memory_usage + memory_design
docker compose run --rm api alembic revision --autogenerate -m "add_memorycore_v2_tables"

# Review the generated file in alembic/versions/, then:
docker compose run --rm api alembic upgrade head
```

Verify the tables exist:

```bash
docker compose exec postgres psql -U aiops -d aiops -c "\dt"
# Look for memory_usage + memory_design
docker compose exec postgres psql -U aiops -d aiops -c "\d memory_usage"
```

Log a fake usage row and read the summary:

```bash
# Log one call
curl -X POST "http://localhost:8000/api/v1/memorycore/usage?user_id=fitclaw" \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "claude_code",
    "model": "claude-opus-4-7",
    "session_id": "sess-demo",
    "input_tokens": 1200,
    "output_tokens": 300,
    "note": "testing from LEARN.md"
  }'

# Summary for today
curl "http://localhost:8000/api/v1/memorycore/usage/summary?user_id=fitclaw&period=today" | python -m json.tool
```

You should see cost calculated automatically from
[pricing.py](app/modules/memorycore/pricing.py) — for 1200 in + 300 out on
claude-opus-4-7 at $15/$75 per 1M, that's $0.018 + $0.0225 = **$0.0405**.

Save a design reference:

```bash
curl -X PUT "http://localhost:8000/api/v1/memorycore/designs/dashboard-v2?user_id=fitclaw" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "dashboard-v2",
    "title": "Dashboard v2",
    "prompt": "dark glassmorphism admin dashboard with purple accents",
    "tags": ["dashboard", "dark", "glassmorphism"],
    "image_paths": ["/data/memorycore/designs/dashboard-v2/shot1.png"]
  }'

# Find it
curl "http://localhost:8000/api/v1/memorycore/designs?user_id=fitclaw&q=dashboard" | python -m json.tool
curl "http://localhost:8000/api/v1/memorycore/designs?user_id=fitclaw&tag=dark" | python -m json.tool
```

### 🏋️ Homework 3.1 — Add an unknown-model warning to the logs

Goal: understand the `None`-cost case and exercise editing service code.

1. In [service.py](app/modules/memorycore/service.py) `UsageService.log`,
   after computing cost, if `cost is None` emit a log line like
   `WARN: no pricing for model 'X' — cost not tracked`.
2. Use `import logging` + a module-level `logger = logging.getLogger(__name__)`.
3. Restart the api. Log a row with `"model": "made-up-model"`. Check
   logs: `docker compose logs api --tail 50 | grep WARN`.
4. Log a row with `"model": "claude-haiku-4-5"`. No warning.

You just learned: logging, module-level loggers, how to verify behavior via
logs instead of the database.

### 🏋️ Homework 3.2 — Add `by_project` to the summary

Goal: exercise the service + schema loop.

1. Add `by_project: dict[str, UsageBreakdown]` to
   [schemas.py](app/modules/memorycore/schemas.py) `UsageSummaryResponse`.
2. Update [service.py](app/modules/memorycore/service.py) `summary()` to
   accumulate a `by_project` dict keyed on `row.project_key or "(none)"`.
3. Restart api. Hit `/usage/summary`. You should see `by_project` in the
   response.

You just learned: keeping schema and service in sync, and how Pydantic
validates responses.

### 🏋️ Homework 3.3 — Explore the OpenAPI docs

FastAPI auto-generates interactive docs at http://localhost:8000/docs.
Every endpoint we just built is there, clickable, with a "Try it out" button.

Open it. Find the `memorycore-v2` tag section. Try the usage log endpoint
through the UI. This is often faster than curl for exploration.

### Gotchas I almost hit

- **Cost can be `None`** — callers must handle it. The summary treats it as
  0.0 for sums, which is the least-surprising behavior. If you want the
  summary to *refuse* to sum when any cost is unknown, that's a separate
  design choice.
- **The unique index on `(user_id, name)` is in `__table_args__`.** If you
  forget it, two designs can share a name per user and `get()` will raise
  `MultipleResultsFound`.
- **`from sqlalchemy import func, or_` is imported lazily inside
  `list()`.** This keeps the module load cheap when nobody searches. You
  could also import at top of file — either is fine.

### What's next (section 4 preview)

Section 4: **your first Go lesson.** We'll open the existing
[memorycore_cli/main.go](memorycore_cli/main.go), read it line by line, and
extend it with `memorycore usage today` and `memorycore design save`
commands that talk to the server we just built. You'll write Go, I'll
review, and LEARN.md will pick up the Go idioms as we go.

---

## 4. Go intro — extending `memorycore_cli`

### What we built

Extended the existing Go CLI at [memorycore_cli/main.go](memorycore_cli/main.go)
with two new subcommands that hit the MemoryCore v2 server we built in
section 3.

New files:
- [memorycore_cli/usage.go](memorycore_cli/usage.go) — token-usage commands
- [memorycore_cli/design.go](memorycore_cli/design.go) — design-library commands

Edited: [memorycore_cli/main.go](memorycore_cli/main.go) — dispatch logic in
`main()` recognizes `usage` / `design` as structured subcommands, falls
through to natural-language mode otherwise.

**What you can now run** (once the stack is up):

```bash
# Log one LLM call
./memorycore_cli usage log --model claude-opus-4-7 --session sess-demo --in 1200 --out 300

# Summaries
./memorycore_cli usage today
./memorycore_cli usage week
./memorycore_cli usage month

# Everything in a session
./memorycore_cli usage session sess-demo

# Save a design reference
./memorycore_cli design save --name dashboard-v2 \
  --title "Dashboard v2" \
  --prompt "dark glassmorphism admin dashboard, purple accents" \
  --tag dashboard --tag dark --tag glassmorphism \
  --image /path/to/shot1.png

# List / search designs
./memorycore_cli design list
./memorycore_cli design list --query dashboard
./memorycore_cli design list --tag dark

# Show one design (prompt + image paths — what Claude reads to "recall" it)
./memorycore_cli design show dashboard-v2

# Remove
./memorycore_cli design delete dashboard-v2
```

### Concept 1 — How a Go program is laid out

Your package is defined by `package main` at the top of every `.go` file in
the folder. The compiler treats **all files in the same folder as one
package**. This is why `usage.go` and `design.go` can call `requestJSON`
from `main.go` without any import — they're in the same package.

That's different from Python, where each file is a module and you `import`
between them. In Go, a folder = a package = one unit of code.

`main` is special: it's the only package that produces an executable, and
it must contain a `func main()` entry point.

Your project's [go.mod](memorycore_cli/go.mod) file is the equivalent of
Python's `requirements.txt` + `pyproject.toml` combined. It defines:
- the **module name** (used as the base for import paths)
- the **Go version**
- the **dependencies** (currently none — we only use the stdlib)

### Concept 2 — Struct tags and how JSON works

Look at this from [usage.go](memorycore_cli/usage.go):

```go
type usageLogPayload struct {
    Tool         string `json:"tool"`
    SessionID    string `json:"session_id,omitempty"`
    InputTokens  int    `json:"input_tokens"`
}
```

The backtick-quoted string after each field is a **struct tag** —
metadata the compiler stores but doesn't interpret. `encoding/json` reads
it to know:

- The field `SessionID` serializes as JSON key `"session_id"`.
- `omitempty` skips the field when empty (so an empty string doesn't become
  `"session_id": ""` in the body).

This is how you bridge Go's `PascalCase` (required for exported fields) and
Python's `snake_case` (the convention of our server).

**Common tag options** across stdlib + popular libs:

| Tag | Meaning |
|---|---|
| `json:"foo"` | serialize as key `"foo"` |
| `json:"foo,omitempty"` | skip if zero value |
| `json:"-"` | never serialize |
| `xml:"foo"` | for encoding/xml |
| `yaml:"foo"` | for gopkg.in/yaml |
| `db:"foo"` | for sqlx/pgx |

### Concept 3 — Pointers, zero values, and nullable fields

Go has **zero values**. A declared-but-unassigned `int` is `0`, a `string`
is `""`, a `bool` is `false`. Helpful, but it creates a problem: how do
you distinguish "the server said cost is zero" from "the server said cost
is null (no pricing data)"?

Answer: **pointer**. A `float64` is never nil; a `*float64` is either a
pointer to a value or `nil`.

```go
type usageLogResponse struct {
    CostUSD *float64 `json:"cost_usd"`
}

func formatCost(cost *float64) string {
    if cost == nil {
        return "(unknown)"
    }
    return fmt.Sprintf("$%.6f", *cost)
}
```

The `*` in the type says "pointer to"; the `*cost` inside the format call
says "dereference — give me the actual value." When `encoding/json` sees a
JSON `null` and the Go field is a pointer, it sets the field to `nil`
instead of the zero value.

**Rule:** when you need to represent "missing" vs "zero," use a pointer.
Everywhere else, values are cleaner and safer.

### Concept 4 — Slices and the nil-vs-empty gotcha

Go slices are backed by dynamic arrays. `append(slice, value)` grows them.
But a declared-but-unassigned slice is **nil**, not empty:

```go
var tags []string              // tags is nil
len(tags)                      // 0 — works fine
tags = append(tags, "foo")     // works; append handles nil

// But when you marshal to JSON:
json.Marshal(tags)             // → "null"  (uh oh)

tags = []string{}              // now it's empty-not-nil
json.Marshal(tags)             // → "[]"
```

In [design.go](memorycore_cli/design.go) we initialize:

```go
payload := designPayload{
    Tags:       []string{},
    ImagePaths: []string{},
}
```

...exactly to dodge this — Pydantic on the server is strict about `null`
vs `[]`, and we want clean bodies.

### Concept 5 — Error handling

Go has no exceptions. Functions that can fail return `(result, error)`:

```go
n, err := strconv.Atoi(args[index])
if err != nil {
    return fmt.Errorf("--in: %w", err)
}
```

Two rules every Go dev learns hard:

1. **Always check `err` immediately.** The compiler won't warn you if you
   ignore it (it would ruin existing code), but reviewers will.
2. **Wrap errors with context using `%w`.** `fmt.Errorf("--in: %w", err)`
   creates a new error that wraps the original — callers can still
   `errors.Is()` / `errors.As()` it, but they also see what was happening
   when it failed.

This feels verbose compared to Python's `try/except`, but after a while
you stop noticing it. The payoff: the entire error path is visible in the
code, no hidden unwinding.

### Concept 6 — Interfaces (briefly)

You didn't write any interfaces in this extension, but you used one:
`io.Reader`. The whole stdlib works against interfaces rather than
concrete types.

```go
var reader io.Reader = bytes.NewReader(payload)
```

`bytes.NewReader` returns a `*bytes.Reader`. That type satisfies
`io.Reader` **implicitly** — there's no `class MyReader(io.Reader)` in
Go. If your type has the right methods, it satisfies the interface.
Nobody has to tell the compiler.

This is the best thing about Go. We'll dig in when we build `vps_stats` in
section 5 — that service actually defines its own interfaces.

### 💡 Try it — compile, run, poke

Build the binary (you'll need Go installed:
https://go.dev/doc/install):

```bash
cd memorycore_cli
go build -o memorycore_cli .
```

Then run — it'll talk to `http://localhost:8000` by default, override with
`--server-url` or `MEMORYCORE_SERVER_URL` env var:

```bash
./memorycore_cli usage log --model claude-opus-4-7 --session sess-demo --in 1200 --out 300
./memorycore_cli usage today
```

The `go build .` command compiles all `.go` files in the current folder
into one binary. The argument `.` means "this folder is the package root."

### Sandbox resources — bookmark these

Go has the best learning resources of any mainstream language. You do
**not** need to buy a book or course.

| Link | What it's for |
|---|---|
| https://go.dev/play/ | **Go Playground** — online compiler, run any snippet, share links |
| https://go.dev/tour/welcome/1 | **A Tour of Go** — official interactive tutorial, 2–3 evenings end to end |
| https://gobyexample.com/ | **Go by Example** — annotated examples for every concept, great reference |
| https://go.dev/doc/effective_go | **Effective Go** — idioms and style, official |
| https://exercism.org/tracks/go | **Exercism** — practice problems with mentor feedback, free |
| https://learngo.gitbook.io/learn-go | **learn-go-with-tests** — TDD-style, deeper |
| https://go.dev/doc/faq | **Official FAQ** — answers a lot of "why does Go do X" questions |

Specific Playground links for concepts in this section (click to run, edit,
share):

- Struct tags and JSON: https://go.dev/play/p/g4y3rvePTzC
- Pointers and nil: https://go.dev/play/p/3XyZ14CM71P
- Slices and append: https://go.dev/play/p/7vljOh1sWuF
- Error wrapping: https://go.dev/play/p/0BFKxIkfk2K

(If a link 404s, the Playground garbage-collected it — just recreate the
snippet. The concept explanations stand alone.)

### 🏋️ Homework 4.1 — Tour of Go, sections 1–3

Do at least the first three sections of https://go.dev/tour/welcome/1
("Basics", "Flow control statements", "More types"). ~60 minutes. Don't
skip — these build the muscle memory you'll need when we write
`vps_stats` next session.

### 🏋️ Homework 4.2 — Add an export subcommand

Goal: write Go from scratch against code you understand.

Add `memorycore usage export [--out PATH]` that writes all usage rows as
a CSV file.

Hints:
- You'll need a new endpoint on the server side returning all rows
  (add to [app/modules/memorycore/api.py](app/modules/memorycore/api.py)
  and [service.py](app/modules/memorycore/service.py) — call it
  `list_all(user_id, limit=10000)`).
- Go stdlib has `encoding/csv` which is exactly what you need.
- Default output path: `./memorycore-usage-YYYY-MM-DD.csv`. Use
  `time.Now().Format("2006-01-02")` — Go's date format is weird (it's a
  reference date, not a format string; look it up, it's a meme).

Expected output:

```
$ ./memorycore_cli usage export
Wrote 47 rows to memorycore-usage-2026-04-24.csv
```

This exercise covers: a new server endpoint + a new Go subcommand + file
I/O + stdlib CSV. A real mini-project, ~2 hours.

### 🏋️ Homework 4.3 — Read one function of the existing code and explain it to yourself

Pick [`requestJSON` in main.go](memorycore_cli/main.go) (around line 353).
Read it line by line. Answer these without looking anything up:

1. What does `*http.Request` mean vs `http.Request`? Why does
   `http.NewRequest` return a pointer?
2. Why is there a `defer resp.Body.Close()`? What would happen without it?
3. What does `json.NewDecoder(resp.Body).Decode(out)` do differently from
   `json.Unmarshal(body, out)`?
4. Why is `out` of type `any`? What's the tradeoff?

Write your answers as comments at the top of your scratch file. Don't
worry about being "right" — just forming the hypothesis is the exercise.
We'll compare next session.

### Gotchas I almost hit

- **`map` iteration is random.** Go deliberately randomizes map iteration
  order to prevent people from relying on it. That's why
  `printBreakdownMap` does `sort.Strings(keys)` before printing —
  otherwise the same input gives different-ordered output.
- **Re-assigning slice elements via range.** `for _, row := range rows {
  row.Foo = "x" }` does NOT mutate `rows` — `row` is a copy. Use
  `for i := range rows { rows[i].Foo = "x" }` if you need to mutate.
- **`errors.New` vs `fmt.Errorf`.** Use `errors.New("literal")` for
  static messages. Use `fmt.Errorf("...%w", err)` when you need
  formatting or wrapping.
- **Multi-file packages need `go build .`, not `go build main.go`.** The
  latter only compiles that one file and misses `usage.go`/`design.go`.

### What's next (section 5 preview)

Section 5: **your first Go service from scratch**.

We'll build `tools/vps_stats/` — a ~300-line Go HTTP service that exposes
`/stats` returning JSON with CPU, RAM, disk, uptime. Runs as a 4th
microservice in your docker-compose. Your FastAPI bot calls it for the
"what's my RAM?" Telegram feature we're heading toward.

You'll learn: writing a Go HTTP server (not just a client), goroutines,
interfaces, Docker multi-stage builds, and how to introduce a new service
to your compose stack cleanly.

---

## 5. Your first Go service from scratch — `vps_stats`

### What we built

A tiny Go HTTP service exposing host system metrics, wired into
docker-compose. This is the VPS-stats feed we'll use later for
"what's my RAM?" Telegram commands.

Files:
- [services/vps_stats/main.go](services/vps_stats/main.go) — HTTP server, auth middleware
- [services/vps_stats/stats.go](services/vps_stats/stats.go) — gopsutil-based collector
- [services/vps_stats/go.mod](services/vps_stats/go.mod) + `go.sum` — module + dep lock
- [services/vps_stats/Dockerfile](services/vps_stats/Dockerfile) — multi-stage build
- [services/vps_stats/.dockerignore](services/vps_stats/.dockerignore) — keep the build context tiny

Wiring:
- [docker-compose.yml](docker-compose.yml) — new `vps_stats` service
- [.env.example](.env.example) — `VPS_STATS_*` vars

### What it returns

`GET /stats` → JSON:

```json
{
  "collected_at": "2026-04-24T12:30:45Z",
  "hostname": "vps-01",
  "cpu_percent": 4.21,
  "cpu_cores": 4,
  "mem_used_mb": 2134,
  "mem_total_mb": 7972,
  "mem_percent": 26.77,
  "disk_used_gb": 38.41,
  "disk_total_gb": 78.72,
  "disk_percent": 48.8,
  "uptime_sec": 491023,
  "load_avg_1": 0.12,
  "load_avg_5": 0.22,
  "load_avg_15": 0.19,
  "processes": 174
}
```

`GET /health` → `200 ok`. Used by Docker's healthcheck.

### Concept 1 — Go HTTP servers in 5 lines

```go
mux := http.NewServeMux()
mux.HandleFunc("/health", handleHealth)
mux.HandleFunc("/stats", handleStats)
http.ListenAndServe(":8090", mux)
```

That's it. No framework. `net/http` is the stdlib — every real Go HTTP
server, from Kubernetes' API server to Docker itself, starts this way.

**Handler signature:** `func(w http.ResponseWriter, r *http.Request)`. You
write response bytes to `w`; you read path/headers/body from `r`. That's
it. No request object magically parsed for you, no decorators, no
framework conventions.

The ecosystem has libraries like `chi`, `gin`, `echo` that add routing
sugar. We don't need them for this service. Keep in mind: **stdlib first,
dependencies only when you feel the pain.** That's the Go way.

### Concept 2 — Middleware via function wrapping

Look at [main.go](services/vps_stats/main.go):

```go
mux.HandleFunc("/stats", withAuth(handleStats))

func withAuth(next http.HandlerFunc) http.HandlerFunc {
    return func(w http.ResponseWriter, r *http.Request) {
        if apiToken == "" { next(w, r); return }
        if r.Header.Get("Authorization") != "Bearer "+apiToken {
            http.Error(w, "unauthorized", http.StatusUnauthorized)
            return
        }
        next(w, r)
    }
}
```

`withAuth` takes a handler, returns a new handler that does auth first
then delegates. **This is middleware in Go.** No decorators, no interfaces
— just higher-order functions.

You can chain: `withAuth(withLogging(withRateLimit(handleStats)))`. The
outermost wrapper runs first. That's it. Whole mental model.

### Concept 3 — `context.Context` threading

Every gopsutil call we make takes a `ctx` argument:

```go
percents, err := cpu.PercentWithContext(ctx, 300*time.Millisecond, false)
```

The `ctx` came from `r.Context()` on the HTTP request. Why does this
matter? **If the client disconnects mid-request, the context is canceled,
and gopsutil can abort any blocking syscall in progress.** You get
automatic timeout/cancellation propagation for free, all the way down.

This is Go's answer to async/await in other languages. Goroutines handle
concurrency; contexts handle cancellation and deadlines. Learn these two
and you have 80% of concurrency in Go.

### Concept 4 — Multi-stage Docker builds

Look at [Dockerfile](services/vps_stats/Dockerfile):

```dockerfile
FROM golang:1.24-alpine AS builder        # 300+ MB — has Go toolchain
WORKDIR /src
COPY go.mod ./
RUN go mod download || true
COPY . .
RUN go mod tidy && CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /out/vps_stats .

FROM alpine:3.20                           # ~5 MB base
RUN apk add --no-cache ca-certificates tzdata wget
COPY --from=builder /out/vps_stats /usr/local/bin/vps_stats
ENTRYPOINT ["/usr/local/bin/vps_stats"]
```

The first stage compiles. The second stage starts fresh from a ~5 MB
image and only copies the compiled binary. Final image is **~15 MB**
instead of ~800 MB.

Key flags:
- `CGO_ENABLED=0` — pure Go binary, no glibc dependency. Runs on anything.
- `GOOS=linux` — cross-compile for Linux even if you're on Windows/Mac.
- `-ldflags="-s -w"` — strip debug info. ~30% smaller binary.

This pattern is standard for any compiled-language microservice. **Your
production containers should never ship compilers.**

### Concept 5 — Host metrics from inside a container

Containers see their own limited view of the world. `mem.VirtualMemory()`
inside Docker returns the container's memory limit, not the host's. Same
for CPU, disk, and uptime.

gopsutil has a clever workaround — it reads env vars `HOST_PROC`,
`HOST_SYS`, `HOST_ETC` and uses them instead of the default
`/proc`, `/sys`, `/etc`. If you mount the host's `/proc` into the
container at `/host/proc` and set `HOST_PROC=/host/proc`, gopsutil
transparently reports the host's metrics.

That's what [docker-compose.yml](docker-compose.yml) does for the
`vps_stats` service:

```yaml
environment:
  HOST_PROC: /host/proc
  HOST_SYS: /host/sys
  HOST_ETC: /host/etc
volumes:
  - /proc:/host/proc:ro   # read-only — we only read metrics
  - /sys:/host/sys:ro
  - /etc:/host/etc:ro
  - /:/host/root:ro       # root FS for disk.Usage()
```

Linux-only. On Windows/Mac dev, the mounts won't work the same way — the
service still runs but reports container-level numbers. Normal.

### Concept 6 — `go.mod` + `go.sum`

Run `go mod tidy` once and two files appear:

- **`go.mod`** — your module's deps, like `package.json` or
  `requirements.txt`.
- **`go.sum`** — a cryptographic hash of every dep version, like
  `package-lock.json` or `requirements.txt` with pinned hashes. Commit
  this. `go build` verifies the downloaded deps match, preventing
  supply-chain attacks and non-reproducible builds.

Adding a dep is one command:

```bash
go get github.com/shirou/gopsutil/v4@latest
```

`go mod tidy` cleans up unused deps and adds any new imports you've
written. Run it before committing.

### 💡 Try it — run vps_stats and talk to it

Requires the full stack and a Linux Docker host (or WSL on Windows) for
host metrics. On Windows Docker Desktop this works, but reports slightly
different numbers.

```bash
# Build and start vps_stats alone (don't need everything else running)
docker compose up -d vps_stats

# Check the logs — you should see:
# "vps_stats listening on :8090 (disk path=/host/root, auth=false)"
docker compose logs vps_stats

# Hit the health endpoint
curl http://localhost:8090/health
# → ok

# Hit stats
curl http://localhost:8090/stats | python -m json.tool
```

Now flip on auth:

```bash
# Set in .env
VPS_STATS_TOKEN=supersecret-change-me

docker compose up -d vps_stats   # picks up the new env

# Without token:
curl http://localhost:8090/stats
# → unauthorized

# With token:
curl -H "Authorization: Bearer supersecret-change-me" http://localhost:8090/stats | python -m json.tool
```

Go run locally (no Docker) to iterate fast while developing:

```bash
cd services/vps_stats
go run .
# Ctrl-C to stop
# Reports your laptop's stats directly — no HOST_PROC mounts needed.
```

### Sandbox resources — Go HTTP + systems

| Link | What it's for |
|---|---|
| https://pkg.go.dev/net/http | **net/http docs** — the actual reference. Bookmark. |
| https://pkg.go.dev/github.com/shirou/gopsutil/v4 | gopsutil docs — every subpackage (cpu, mem, disk, etc.) |
| https://go.dev/blog/context | Official context package guide — crucial for servers |
| https://gobyexample.com/http-servers | Minimal HTTP server example, annotated |
| https://gobyexample.com/http-clients | Complement: HTTP client basics |
| https://github.com/mattermost/awesome-go | Curated Go library list when you want to skip stdlib |
| https://pkg.go.dev/ | **Every Go package is documented here.** Go's killer feature. |

### 🏋️ Homework 5.1 — Add a `/processes` endpoint

Goal: add one more endpoint end to end.

Expose `GET /processes?top=10` returning the top N processes by CPU or
memory usage.

Hints:
- [gopsutil/process](https://pkg.go.dev/github.com/shirou/gopsutil/v4/process)
  has `Processes()` which lists all, and each process has `CPUPercent()`
  / `MemoryPercent()` methods.
- Parse `top` from `r.URL.Query().Get("top")`. Default to 10. Use
  `strconv.Atoi`.
- Sort the slice with `sort.Slice(procs, func(i, j int) bool { ... })`.
- Return a JSON array of `{pid, name, cpu_percent, mem_percent}`.

Add it behind `withAuth` too.

### 🏋️ Homework 5.2 — Add a Prometheus metrics endpoint

Goal: real-world Go pattern — every microservice exposes `/metrics`.

1. Add `github.com/prometheus/client_golang` to go.mod (`go get …`).
2. Create counters/gauges for: request count per endpoint, response
   duration, current CPU percent, current mem percent.
3. Expose `GET /metrics` returning the Prometheus text format.
4. Update stats collector to refresh the gauges every 30 seconds in a
   background goroutine.

This is your introduction to **goroutines** + **ticker**:

```go
go func() {
    ticker := time.NewTicker(30 * time.Second)
    defer ticker.Stop()
    for range ticker.C {
        // update gauges
    }
}()
```

The `go` keyword spawns a goroutine — a lightweight thread managed by the
Go runtime. You can run millions. We haven't needed one until now.

### 🏋️ Homework 5.3 — Unit test `roundTo`

Goal: your first Go test.

Create `services/vps_stats/stats_test.go`:

```go
package main

import "testing"

func TestRoundTo(t *testing.T) {
    cases := []struct {
        name     string
        input    float64
        places   int
        expected float64
    }{
        {"zero", 0, 2, 0},
        {"round-down", 1.234, 2, 1.23},
        {"round-up", 1.235, 2, 1.24},
        {"integer", 5.0, 0, 5.0},
        {"negative", -3.14159, 3, -3.142},
    }
    for _, tc := range cases {
        t.Run(tc.name, func(t *testing.T) {
            got := roundTo(tc.input, tc.places)
            if got != tc.expected {
                t.Errorf("roundTo(%v, %d) = %v, want %v", tc.input, tc.places, got, tc.expected)
            }
        })
    }
}
```

Run: `go test ./...`

This is Go's test style — **table-driven tests** with subtests. No
assertion library needed; plain `if`/`t.Errorf`. The entire Go test
ecosystem works this way. Most Go projects don't use testify or similar.

### Gotchas I almost hit

- **`http.ListenAndServe` blocks forever.** It only returns on error. Put
  it last in `main()`.
- **`defer ticker.Stop()` is not optional.** Forgetting it leaks a
  goroutine on exit. Go tools like `go vet` will warn you.
- **Not setting `ReadHeaderTimeout`** leaves you open to slowloris
  attacks. Every production HTTP server should set it. We did.
- **Windows + gopsutil quirks.** `load.Avg()` doesn't exist on Windows and
  returns an error — we handle this by letting the subsystem silently
  omit its fields. Check your `/stats` output and see which fields are 0
  on your platform.

### What's next (section 6 preview)

Section 6: **wire vps_stats into the Telegram bot**. Add a handler so
`/stats` or `/vps` in Telegram calls `GET http://vps_stats:8090/stats`
(internal Docker network), formats the result, and sends it back. First
real cross-service integration in your monolith + microservices hybrid.
Small code change, but it's the moment the architecture earns its keep.

---

## 6. Telegram → `vps_stats` — first cross-service call

### What we built

Three new Telegram commands that fetch from the Go `vps_stats` service
over the internal Docker network:

- `/stats` — CPU / RAM / disk / uptime summary
- `/processes` (optional: `mem`, or a number like `20`) — top processes
- `/disks` — mounted filesystems

Files:
- [app/services/vps_stats_service.py](app/services/vps_stats_service.py) —
  Python client that talks to Go
- [app/bot/handlers.py](app/bot/handlers.py) — three new
  `..._command` handlers and registrations
- [app/core/config.py](app/core/config.py) — `VPS_STATS_INTERNAL_URL` +
  `VPS_STATS_TOKEN` settings
- [.env.example](.env.example) — env vars documented

### Concept 1 — Service-to-service calls inside the Docker network

In [docker-compose.yml](docker-compose.yml) each service's **name** is
its DNS hostname inside the Docker network. The bot runs in the `bot`
container; `vps_stats` runs in the `vps_stats` container; the bot can
reach it at `http://vps_stats:8090` — no port publishing needed, no
`host.docker.internal`, nothing else.

Ports are published to the **host** only when you want outside access.
`vps_stats` has `"127.0.0.1:8090:8090"` so you can `curl` it from your
laptop for debugging, but from the bot's perspective it's just another
container.

**Why this matters:** your monolith and microservices coexist in the
same compose network. Calling a microservice from the monolith is a
localhost HTTP call. No service mesh, no discovery layer, no complexity.

### Concept 2 — The thin-client pattern

Every external integration gets a small wrapper like
[vps_stats_service.py](app/services/vps_stats_service.py). Two reasons:

1. **Single place to change.** If we later move `vps_stats` behind
   Kubernetes DNS, or swap to gRPC, only this file changes. Handlers
   stay clean.
2. **Domain-specific errors.** `VpsStatsUnavailable` lets handlers write
   `except VpsStatsUnavailable:` instead of catching every possible
   `httpx` exception. Your error handling matches the conceptual
   failure mode, not the transport mode.

This is the same discipline as the contracts rule in section 2 — a
module only talks to another module through a narrow, explicit surface.

### Concept 3 — `asyncio.to_thread` for sync calls in an async framework

python-telegram-bot handlers are async (`async def`). But
`httpx.get(...)` is synchronous — it blocks the thread. If we just
called it directly, the entire bot's event loop would freeze during
the HTTP round trip.

`await asyncio.to_thread(VpsStatsService.fetch)` pushes the sync call
onto a thread pool. The event loop keeps servicing other updates while
that thread waits for the HTTP response. Once it returns, the coroutine
resumes.

You'll see this pattern everywhere in the codebase — every
`process_message_sync`, `deliver_processed_message`, etc. goes through
`to_thread`.

Alternative: `httpx.AsyncClient` with `await`. Faster, more idiomatic,
but would mean propagating async up the service layer. We chose
`to_thread` to match the existing service style.

### 💡 Try it

Once the stack is up:

```bash
# Send /stats in Telegram → you should see a formatted summary.
# Try /processes mem 5 → top 5 by memory.
# Try /disks → filesystem list.
```

Tail the bot logs while you do this:

```bash
docker compose logs -f bot
```

If `vps_stats` is down or auth is wrong, the bot replies with a clear
error from `VpsStatsUnavailable` rather than crashing.

### 🏋️ Homework 6.1 — Cache the response

Repeated `/stats` hits every 5 seconds trigger a fresh gopsutil
collection. Wasteful.

Add a 5-second in-memory cache in `VpsStatsService.fetch`. Use
`functools.lru_cache`? No — `lru_cache` doesn't expire on time.
Instead:

```python
import time
_cache: tuple[float, dict] | None = None

@staticmethod
def fetch() -> dict:
    global _cache
    now = time.time()
    if _cache and (now - _cache[0]) < 5.0:
        return _cache[1]
    # ... do the HTTP call ...
    _cache = (now, result)
    return result
```

Concept: TTL caches. Good first intuition for Redis-backed caching.

### 🏋️ Homework 6.2 — Natural-language fallback

Currently `/stats` is a slash command. Add recognition in
[text_message](app/bot/handlers.py) so "what's my RAM?" or "vps
status" trigger the same handler. Look at how the existing natural-
language layer routes other commands.

### Gotchas

- **Service name with underscore vs dash.** Docker compose accepts
  both. In DNS `vps_stats` resolves inside the compose network fine.
  For k8s you'll need `vps-stats` (no underscores allowed in DNS-1123
  names). That's why our k8s manifests use `vps-stats`.
- **Timeouts.** `httpx.get(url, timeout=5.0)` — always set it.
  Without, a hanging server hangs the bot.
- **Token mismatch.** If `VPS_STATS_TOKEN` differs between the
  `vps_stats` and `bot`/`api` services, you get 401s. Set it once in
  `.env`; compose loads the same file for all services.

---

## 7. Read-only VPS action endpoints + safe write-action design

### What we built

Two additional endpoints on the Go service:

- `GET /processes?top=N&by=cpu|mem` — per-process CPU%, memory%, RSS
- `GET /disks` — all mounted filesystems with usage

Plus the Telegram commands from section 6 that call them.

Files touched:
- [services/vps_stats/actions.go](services/vps_stats/actions.go) — **new**
- [services/vps_stats/main.go](services/vps_stats/main.go) — routes
  registered
- Python side reuses the same service client with new helper methods

### Concept 1 — "Actions" vs "metrics"

Metrics are read-only: `/stats`, `/disks`, `/processes`. Calling them
produces no side effects; you can spam them without risk.

Actions mutate state: `restart-service`, `reboot`, `delete-file`,
`docker-kill`. They need a fundamentally different safety model.

**This session delivers metrics only.** The write-action design is
documented below but not implemented, because rushed mutate-the-VPS
code is exactly how people self-pwn.

### Concept 2 — Why we didn't implement `/actions/restart-minecraft` today

To restart a systemd service from inside a container you need one of:

1. **Docker-socket-mount + privileged container.** The container can
   talk to the host Docker daemon and restart other containers. Grants
   **root on the host** to anyone who compromises the container.
2. **DBus/systemd mount + privileged + CAP_SYS_ADMIN.** Can call
   `systemctl` directly. Grants root-equivalent.
3. **Host agent pattern.** A tiny binary runs on the host (not in
   Docker), listens on a Unix socket, accepts signed requests from an
   allowlist, executes them. No container privileges needed.

Option 3 is the right answer. It's also a whole separate project —
think of it as `vps_agent` alongside `vps_stats`. It needs:

- Systemd unit file that runs as root.
- Cryptographic request signing (HMAC) so the Docker side can't
  accidentally/maliciously run arbitrary commands.
- A static YAML allowlist of permitted commands with template
  parameters and argument-validation regex.
- An audit log persisted outside the agent's write path.

That's a full LEARN.md section on its own. We'll build it when you
actually want a Telegram "restart-minecraft" command — not today.

### Concept 3 — Allowlist design for the future action registry

When we build it, the config will look roughly like:

```yaml
# /etc/vps_agent/actions.yml — owned by root, 0600
actions:
  restart-minecraft:
    command: ["/bin/systemctl", "restart", "minecraft"]
    description: "Restart the Minecraft systemd service"
    require_confirmation: true

  du-path:
    command: ["/usr/bin/du", "-sh", "{path}"]
    description: "Show disk usage for a directory"
    args:
      path:
        pattern: "^/(home|var|srv)/[A-Za-z0-9_\\-./]+$"
    require_confirmation: false
```

Three discipline points:

1. **Commands are arrays**, never shell strings. No `sh -c "..."` →
   no shell injection.
2. **Arg validation is regex**, and every arg is substituted by
   string replacement only. Never `eval`, never `format` with
   untrusted input elsewhere.
3. **`require_confirmation: true`** causes the Telegram bot to show
   an inline keyboard "Yes / No" before executing. Mutating actions
   default to true.

### Concept 4 — Process listing is a realistic exercise in failure modes

[`collectProcesses`](services/vps_stats/actions.go) iterates every
PID and queries each. Per-process fields can fail for many reasons:

- Process exited between enumeration and detail fetch (race).
- Kernel refused the read (permissions, namespace).
- Process name contains weird bytes.

We handle each field-fetch in its own `if err == nil { ... }` block
— a single failed field doesn't drop the row, a single failed row
doesn't fail the response. This pattern is correct for any
"enumerate-then-detail" call.

**Counter-example to avoid:** using `errgroup.Wait()` across all
fields, which fails the whole request if any single goroutine
errors. Wrong semantic — you'd get 500s all day.

### 💡 Try it

```bash
# Directly
curl http://localhost:8090/processes?top=5 | python -m json.tool
curl http://localhost:8090/processes?top=5&by=mem | python -m json.tool
curl http://localhost:8090/disks | python -m json.tool

# From Telegram
/processes
/processes mem
/processes 20
/disks
```

### 🏋️ Homework 7.1 — Add `/netstats`

Goal: write another read-only endpoint.

Add `GET /netstats` in
[services/vps_stats/actions.go](services/vps_stats/actions.go) using
[`gopsutil/net`](https://pkg.go.dev/github.com/shirou/gopsutil/v4/net).
Return per-interface bytes sent/received + packet counts. Then add a
Telegram `/net` command.

This exercises: a new Go endpoint + a new Python client method + a new
bot handler. Full vertical slice, ~1 hour.

### 🏋️ Homework 7.2 — Prototype the action registry (design only)

Write a markdown doc at `deploy/vps_agent/DESIGN.md` that sketches:

1. What commands would live in the allowlist for *your* VPS (list 5–8).
2. What arg validation each needs.
3. Which are "read-only-safe" (no confirm) vs "mutating" (confirm).
4. How the Telegram confirmation flow works from the user's POV.
5. Rough API surface — one paragraph each for
   `GET /actions`, `POST /actions/{name}`, `GET /audit`.

This is a design-doc exercise, no code. Good practice — real projects
start here.

### Gotchas

- **Process enumeration is slow** on busy hosts. We cap `top` at 200.
  Always cap when an endpoint's cost scales with system state.
- **Disk partitions include /boot, /snap/*, etc.** on Linux hosts. If
  you want to hide those, filter by `Fstype` or `Mountpoint` prefix.

---

## 8. Kubernetes on k3d — porting `vps_stats` to manifests

### What we built

A complete set of k8s manifests that run `vps_stats` as a **DaemonSet**
on a local k3d cluster. Everything lives in
[deploy/k8s/](deploy/k8s/):

- `namespace.yaml` — the `aiops` namespace
- `vps-stats-configmap.yaml` — non-secret env (disk path, addr)
- `vps-stats-secret.yaml.example` — template (real Secret created via
  `kubectl create secret`, never in git)
- `vps-stats-daemonset.yaml` — one pod per node, host mounts
- `vps-stats-service.yaml` — ClusterIP on port 8090
- `kustomization.yaml` — ties it together for `kubectl apply -k .`
- `README.md` — step-by-step runbook

### Concept 1 — k8s vocab in 2 minutes

| Thing | What it is | Analogy |
|---|---|---|
| **Pod** | Smallest unit — 1+ containers sharing network | Docker container |
| **Deployment** | "I want N pods, replace as needed" | docker compose service with `replicas:` |
| **DaemonSet** | "I want exactly one pod per node" | — no docker-compose equivalent |
| **Service** | Stable DNS + virtual IP in front of pods | Docker network alias |
| **ConfigMap** | Non-secret env as a k8s resource | `.env` file |
| **Secret** | Encoded secret as a k8s resource | `.env` file with gitignore |
| **Namespace** | Folder to group resources + scope RBAC | folder |
| **Ingress** | External HTTP(s) entry point | reverse proxy |
| **PersistentVolume** + **Claim** | Mounted disk for a pod | named volume |

That's 95% of what you'll use.

### Concept 2 — Why DaemonSet, not Deployment

Deployment: "I want 3 replicas of this pod, place them anywhere in the
cluster." Good for API servers, background workers. Placement is up to
the scheduler.

DaemonSet: "I want exactly one pod **per node**." Good for node-level
services — metrics, log shippers, network agents. Each pod sees its
own node's `/proc`, `/sys`, `/`.

`vps_stats` is genuinely node-level: it reports that node's CPU, not
"some node somewhere." DaemonSet is the right choice. Add a second
node (`k3d node add`) and you automatically get a second pod. Zero
manifest change.

The industry-standard "node_exporter" for Prometheus uses the same
pattern for the same reason.

### Concept 3 — The Deployment→Service→Ingress chain

External traffic hits k8s via an Ingress. Ingress routes to a Service.
Service load-balances across matching Pods.

```
[Client] → Ingress (HTTPS) → Service (ClusterIP) → Pod(s)
```

We didn't configure an Ingress for `vps_stats` because it's internal
— only other pods need it. For externally-exposed services (your
future API), you'd add an Ingress on top:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: api
spec:
  rules:
    - host: api.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: api
                port:
                  number: 8000
```

### Concept 4 — Kustomize vs Helm

Two ways to bundle k8s manifests:

- **Kustomize** — built into `kubectl`. Patches over a base — good for
  simple overlays (dev/staging/prod). No templating. We use this.
- **Helm** — separate tool. Go-template-based values + charts. Better
  for published reusable packages (e.g. installing Postgres via a
  maintained chart).

Start with Kustomize. Graduate to Helm when you want to share manifests
across projects or consume third-party charts.

### Concept 5 — `imagePullPolicy: IfNotPresent` + local images

In production, k8s pulls images from a registry. In local dev with
k3d, your Docker images aren't in any registry.

`k3d image import` copies a locally-built Docker image into the k3d
cluster's container runtime. After import, pods can use `image:
vps_stats:local` without ever hitting a registry. `imagePullPolicy:
IfNotPresent` says "don't try to pull if the image is already here."

For production, you'd push to a registry (Docker Hub, GHCR, ECR) and
remove the `:local` tag in favor of `:v1.2.3`. Same manifests.

### 💡 Try it — stand up k3d and deploy

Full runbook in [deploy/k8s/README.md](deploy/k8s/README.md). Quick
version:

```bash
# Install k3d + kubectl (Homebrew, choco, apt, your choice)

# Create a cluster (30 sec)
k3d cluster create aiops-lab

# Build and import the image
cd services/vps_stats
docker build -t vps_stats:local .
k3d image import vps_stats:local -c aiops-lab

# Create namespace + secret
kubectl create ns aiops --dry-run=client -o yaml | kubectl apply -f -
kubectl -n aiops create secret generic vps-stats-secret \
  --from-literal=VPS_STATS_TOKEN="$(openssl rand -hex 32)"

# Apply everything
cd ../../deploy/k8s
kubectl apply -k .

# Watch the rollout
kubectl -n aiops get pods -w

# Smoke test
kubectl -n aiops port-forward svc/vps-stats 8091:8090 &
TOKEN=$(kubectl -n aiops get secret vps-stats-secret -o jsonpath='{.data.VPS_STATS_TOKEN}' | base64 -d)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8091/stats
```

### Sandbox resources

| Link | What it's for |
|---|---|
| https://k3d.io/ | k3d — local k8s in Docker, what we use |
| https://kubernetes.io/docs/tutorials/ | Official tutorials, genuinely good |
| https://www.katacoda.com/ (shut down) / **https://killercoda.com/** | In-browser k8s scenarios |
| https://learnk8s.io/ | Long-form articles, paid courses |
| https://labs.play-with-k8s.com/ | Free in-browser 4-hour lab cluster |
| https://kubernetes.io/docs/reference/kubectl/cheatsheet/ | kubectl cheat sheet — bookmark it |

### 🏋️ Homework 8.1 — Break the DaemonSet on purpose

Do all of these, watch the behavior:

1. `kubectl -n aiops delete pod <vps-stats-xxxx>` — should be replaced
   in ~5 seconds.
2. Edit the DaemonSet and set memory limit to `4Mi` (tiny). Apply.
   Watch pods OOMKill in a loop — `kubectl -n aiops get pods` shows
   `CrashLoopBackOff`.
3. `kubectl -n aiops describe pod <name>` — find the OOM events. This
   is how you diagnose prod issues.
4. Fix the limit back to `128Mi`. Watch pods stabilize.

You just learned: resource limits + crash loops + describe pod — 60%
of real k8s debugging.

### 🏋️ Homework 8.2 — Add a second node

```bash
k3d node add new-agent --role agent --cluster aiops-lab
kubectl get nodes             # should show 2 nodes
kubectl -n aiops get pods     # should show 2 vps-stats pods
```

Confirm each pod reports its own node's metrics (you may need to
port-forward to a specific pod, not the Service — the Service
load-balances).

### 🏋️ Homework 8.3 — Write a Deployment manifest from scratch

Goal: build the full shape of a typical web-app deployment.

Create `deploy/k8s/example-api.yaml` with:

1. A `Deployment` for a dummy nginx image, 2 replicas.
2. A `Service` (ClusterIP).
3. Liveness + readiness probes hitting `/`.
4. Resource requests + limits.
5. Environment variable from a new ConfigMap.
6. Apply with `kubectl apply -f example-api.yaml`.
7. Delete with `kubectl delete -f example-api.yaml`.

You'll do this pattern for every real service you ever deploy.

### Gotchas

- **DNS-1123 names.** Pod/Service/ConfigMap names must be lowercase
  alphanumeric with `-`. No underscores (hence `vps-stats`, not
  `vps_stats`). k8s will reject the manifest otherwise.
- **`kubectl apply -k` needs kustomization.yaml.** The `-k` flag means
  kustomize mode. `kubectl apply -f .` without `-k` silently does
  nothing useful in a directory with a kustomization file.
- **Secrets in git.** Never. `.gitignore` catches
  `deploy/k8s/*secret.yaml` but not `*secret.*.yaml` — double-check
  before committing.
- **DaemonSet doesn't scale horizontally.** Replica count = node
  count. If you want 2 per node, use a StatefulSet with affinity, or
  two DaemonSets. (You won't need this.)

---

## 9. ML service scaffold — TensorFlow/OpenCV placeholder

### What we built

A minimal Python microservice at [services/ml/](services/ml/) that:

- Exposes `/health`, `/models`, `/infer`, `/embeddings` endpoints.
- Returns stub/echo responses for now.
- Has a Dockerfile prepared for TensorFlow/OpenCV/torch (commented
  out — uncomment when you need them).
- Is wired into docker-compose behind the `ml` profile, so it doesn't
  start by default.

**Nothing about it does real ML yet.** This is the skeleton. Real
model code goes into `services/ml/models/` when you write it.

### Concept 1 — Why scaffolding first, ML code second

Half the time spent on ML projects is infrastructure: HTTP
boundaries, request shapes, deployment, secrets, scaling. If you
start with TensorFlow code inside your main API, you'll eventually
do this split anyway, under production pressure.

Doing the split *first* — with a dummy endpoint — costs nothing and
locks in the right shape. You add the model, not the service.

### Concept 2 — Docker compose profiles

```yaml
ml:
  profiles: ["ml"]
  ...
```

Services with a `profiles:` field only start when you pass
`--profile <name>`. So:

```bash
docker compose up -d              # core stack, ml NOT started
docker compose --profile ml up -d # core stack + ml
docker compose --profile ml up -d ml   # ml alone
```

Use profiles for: optional services (heavy ML, monitoring, dev
tools), environment variants (e.g. `profiles: ["prod"]`), or
services you sometimes want to test in isolation.

### Concept 3 — The "dependency laziness" pattern

[requirements.txt](services/ml/requirements.txt) has TensorFlow,
OpenCV, torch commented out:

```
# tensorflow>=2.18,<3.0
# opencv-python-headless>=4.10,<5.0
# torch>=2.4,<3.0
```

Uncommented, the Docker image jumps from ~200 MB to ~3 GB. By leaving
them out until you need them, your `docker compose build ml` is fast,
and you're forced to consciously opt in to each huge dependency.

Same principle applies in Python generally: **don't install what you
don't use**. Every dep is a liability.

### Concept 4 — Why a synchronous FastAPI for ML

Most ML inference is compute-bound, not I/O-bound. Making endpoints
`async def` buys you nothing — TensorFlow's `.predict()` blocks the
event loop regardless. Worse, using async here gives junior
contributors the wrong intuition about when async helps.

Keep ML endpoints `def` (sync). FastAPI runs each sync request in a
thread-pool worker by default. Per-request isolation, no cross-request
contention from the GIL except inside the model itself, which is
usually released inside NumPy/TF native code.

This matches the ML-serving conventions (Triton, TorchServe, BentoML)
— sync handlers, rely on worker processes for concurrency.

### Concept 5 — Model weights are not code

Storing `.pt` / `.safetensors` / `.bin` files in git is a common
beginner mistake. They're:

- Huge (100 MB – 10 GB).
- Changed frequently during training.
- Binary, un-diffable.
- Make `git clone` miserable.

Instead:

- **Mount a volume** at startup (`-v /srv/ml-models:/app/models:ro`).
- **Pull from object storage** at container startup (S3, R2, MinIO,
  Hugging Face Hub).
- **Use Git LFS only as a last resort** — it's a partial workaround.

Our [.dockerignore](services/ml/.dockerignore) excludes `models/*`
for this reason.

### 💡 Try it

```bash
# Start ml alongside the core stack
docker compose --profile ml up -d ml

# Health
curl http://localhost:9000/health

# Loaded models (empty until you add one)
curl http://localhost:9000/models

# Echo inference (the only "model" that exists)
curl -X POST http://localhost:9000/infer \
  -H "Content-Type: application/json" \
  -d '{"model": "echo", "inputs": [1, 2, 3]}'

# Fake embeddings
curl -X POST http://localhost:9000/embeddings \
  -H "Content-Type: application/json" \
  -d '{"texts": ["hello", "world"]}'

# Tear down ml alone
docker compose stop ml
```

### Sandbox resources

| Link | What it's for |
|---|---|
| https://www.tensorflow.org/tutorials/quickstart/beginner | TF quickstart — MNIST in 10 minutes |
| https://pytorch.org/tutorials/beginner/basics/intro.html | PyTorch fundamentals |
| https://huggingface.co/learn | NLP + CV modern stack, free, excellent |
| https://opencv.org/ | OpenCV, for image processing specifically |
| https://fastapi.tiangolo.com/deployment/ | FastAPI deployment — the ML-serving story |
| https://min.io/docs/minio/container/ | Self-hosted S3 for model storage |

### 🏋️ Homework 9.1 — Wire a real embedding model

Goal: replace the stub `/embeddings` with a real model.

1. `pip install sentence-transformers` (uncomment in requirements.txt).
2. In `services/ml/models/embeddings.py`, load
   `sentence-transformers/all-MiniLM-L6-v2` at module import.
3. Update `/embeddings` in `main.py` to call it.
4. Test:
   ```bash
   curl -X POST http://localhost:9000/embeddings \
     -H "Content-Type: application/json" \
     -d '{"texts": ["a dog", "a puppy", "the stock market"]}'
   ```
   The first two embeddings should be more similar to each other than
   either is to the third. Verify with cosine similarity.

You just built a real embeddings microservice. Bonus: wire this into
MemoryCore v2 so design-library search uses semantic similarity (via
pgvector, which you'll add later) instead of SQL LIKE.

### 🏋️ Homework 9.2 — Image-classify from Telegram

Goal: end-to-end ML from user input.

1. Add a TF/torch image-classification model (e.g. MobileNetV3).
2. New endpoint `POST /classify` accepting a URL or base64 image,
   returning top-5 labels.
3. Telegram: wire the existing `media_message` handler so sending a
   photo with caption "classify this" calls `/classify` and replies
   with the top labels.

This is a real multi-layer project: Go microservice + Python client
wrapper + Telegram handler + ML. ~4 hours of focused work.

### Gotchas

- **First startup is slow.** TensorFlow alone takes 5–15 sec to
  import. Bump the Docker healthcheck `start_period` if you
  uncomment heavy deps.
- **`libGL.so.1 not found` errors with OpenCV.** The Dockerfile has
  the `apt install libgl1 libglib2.0-0` line commented out. Uncomment
  when you uncomment `opencv-python-headless`.
- **Don't return NumPy arrays directly from FastAPI.** Convert to
  lists or use `orjson.dumps(...)` — default json can't handle
  ndarrays.

---

## 10. Observability — Prometheus + Grafana across the stack

### What we built

A full metrics stack that reads from both the Go microservice and the
Python monolith, all behind a `docker compose --profile observability`
flag so it only runs when you want it.

Files:
- [services/vps_stats/metrics.go](services/vps_stats/metrics.go) — Go
  Prometheus counters + histograms + gauges, middleware, `/metrics` endpoint
- [services/vps_stats/main.go](services/vps_stats/main.go) — routes wrapped
  with `withMetrics`, `/metrics` exposed unauthenticated (scraper needs it)
- [app/main.py](app/main.py) — `Instrumentator().instrument(app).expose(app)`
  adds Python-side metrics in one line
- [deploy/observability/prometheus.yml](deploy/observability/prometheus.yml) —
  scrape config targeting `vps_stats:8090/metrics` + `api:8000/metrics`
- [deploy/observability/grafana/provisioning/](deploy/observability/grafana/provisioning/)
  — auto-wires Prometheus as the default datasource
- [docker-compose.yml](docker-compose.yml) — new `prometheus` + `grafana`
  services behind the `observability` profile

### Concept 1 — The three pillars of observability

| Pillar | What it answers | Tool |
|---|---|---|
| **Metrics** | "How many? How fast? How much?" — numbers over time | Prometheus |
| **Logs** | "What happened?" — discrete text events | Loki / ELK |
| **Traces** | "Where did this slow request spend its time?" — distributed call graphs | Jaeger / Tempo |

We're adding metrics only today. Logs already exist in your Docker output.
Tracing is overkill until you have real latency mysteries to solve.

### Concept 2 — Prometheus is a pull-based scrape loop

Most monitoring systems are push: your app sends metrics to a collector.
Prometheus inverts this. It **pulls** — it hits each configured target's
`/metrics` endpoint every 15 seconds and stores what it finds.

Why pull wins:
- Your app doesn't need a "where's the collector?" config.
- A dead target is obviously visible (scrape fails).
- You can query any app by hand:
  `curl http://vps_stats:8090/metrics` — same format Prometheus sees.

Why pull has limits: it's bad at short-lived jobs (they die before
being scraped). For those, Prometheus has a Pushgateway. We don't need one.

### Concept 3 — The four metric types

```
# TYPE vps_stats_requests_total counter
vps_stats_requests_total{path="/stats",status="200"} 42

# TYPE vps_stats_request_duration_seconds histogram
vps_stats_request_duration_seconds_bucket{path="/stats",le="0.005"} 40
vps_stats_request_duration_seconds_bucket{path="/stats",le="0.01"} 41
vps_stats_request_duration_seconds_bucket{path="/stats",le="+Inf"} 42
vps_stats_request_duration_seconds_sum{path="/stats"} 0.14
vps_stats_request_duration_seconds_count{path="/stats"} 42

# TYPE vps_stats_host_cpu_percent gauge
vps_stats_host_cpu_percent 4.2
```

- **Counter** — monotonically increasing integer. "Total requests served." Use `rate()` in PromQL to turn it into req/sec.
- **Gauge** — arbitrary value that goes up and down. "Current memory usage." Use directly or `avg_over_time()` / `max_over_time()`.
- **Histogram** — pre-bucketed distribution for latency. Use `histogram_quantile(0.95, …)` to get p95.
- **Summary** — like histogram but client-side quantiles. Rare; prefer histograms.

You'll live in counters and histograms 90% of the time.

### Concept 4 — Labels are cardinality landmines

```go
reqCounter.WithLabelValues(path, strconv.Itoa(sr.status)).Inc()
```

Every unique combination of label values creates a new time series. Two
labels (`path`, `status`) with 10 paths × 8 statuses = 80 series. Fine.

**Anti-pattern:** adding `user_id` as a label. With 10k users that's 10k
× 80 = 800k series from one counter. Your Prometheus instance crawls to
its knees.

Rule: labels are for **low-cardinality, bounded** dimensions (status,
endpoint, environment, region). User IDs, request IDs, and free-text
go in logs, not metric labels.

### Concept 5 — Reusing collection work with gauges

`/stats` already collects CPU/memory/disk as JSON. Rather than duplicate
that work in a separate ticker goroutine just for Prometheus, we call
`updateHostGauges(s)` inside `handleStats` — same gopsutil data feeds
both the JSON endpoint and the metrics gauges.

Downside: if no one hits `/stats` for a while, the gauges go stale.
Prometheus will scrape `/metrics` every 15s and see the last observed
values — usually fine because Grafana/Telegram also polls `/stats`
regularly. If you really need background refresh, add a ticker
goroutine (see §5 homework 5.2).

### 💡 Try it

```bash
# Start the observability stack alongside the rest
docker compose --profile observability up -d

# Prometheus UI
#   http://localhost:9090
# Try these queries in the "Graph" tab:
rate(vps_stats_requests_total[1m])
histogram_quantile(0.95, sum(rate(vps_stats_request_duration_seconds_bucket[5m])) by (le, path))
vps_stats_host_cpu_percent

# Grafana UI
#   http://localhost:3000
# Login: admin / admin (change in .env via GRAFANA_ADMIN_PASSWORD)
# The Prometheus datasource is already wired — go to Explore and run the
# same queries above.
```

To build a dashboard:
1. In Grafana → **Dashboards → New → New dashboard**.
2. Add a panel, set **Data source = Prometheus**.
3. Paste a PromQL query.
4. Save the dashboard.
5. To persist it as code, **Share → Export → Save to file** and drop
   the JSON into
   [deploy/observability/grafana/dashboards/](deploy/observability/grafana/dashboards/).
   Next restart, Grafana auto-loads it.

### 🏋️ Homework 10.1 — Make a dashboard for the hybrid stack

One panel each:

1. **Requests per second** — `rate(vps_stats_requests_total[1m])`, broken down by `path`.
2. **p95 latency** — use `histogram_quantile` over vps_stats_request_duration_seconds.
3. **Host CPU / Memory / Disk %** — three separate gauges, green/yellow/red thresholds.
4. **Python API request rate** — FastAPI instrumentator emits
   `http_requests_total`; filter by `handler` label.

Save as JSON in the dashboards folder. Commit it — now your monitoring
is version-controlled.

### 🏋️ Homework 10.2 — Alerting (stretch)

Create `deploy/observability/alerts.yml` with rules like:

```yaml
groups:
  - name: basics
    rules:
      - alert: HostDiskHigh
        expr: vps_stats_host_disk_percent > 85
        for: 10m
        labels: { severity: warning }
        annotations: { summary: "disk > 85% for 10m" }
```

Mount it into Prometheus via the compose config and restart.
Integrate alerting with Alertmanager → Telegram for a real
end-to-end alerting pipeline. (Big-ish exercise, ~2 hours.)

### Gotchas

- **`/metrics` endpoint is unauthenticated.** That's the Prometheus
  convention — scrape target must be scrapeable. Lock it down at the
  network layer (bind to 127.0.0.1 or private network), not with auth.
- **Scraper-side vs server-side labels.** Labels like `instance` and
  `job` are attached by Prometheus itself during scrape; don't emit
  them from your app. Your app emits domain labels (path, status).
- **Changing a metric's label set is a breaking change.** Existing time
  series get orphaned, queries break. Pick labels thoughtfully up
  front.
- **Grafana admin password is `admin/admin` by default.** Change it via
  `GRAFANA_ADMIN_PASSWORD` in `.env` before exposing to any network
  beyond your laptop.

---

## 11. Bring-up report — bugs we hit and fixed

The first end-to-end `docker compose up` never comes up clean. That's
universal. Here's what broke during the real-deal run, what each symptom
actually meant, and the fix. **These are the bugs you'll meet again in
every future project** — all four are textbook.

### Final state (for reference)

- All 11 containers healthy: api, bot, worker, beat, flower, postgres,
  redis, ollama, vps_stats, whatsapp-bridge, n8n.
- 13 tables in `aiops` database, including `memory_usage` + `memory_design`.
- `alembic_version` contains `5dda5a254210` (the initial_schema revision).
- `POST /api/v1/memorycore/usage` → 200 with `cost_usd: 0.0405` (pricing
  math works).
- `PUT /api/v1/memorycore/designs/<name>` → 200, retrievable by tag.
- `curl http://localhost:8090/metrics` → Prometheus Go runtime metrics
  streaming.

### Bug 1: Dockerfile didn't pick up new Go source files

**Symptom:**
```
./main.go:91:13: undefined: runUsageCommand
./main.go:95:13: undefined: runDesignCommand
```

**Root cause:** The project's root
[Dockerfile](Dockerfile) has a multi-stage build that compiles
`memorycore_cli`. It only copied the old files explicitly:

```dockerfile
COPY memorycore_cli/go.mod ./
COPY memorycore_cli/main.go ./        # ← explicit single file
```

When we added `usage.go` and `design.go` to `memorycore_cli/`, they
weren't copied, so `main.go` referenced functions that didn't exist in
the build context.

**Fix:** one character change:

```dockerfile
COPY memorycore_cli/*.go ./
```

**Lesson — "explicit file copies are brittle."** Copy directories or
globs so new files in that folder come along automatically. The only
time to explicitly list files is when you're deliberately excluding
others (use `.dockerignore` for that instead).

### Bug 2: Alembic revision file landed inside the throwaway container

**Symptom:** Command ran without error, "Generating
/app/alembic/versions/…/initial_schema.py … done", but
`ls alembic/versions/` on the host was empty.

**Root cause:** [docker-compose.yml](docker-compose.yml) only bind-mounts
`./data:/data`. The rest of the app — including `alembic/versions/` — is
**copied into the image at build time**. A file created inside a
`--rm` container disappears when the container exits.

**Fix:** bind-mount the one directory we wanted to write to:

```bash
docker compose run --rm \
  -v "/c/.../alembic/versions:/app/alembic/versions" \
  api alembic revision --autogenerate -m "initial_schema"
```

**Lesson — "writes in `--rm` containers are ephemeral."** Any file you
want to keep either needs (a) a bind mount to the host, (b) a named
volume, or (c) a follow-up `docker cp` before the container is removed.

### Bug 3: Git-bash path mangling

**Symptom:** With the bind mount above, the command silently did
nothing relevant to the host filesystem. `docker compose run` with
`-v /app/...` produced a mount targeting
`C:/Program Files/Git/app/...` instead of `/app/...`.

**Root cause:** MSYS2 / git-bash on Windows "helpfully" rewrites any
path-looking argument. `/app/alembic/versions` looked like a Unix path
to it, so it prepended the git-bash install prefix.

**Fix:**

```bash
MSYS_NO_PATHCONV=1 docker compose run --rm -v "..." api alembic ...
```

Alternative: prefix paths with double-slash (`//app/...`) — same effect.

**Lesson — "check the layer between your shell and your tool."** When
an absolute path mysteriously gets prepended with something weird,
it's almost always MSYS on Windows or a shell alias. Verify the exact
command Docker actually received (`docker events`, or add `-v` to your
command) before blaming the tool.

### Bug 4: ENUM-types leaking across failed migration attempts

**Symptom:**
```
psycopg.errors.DuplicateObject: type "agentstatus" already exists
[SQL: CREATE TYPE agentstatus AS ENUM ('online', 'busy', 'offline')]
```

Yet the postgres volume had been freshly deleted with
`docker compose down -v`.

**Root cause:** Three things combined:

1. The compose `api` command is
   `sh -c "alembic upgrade head && uvicorn …"` — migrations run before
   the app starts.
2. `alembic upgrade head` inside the api container's **first boot**
   created the 7 PostgreSQL ENUM types but then hit something
   (a transient connection issue, a long delay, or — most likely —
   the Docker healthcheck tagged the container unhealthy mid-migration
   and forced a restart).
3. On restart, `alembic upgrade head` ran again. Alembic's transactional
   DDL usually rolls back a failed migration — but when the container
   is killed externally (by Docker), the transaction doesn't cleanly
   roll back. ENUM types persisted. Next attempt tried to re-create
   them → `DuplicateObject` error → container crashed → restart loop.

**Why the same migration worked when run manually:**
```bash
docker compose run --rm --entrypoint alembic api upgrade head
```
…with no healthcheck, no external termination, no restart loop. The
migration completed its transaction normally, ENUMs committed alongside
tables, all good.

**Fix for this run:** `docker compose down -v` (wipe volumes), then run
the migration in a throwaway container **first**, only then bring up
the full stack. On boot, `alembic upgrade head` sees the revision
already applied and is a no-op.

**Permanent fix (for the future):** split migration from app start.
Don't chain them in the compose `command`. Instead:

- Add a dedicated one-shot container: `docker compose run --rm api alembic upgrade head`
  — run this before `docker compose up -d` whenever schemas change.
- OR keep the chain but make migrations idempotent by prepending
  `DROP TYPE IF EXISTS agentstatus CASCADE;` (etc.) inside each ENUM's
  migration. Unpleasant.
- OR use `postgresql.ENUM(..., create_type=False)` in the generated
  migration and a single `CREATE TYPE IF NOT EXISTS` (Postgres 9.5+
  doesn't have IF NOT EXISTS for types — you'd need a DO block).

For this project I recommend the first option: **migrations are a
deploy step, not a startup step.** Run `alembic upgrade head` from CI
or a one-shot container, then start the app.

**Lesson — "don't couple migrations to app startup."** The restart
loop pattern is the problem. Every time the app restarts for any
reason, you try to re-run migrations. On flaky networks or failed
healthchecks, you get half-applied state. Decouple.

### What this run actually exercised

The run above walked through the full architecture we built:
- Docker multi-stage builds with Go + Python + heterogeneous deps.
- Alembic autogenerate against live Postgres.
- Compose volumes vs build-context copies.
- Docker healthcheck interaction with init commands.
- Shell path-translation quirks on Windows.
- Live smoke-testing an HTTP API end to end.

All four bugs are real-world bugs, not specific to this project. You
will meet every single one again. Remember the shapes, not the fixes.

---

## 12. Universal agent context + token auto-capture from any medium

### What we built

A tool-agnostic system so **any** AI coding agent — Claude Code, Codex,
Cursor, Aider, Gemini, or whatever comes next — can (a) bootstrap
project context from one canonical file instead of re-exploring the
tree, and (b) log its token usage to a single ledger the user queries
from anywhere.

Files:
- **[AGENTS.md](AGENTS.md)** — single source of truth for project
  context. ~220 lines. Read first by any agent.
- **[CLAUDE.md](CLAUDE.md)** — 20-line pointer to AGENTS.md plus
  Claude-specific notes. Claude Code auto-loads this filename.
- **[.claude/settings.json](.claude/settings.json)** — Stop hook
  registration.
- **[.claude/hooks/log-usage.py](.claude/hooks/log-usage.py)** — parses
  Claude Code transcript, sums usage, POSTs to ledger. Silent-fail.
- **[scripts/codex-with-usage.sh](scripts/codex-with-usage.sh)** —
  wrapper: run `scripts/codex-with-usage.sh <args>` instead of `codex
  <args>` and usage is logged automatically from `~/.codex/sessions/`.
- `/usage [today|week|month]` Telegram command — formatted spend
  readout from any chat client pointed at your bot.
- New helper in
  [app/services/vps_stats_service.py](app/services/vps_stats_service.py)
  — `UsageService` class wrapping the summary endpoint.

### Concept 1 — There is no single standard file name (yet)

Right now the coding-agent ecosystem is fragmented:

| Agent | Context file |
|---|---|
| Claude Code | `CLAUDE.md` (auto-loaded) |
| Codex CLI (OpenAI) | `AGENTS.md`, `codex.md` |
| Cursor | `.cursorrules` |
| Aider | `AIDER.md` |
| Gemini | no standard yet |
| Future agent | who knows |

**`AGENTS.md` is winning as a de-facto standard.** We treat it as
canonical. `CLAUDE.md` is a 3-line pointer to `AGENTS.md` so Claude
auto-loads don't diverge from everyone else's context.

Pattern to steal: one canonical context file, cheap pointer files for
each tool-specific convention. When a new agent emerges, add a pointer
and you're done.

### Concept 2 — What a good AGENTS.md contains

Tradeoff: too short, agents still explore; too long, you waste the
tokens you were trying to save. Our file has:

1. **Project snapshot** — 1 paragraph, plus owner + repo.
2. **Architecture tree** — directory names + 1-line purpose each.
3. **Stack table** — one row per layer.
4. **Conventions** — the non-negotiable discipline points. Numbered
   so agents can cite them.
5. **Key commands** — copy-pastable.
6. **Initialization prompt** — a block the user pastes verbatim to any
   agent on a fresh session to tell it "read this first, log tokens,
   follow conventions."
7. **Common tasks** — a "when user says X, do Y" table.
8. **User preferences** — how the user communicates.

Things we **don't** put in AGENTS.md:
- API surface details (the agent should read the actual code)
- Exhaustive file listings (the tree section is enough orientation)
- Tutorial content (that's LEARN.md)

### Concept 3 — The initialization prompt pattern

Inside [AGENTS.md](AGENTS.md) there's a labelled
"Initialization prompt for agents" section. It tells the agent:

1. Read AGENTS.md first.
2. Read LEARN.md only if relevant (don't read it all).
3. Don't redo setup steps that are already done.
4. Log your session's usage when done.
5. Follow the conventions in the file.
6. Summarize understanding + ask clarifying questions before making changes.

**Paste that block at the top of any new agent session.** Works with
Claude, GPT, Gemini — anything that can read markdown. Saves a
measurable amount of tokens on every first message because the agent
won't grep half the repo.

### Concept 4 — Hooks: server-push vs client-pull for token logging

Two ways to get usage into the ledger:

**Client-pull** — the agent POSTs on session end. Claude Code's Stop
hook is exactly this pattern. [log-usage.py](.claude/hooks/log-usage.py)
parses the transcript file at `$transcript_path`, sums every
`message.usage` field, POSTs once.

**Server-push** — no agent cooperation needed. If you own the server
that serves the model (e.g. your own Ollama instance, or a proxy in
front of Claude/OpenAI APIs), you log usage server-side on every
request. Cleaner, works for agents that can't run hooks.

We do client-pull today because Anthropic's API is the model serving
layer, not us. When you eventually route through your own proxy (e.g.
[LiteLLM](https://github.com/BerriAI/litellm) as a gateway for all
LLM traffic), you'd switch to server-push and delete the hooks.

### Concept 5 — Silent-fail hooks

The hook script has three error paths that **all** silently succeed
(exit 0):

1. stdin isn't JSON → exit 0, nothing to log.
2. Transcript path missing / unreadable → exit 0.
3. POST to server fails (server down, timeout, network error) → exit 0.

Why: if the hook returns non-zero, Claude Code surfaces an error to
the user. Telemetry failures should **never** interrupt their work.
Your observability is less important than their flow.

This is the right default for **any** telemetry code you write —
metrics, logging, tracing. The system being observed always takes
precedence over the observer.

### Concept 6 — Cost math in the hook

Notice: the hook doesn't compute cost. It sends raw token counts. The
server — [pricing.py](app/modules/memorycore/pricing.py) — converts to
USD.

Why: pricing changes frequently. If you computed cost client-side in
10 different agents, you'd have to update 10 places every time
Anthropic adjusts rates. Do math in one place — the server. Clients
send raw facts.

### 💡 Try it — end-to-end

Bring up stack if not already running:

```bash
docker compose up -d
```

**1. Post manually from any HTTP client** (simulates any agent):

```bash
curl -X POST "http://localhost:8000/api/v1/memorycore/usage?user_id=fitclaw" \
  -H "Content-Type: application/json" \
  -d '{"tool":"cursor","model":"claude-sonnet-4-6","session_id":"manual-test","input_tokens":2500,"output_tokens":400,"note":"from the LEARN.md try it block"}'
```

**2. Query via Telegram bot:** message your bot `/usage` (defaults to
today), or `/usage week`, `/usage month`.

**3. Query via Go CLI:**

```bash
./memorycore_cli usage today
```

**4. Query directly via curl:**

```bash
curl -s "http://localhost:8000/api/v1/memorycore/usage/summary?user_id=fitclaw&period=today" | python -m json.tool
```

**5. Verify Claude Code hook on next session.** Next time you finish a
Claude Code session, check `./memorycore_cli usage today` (or
`/usage`) — the session should appear automatically with the real
transcript's token counts.

### Sandbox resources

- **Claude Code hooks reference** — https://docs.anthropic.com/en/docs/claude-code/hooks
- **Codex CLI config** — https://github.com/openai/codex#configuration
- **LiteLLM proxy** (server-push pattern) — https://docs.litellm.ai/docs/proxy/quick_start
- **AgentOps** (SaaS alternative to this) — https://docs.agentops.ai/
- **OpenLLMetry** (open standard for LLM tracing) — https://github.com/traceloop/openllmetry

### 🏋️ Homework 12.1 — Instrument your own Ollama calls

Goal: capture usage from the Telegram bot's own chat calls, so spend
from natural-language chats is logged automatically.

1. Open [app/services/llm_service.py](app/services/llm_service.py).
2. Find the call to Ollama (`httpx.post(...)` or similar). After the
   response, read `eval_count` + `prompt_eval_count` from the JSON —
   Ollama returns these.
3. POST a ledger row with `tool="api"`, `model=<the ollama model>`,
   `input_tokens=prompt_eval_count`, `output_tokens=eval_count`,
   `session_id=<telegram user id or chat session>`.
4. Use `memorycore_usage.UsageService.log(...)` in-process (faster
   than HTTP to yourself) — import the service from
   [app/modules/memorycore/service.py](app/modules/memorycore/service.py).

After this, every Telegram chat message logs cost, visible via
`/usage` or `./memorycore_cli usage today`. The word "universal" stops
being aspirational.

### 🏋️ Homework 12.2 — Track cost per user

The ledger already has `user_id`. Add a Telegram subcommand
`/usage by-user` that returns per-user totals. Useful when you open
the bot to a small group.

### Gotchas

- **`python` vs `python3` on Windows.** [.claude/settings.json](.claude/settings.json)
  uses `python` — Python 3 on Windows installers default to this.
  On Linux you may need `python3`. The hook itself is Python 3.
- **Hook transcript path may not exist.** The script handles this:
  returns silently. Don't assume Claude Code always writes a
  transcript — quick one-shot `claude -p` calls may not.
- **Stop hook runs even on ESC / Ctrl-C.** That's intentional — you
  get logging for interrupted sessions. The transcript may have less
  data than a full session, but whatever the agent actually spent is
  captured.
- **Codex session file format may change** (it's new). The wrapper
  script tolerates missing fields by logging zero-tokens-with-note.
- **Cache-read tokens are mostly free.** They're tracked separately
  so you can see the cache-hit rate, but
  [pricing.py](app/modules/memorycore/pricing.py) doesn't currently
  multiply them into cost. Add that if you want fine-grained cost
  reporting (Anthropic charges ~10% of normal input for cache reads).

### What's next (not built yet)

- **Per-prompt cost, not per-session.** Today we log one row per
  session. If you want per-prompt granularity, the hook would need to
  fire after every assistant turn (not just at Stop). Claude Code has
  a `PostToolUse` hook that could do this.
- **Budget alerts.** Add a scheduled Celery task that checks today's
  spend and fires a Telegram message when it crosses a threshold.
- **LiteLLM gateway.** Route all LLM traffic (Claude, OpenAI, Gemini,
  Ollama) through LiteLLM, log from there → zero agent-side
  instrumentation. Biggest long-term win, biggest refactor.

---

## 13. OpenClaw-style — `/claude` command + session pings + approval round-trip

### What we built

Three tightly-related pieces that together make your project behave like
**OpenClaw** (self-hosted personal AI agent reachable via Telegram):

**Step 1 — `/claude <agent> | <path> | <prompt>`** Telegram command.
Dispatches a Claude Code prompt to a named agent PC via the existing
NL-routed agent pipeline. Agent on the PC runs `claude -p "…"` in the
given path, transcript saved locally, result posted back. Counterpart
to the existing `/codex` command.

**Step 2 — Session-finished Telegram ping.** The existing
[`log-usage.py`](.claude/hooks/log-usage.py) Stop hook now passes
`?notify=true`. Server calls Telegram's `sendMessage` API after
persisting the ledger row so you see every completed session in chat
without polling.

**Step 3 — Telegram-gated approval round-trip** (the feature you
originally asked for). New [app/modules/approvals/](app/modules/approvals/)
module. PreToolUse hook on Claude Code detects risky actions (rm -rf,
systemctl, docker rm, sudo, unknown Bash, writes outside the project),
POSTs a pending approval, server sends a Telegram message with
Approve/Deny buttons, hook polls for your decision, Claude blocks or
proceeds accordingly. Times out to "deny" after 5 minutes.

Files created or changed:
- [app/bot/handlers.py](app/bot/handlers.py) — `claude_command`,
  `approval_callback`, `CallbackQueryHandler` registration, `/claude`
  + `/usage` in BotCommands.
- [app/modules/memorycore/service.py](app/modules/memorycore/service.py) —
  `notify_telegram_usage` helper.
- [app/modules/memorycore/api.py](app/modules/memorycore/api.py) —
  `?notify=true` query param on POST /usage.
- [app/modules/approvals/](app/modules/approvals/) — **new module**:
  `__init__.py`, `models.py`, `schemas.py`, `service.py`, `api.py`.
- [app/modules/__init__.py](app/modules/__init__.py) — registers
  `approvals` alongside `memorycore`.
- [.claude/hooks/log-usage.py](.claude/hooks/log-usage.py) — passes the
  notify flag.
- [.claude/hooks/approval.py](.claude/hooks/approval.py) — **new** PreToolUse hook.
- [.claude/settings.json](.claude/settings.json) — wires both hooks.
- [alembic/versions/e0f91cf2aa82_add_pending_approvals.py](alembic/versions/) —
  migration for `pending_approvals` table.

### Concept 1 — Fail-open vs fail-closed for approvals

The PreToolUse hook has two failure modes to choose between:

| Mode | If server is unreachable | If server times out waiting for you |
|---|---|---|
| **Fail-open** | allow the action (log warning) | allow (not relevant) |
| **Fail-closed** | block the action | block |

We chose **fail-open on server unreachable** (you can still use Claude
Code offline) but **fail-closed on human timeout** (assume denial if
you didn't see the Telegram message in 5 min). This is the pragmatic
default: prioritize developer productivity when infrastructure is
broken, prioritize safety when a human is just slow.

Flip to fully fail-closed by changing `return 0` to `return 2` in
`_post_json` failure branch. The comment in
[approval.py](.claude/hooks/approval.py) explicitly flags this as a
knob.

### Concept 2 — PreToolUse policy — allowlist, denylist, everything else

Three tiers in the hook:

1. **Auto-allow** (no approval):
   - `Read`, `Grep`, `Glob`, `Notebook`, `ToolSearch` — read-only tools.
   - Safe Bash patterns: `ls`, `pwd`, `git status`, `git diff`,
     `docker ps`, etc.
2. **Always block until approved**:
   - Dangerous Bash patterns: `rm -rf`, `mkfs`, `dd if=`, `sudo`,
     `docker rm`, `kubectl delete`, `git push --force`, etc.
   - Writes to `/etc`, `/usr`, or paths containing `..`.
3. **Unknown Bash / unknown tool**: **fail-closed** — require approval.

The "unknown → approval" default is important. If a future Claude Code
gains a new tool, you don't silently get exposure. You find out because
a Telegram approval request appears.

### Concept 3 — The round-trip timing model

```
  Claude Code        Hook           Cloud API        Telegram       You
       │               │                │               │            │
       │─PreToolUse──▶ │                │               │            │
       │               │── POST ─────▶  │               │            │
       │               │                │── sendMessage ▶            │
       │               │                │               │─ buttons ─▶│
       │               │                │               │            │
       │               │                │               │◀── tap ────│
       │               │                │◀─ callback ───│            │
       │               │── GET (poll)──▶│ status=approved            │
       │               │◀─────────────  │                            │
       │◀── exit 0 ─── │                │                            │
       │ runs tool ... │                │                            │
```

**Why polling, not push?** Because Claude Code hooks are synchronous
shell commands. They can't receive events. If the hook returns, the
decision is final — no way to call back later. Polling is how you
simulate bidirectional comms in a one-shot process.

**Alternative** would be a persistent daemon that keeps WebSocket
connections open. Overkill for this scale. Polling every 3 seconds
for 5 minutes = 100 cheap `GET` calls max. Not a problem.

### Concept 4 — Telegram inline keyboards

```python
{"reply_markup": {
    "inline_keyboard": [[
        {"text": "✅ Approve", "callback_data": f"app_approve:{approval_id}"},
        {"text": "🚫 Deny", "callback_data": f"app_deny:{approval_id}"},
    ]]
}}
```

`callback_data` is an opaque string (max 64 bytes) that Telegram echoes
back to your bot when the user taps. Our pattern:
`<action>:<identifier>`. The bot's `CallbackQueryHandler(pattern=r"^app_")`
regex-matches only our buttons, parses the pair, POSTs to
`/api/v1/approvals/{id}/decide`, and calls
`query.answer()` to dismiss the spinner.

**Security note:** `callback_data` is controlled by whoever sends the
button. A malicious actor who could send Telegram messages as your bot
could forge decisions. Mitigation:
- Telegram bot token is only known to the bot.
- The `approval_callback` handler checks `is_authorized(from_user.id)`
  before acting — same gate every other command uses.

### Concept 5 — Module-level notify vs sidecar service

Notice `notify_telegram_usage` lives in
[app/modules/memorycore/service.py](app/modules/memorycore/service.py),
not in a separate "notifications" module. Tradeoff:

- **In-module**: fewer files, but `memorycore` now knows how to talk
  to Telegram. That's outside its single responsibility.
- **Separate notifications module**: cleaner separation, but adds a
  contract + a new module for two tiny features.

For a side project I chose in-module. When this grows to "also email,
also Slack, also webhook," a dedicated `app/modules/notifications/`
with a `Notification` contract (and `memorycore` / `approvals` both
firing `Notification` events) is the right refactor. Not worth it for
two use sites.

### 💡 Try it — full end-to-end

**1. Test approval API directly:**
```bash
# Create a pending approval
curl -X POST "http://localhost:8000/api/v1/approvals?user_id=fitclaw" \
  -H "Content-Type: application/json" \
  -d '{"source":"claude_code","session_id":"test","tool_name":"Bash","action_summary":"rm -rf /tmp/foo","action_detail":{"tool_input":{"command":"rm -rf /tmp/foo"}}}'

# Check status
curl http://localhost:8000/api/v1/approvals/apr_XXXX

# Decide from server
curl -X POST http://localhost:8000/api/v1/approvals/apr_XXXX/decide \
  -H "Content-Type: application/json" \
  -d '{"approved":true,"decided_by":"manual-test"}'
```

**2. Test the hook script locally:**
```bash
# Safe command — exits 0 immediately
echo '{"tool_name":"Read","tool_input":{"file_path":"foo.txt"},"session_id":"x"}' \
  | python .claude/hooks/approval.py; echo "exit=$?"

# Dangerous command — creates approval, polls, times out at 5 seconds
APPROVAL_TIMEOUT_SEC=5 APPROVAL_POLL_SEC=1 \
  echo '{"tool_name":"Bash","tool_input":{"command":"rm -rf /tmp/foo"}}' \
  | python .claude/hooks/approval.py; echo "exit=$?"
```

**3. Real end-to-end** (requires Telegram configured):
- Set `TELEGRAM_BOT_TOKEN` and `DEFAULT_REPORT_CHAT_ID` in `.env`.
- Restart the api: `docker compose restart api`.
- Open Claude Code anywhere inside this project folder.
- Try to do anything dangerous — e.g. ask Claude to "delete the tmp
  folder." Claude's Bash call triggers the hook, hook POSTs, you get a
  Telegram message with Approve/Deny buttons. Tap one, Claude Code
  continues or blocks.

**4. `/claude` command** (requires an agent_daemon installed on a PC):
```
/claude office-pc | C:\projects\myrepo | add a unit test for UsageService
```
The bot sends this as a task to the `office-pc` agent. When the agent
processes it, the PC runs `claude -p "…"` in the path.

### Sandbox resources

- **Claude Code hooks reference** — https://docs.anthropic.com/en/docs/claude-code/hooks
- **Telegram bot API inline keyboards** — https://core.telegram.org/bots/features#inline-keyboards
- **python-telegram-bot CallbackQueryHandler** — https://docs.python-telegram-bot.org/en/stable/telegram.ext.callbackqueryhandler.html
- **OpenClaw GitHub** — https://github.com/openclaw/openclaw
- **shinglokto/openclaw-claude-bridge** (if you want to compare architectures) —
  https://github.com/shinglokto/openclaw-claude-bridge

### 🏋️ Homework 13.1 — Stale pending cleanup

After 5 minutes of no decision, the hook exits with "timeout" but the
DB row is still `status=pending`. Add a Celery beat task that runs every
5 minutes and marks rows older than 1 hour as `status=timeout`. This is
your first Celery beat task.

### 🏋️ Homework 13.2 — Per-action audit history

Every approval decision is a log entry you'll wish you had later.
Create a `ApprovalAuditLog` table + service that records every create
and every decide call with timestamps. The `decided_at` on
`pending_approvals` covers the minimum case, but a separate audit log
means you can see the *path* of approvals over time, including any
denied ones.

### 🏋️ Homework 13.3 — Richer Telegram formatting

The current "Approval needed" message is plain text. Make it:
- Use Telegram Markdown (`parse_mode: MarkdownV2`) for the command.
- Include a preview of what the tool will do (e.g. diff for Edit, full
  command for Bash).
- Add a "Show details" button that posts the full `action_detail`
  JSON as a code block in a reply.

### Gotchas

- **Image layer staleness with Alembic migrations.** When you
  autogenerate a new migration via bind-mount and then rebuild the
  image *without* the migration file included, the container's
  `alembic upgrade head` tries to migrate to a revision the image
  doesn't know about. Always rebuild the image after adding a new
  revision file (the file gets baked in via `COPY . /app`).
- **`Bash` matcher in `.claude/settings.json`.** We use
  `"matcher": "Bash|Write|Edit|NotebookEdit"` — the regex form Claude
  Code expects. A plain `"Bash"` matcher also works (exact string
  match). Case-sensitive.
- **`query.answer()` is not optional.** Telegram shows a spinner on
  the button until you call `answer()`. Without it, the UI looks
  broken even if your backend succeeded.
- **Callback data is max 64 bytes.** UUIDs are 36 chars, plus your
  action prefix. Fits. Don't pack structured data in there — use DB
  lookups instead.

### What's next (not built today)

- **Real agent_daemon support for `claude_prompt` task type.** Today
  `/claude` builds a natural-language dispatch message ("run this
  prompt inside claude code on X"). For the agent to actually execute
  it, the PC-side `agent_daemon` needs a command handler that spawns
  `claude -p "<prompt>"`. See the agent_daemon's task_executor.py for
  the shape — homework in a later session.
- **OAuth / per-user approval routing.** Today every approval goes to
  `DEFAULT_REPORT_CHAT_ID`. Multi-user needs per-user chat IDs in
  `memorycore_profile`.
- **Expire auto-approve for repeat commands.** If you approve
  `docker system prune` once, you might want to auto-approve it again
  for the next 10 minutes in the same session. Cache layer homework.

---

## 14. Multi-project fix-and-deploy loop — registry + /fix + /push + /deploy

### What we built (Stages A → D)

The full Telegram → AI fix → push → auto-deploy loop, working across
many projects, with one Telegram command per stage. Universal: any
project that defines a `deploy_command` (Docker, PM2, systemd,
whatever) plugs in.

**Stage A — Project registry.** New module
[app/modules/projects/](app/modules/projects/) with table `projects`,
full CRUD API at `/api/v1/projects/*`, plus a `/match` endpoint that
returns projects whose slug/name/keywords appear as substrings of an
input string ("the button is broken on fitclaw" → matches `fitclaw`).

**Stage B — `/fix` command.** Telegram `/fix <slug> | <issue>` looks up
the project, dispatches a Claude Code fix request to its registered
PC agent via the existing NL-routing pipeline (the same one `/codex`
uses). The agent runs `git pull` → `claude -p "<issue>"` → leaves
changes uncommitted in the working tree.

**Stage C — `/push` command.** Telegram `/push <slug>` shows an inline
keyboard with that project's branches. Tapping a branch dispatches a
`git_push` task to the agent: stage, commit, push.

**Stage D — `/deploy` command.** Telegram `/deploy <slug> [branch]`
runs the project's `deploy_command` on this VPS via `subprocess`,
streams exit code + tail of stdout/stderr back as a Telegram message.

### Files added/changed

- [app/modules/projects/](app/modules/projects/) — full module (5 files).
- [app/modules/__init__.py](app/modules/__init__.py) — registers `projects`.
- [alembic/versions/02553c1779ee_add_projects.py](alembic/versions/) — migration.
- [app/services/vps_stats_service.py](app/services/vps_stats_service.py) —
  new `ProjectsClient` (list/match/get/deploy from inside the bot).
- [app/bot/handlers.py](app/bot/handlers.py) — `/projects`, `/fix`,
  `/push`, `/deploy` commands + branch & deploy callback handlers,
  inline keyboards.
- [agent_daemon/ai_ops_agent/claude_fix_executor.py](agent_daemon/ai_ops_agent/claude_fix_executor.py) —
  drop-in handlers for `claude_fix` and `git_push` command types,
  ready to wire into `task_executor.py` on the PC.

### Concept 1 — One-table-rules-them-all

Every project becomes a single row:

| Field | Purpose |
|---|---|
| `slug` | Stable identifier used by Telegram commands |
| `name`, `description`, `keywords` | NL matching |
| `repo_url`, `default_branch`, `branches` | Git side |
| `agent_name`, `local_path` | Where to run the fix on PC |
| `vps_path`, `deploy_command` | How to redeploy on this VPS |

The `deploy_command` is a free-form shell string — the universal
escape hatch. Examples:

```bash
# Docker compose
cd /home/admin/fitclaw && git pull && docker compose pull && docker compose up -d

# PM2 (Node)
cd /var/www/myapp && git pull && npm ci --production && pm2 reload myapp

# systemd
cd /opt/myservice && git pull && sudo systemctl restart myservice

# Static site
cd /var/www/landing && git pull && npm run build
```

The server passes `$PROJECT_SLUG` and `$PROJECT_BRANCH` as env vars so
your script can use them.

### Concept 2 — NL match without ML

[ProjectService.match_by_text](app/modules/projects/service.py) is 12
lines of code: lowercase the input, lowercase each project's
slug/name/keywords, return projects with any substring hit. **No
embeddings, no LLM.** This is enough until you have ~50+ projects with
overlapping keywords. When that day comes, swap the implementation
behind the same function signature; callers don't change.

Lesson: **start with the dumbest possible version.** If
`"fitclaw" in "fix the button on fitclaw"` solves your need, you
don't need pgvector. The cost of overengineering this early is real:
embeddings, API calls, an extra dependency, a learning curve, and an
extra failure mode.

### Concept 3 — Inline keyboards as state machines

The Telegram inline keyboard pattern from approvals (§13) generalizes:

| Step | Sent | callback_data |
|---|---|---|
| `/push fitclaw` | "Choose target branch" + buttons | `push_branch:fitclaw:main` |
| User taps `dev` | (callback fires) | `push_branch:fitclaw:dev` |
| Bot dispatches `git_push` task | "Push dispatched…" | — |

Each callback is a state transition. Encode the next-step intent in
`callback_data` (max 64 bytes — slug + branch fits). For anything
larger than 64 bytes, look it up by ID from a table.

The whole flow has no server-side session/state machinery. Every
button tap is self-contained, looks up DB rows by ID, performs an
action, edits the message. Stateless server, state in the user's
chat history. Robust.

### Concept 4 — Why the agent just does git, no merge magic

The PC agent's `git_push` handler is intentionally simple:
`add -A && commit -m '<msg>' && push origin <branch>`. It does not
try to rebase, resolve conflicts, or open PRs.

Reasoning: anything more sophisticated requires human judgment when
something goes wrong. Better to fail loudly ("push failed: rejected
non-fast-forward") and let you decide than to auto-resolve and create
silent merges. The agent is an executor, not a maintainer.

For PR creation, the right tool is `gh pr create` from inside the
agent. Add later as a homework — it's 5 lines.

### Concept 5 — Deploy security

`run_deploy` in [service.py](app/modules/projects/service.py) executes
`/bin/sh -c "<deploy_command>"` with the project's vps_path as cwd.
That's potentially dangerous if anyone untrusted can write to the
projects table. Mitigations:

1. **The project registry is owner-only.** Only `fitclaw` (you) writes
   to it. Telegram `is_authorized` gate on `/deploy` ensures the
   command can only fire from you.
2. **`_safe_env()` strips most env vars** before the subprocess. The
   shell sees only `PATH`, `HOME`, `USER`, etc. plus
   `$PROJECT_SLUG` and `$PROJECT_BRANCH`. Your bot token doesn't
   leak into the deploy script.
3. **Timeout = 600s.** A runaway deploy command can't hang the api
   forever.
4. **stdout / stderr are captured.** No surprise interactive prompts.

Improvements to do later: run deploys as a non-root user, log every
deploy to an audit table (similar to homework 13.2), require a second
approval via the inline keyboard for `production` branch deploys.

### 💡 Try it — full QA

```bash
# Stage A: register a project
curl -X PUT "http://localhost:8000/api/v1/projects/fitclaw?user_id=fitclaw" \
  -H "Content-Type: application/json" \
  -d '{
    "slug": "fitclaw",
    "name": "Personal AI Ops Platform",
    "keywords": ["fitclaw", "memorycore", "ai-ops"],
    "branches": ["main", "dev", "staging"],
    "agent_name": "office-pc",
    "local_path": "/home/you/projects/fitclaw",
    "vps_path": "/home/admin/fitclaw",
    "deploy_command": "echo deploy $PROJECT_SLUG branch=$PROJECT_BRANCH && date"
  }'

# Stage A: NL match
curl "http://localhost:8000/api/v1/projects/match?user_id=fitclaw&q=fix+the+button+on+fitclaw"

# Stage D: deploy
curl -X POST "http://localhost:8000/api/v1/projects/fitclaw/deploy?user_id=fitclaw" \
  -H "Content-Type: application/json" -d '{"branch":"main"}'

# Telegram (requires the bot up + your chat authorized):
/projects                                  # lists registered projects
/fix fitclaw | the /usage button is broken # dispatches fix
/push fitclaw                              # branch selection keyboard
/deploy fitclaw main                       # confirm-then-deploy keyboard
```

### 🏋️ Homework 14.1 — Wire the executor into agent_daemon

The drop-in module
[agent_daemon/ai_ops_agent/claude_fix_executor.py](agent_daemon/ai_ops_agent/claude_fix_executor.py)
defines `run_claude_fix(payload)` and `run_git_push(payload)`. Open
`task_executor.py` and add:

```python
from .claude_fix_executor import run_claude_fix, run_git_push

# inside execute_task or wherever device_command_type is dispatched:
if device_command_type == "claude_fix":
    return run_claude_fix(payload_json)
if device_command_type == "git_push":
    return run_git_push(payload_json)
```

You'll also need to teach the server's NL message routing to emit
`device_command_type="claude_fix"` for "run this prompt inside claude
code on …" messages. Look at how `codex` is currently routed in
[app/services/](app/services/) and clone the pattern. Estimated 1–2
hours.

### 🏋️ Homework 14.2 — `gh pr create` instead of direct push

Modify `run_git_push` to push to a feature branch (e.g.
`fix/<slug>-<timestamp>`), then run `gh pr create --base <chosen> --head <feature>`,
and return the PR URL. Telegram sends the URL as a clickable link.
This is a strictly better workflow for shared repos — review before
merge.

### 🏋️ Homework 14.3 — Deploy audit table

Mirror the approval pattern: a `deploy_audit` table that records every
`/deploy` invocation (slug, branch, exit_code, started_at,
duration_ms, decided_by). Add `/audit deploy` Telegram command to
review the last 10.

### Gotchas

- **`vps_path` must exist on the api container's filesystem** for
  `subprocess.run(cwd=...)` to work. We added a fallback that drops
  the cwd if the path is missing — useful for smoke tests, but for
  real deploys you need to either (a) bind-mount the path into the
  api container or (b) make the deploy_command SSH out to a separate
  deploy host (`ssh deploy@vps "cd /path && docker compose up -d"`).
- **Telegram callback_data is 64 bytes max.** `push_branch:<slug>:<branch>`
  fits as long as both stay short. If you ever have a slug or branch
  over ~25 chars, look up by ID instead of packing into callback_data.
- **`process_message_sync` for /fix and /push** uses your existing NL
  routing layer. If the routing layer doesn't yet recognize "run this
  prompt inside claude code on …", the dispatch silently no-ops. Wire
  it (homework 14.1) for the loop to actually execute on a real PC.

### What's next (not built today)

- **Streaming deploy logs.** Today /deploy returns a single message
  after `subprocess.run` finishes. For real-world deploys (5+ min)
  you want progressive log streaming back to Telegram. Pattern:
  spawn the subprocess, read stdout in chunks, edit the Telegram
  message every ~2 seconds with the latest tail.
- **Webhook from GitHub.** Instead of /deploy from Telegram, listen
  for `git push` webhooks and auto-deploy. Adds zero risk if the
  deploy command is idempotent.
- **Per-project AGENTS.md fetch.** Currently the agent assumes the
  project repo has its own AGENTS.md. If not, the bot could fetch
  one centrally. v2.

---

## 📚 Sandbox & learning resources

Everything below is free (or has a generous free tier). Curated by topic,
not alphabetical — the top of each list is where to start.

### Go

**Official / first-stop**
- 🏖 **Go Playground** — https://go.dev/play/ — online compiler, share snippets
- 📘 **A Tour of Go** — https://go.dev/tour/welcome/1 — interactive official tutorial
- 📘 **Go by Example** — https://gobyexample.com/ — annotated snippets for every concept
- 📘 **Effective Go** — https://go.dev/doc/effective_go — the idiom bible
- 📘 **Go Standard Library** — https://pkg.go.dev/std — bookmark forever
- 📘 **Official FAQ** — https://go.dev/doc/faq — answers "why does Go do X"

**Practice**
- 🏋️ **Exercism Go track** — https://exercism.org/tracks/go — exercises + mentor feedback, free
- 🏋️ **Learn Go with Tests** — https://quii.gitbook.io/learn-go-with-tests — TDD-style, excellent
- 🏋️ **Gophercises** — https://gophercises.com/ — practical projects
- 🏋️ **Codewars Go** — https://www.codewars.com/?language=go — short kata

**Deeper / advanced**
- 📘 **The Go Memory Model** — https://go.dev/ref/mem — concurrency primitives formally
- 📘 **Context package guide** — https://go.dev/blog/context — read before writing servers
- 📘 **Awesome Go** — https://github.com/avelino/awesome-go — curated library list
- 📘 **Uber Go Style Guide** — https://github.com/uber-go/guide/blob/master/style.md — industry-strength conventions

**Books (pick one — don't read all)**
- 📚 *Learning Go* (2nd ed) by Jon Bodner — best single book for beginners
- 📚 *The Go Programming Language* by Donovan & Kernighan — the canonical reference
- 📚 *100 Go Mistakes* by Teiva Harsanyi — patterns to avoid

---

### Python

**Level up from comfortable**
- 📘 **Real Python** — https://realpython.com/ — deep tutorials, free tier is huge
- 📘 **PyMOTW (Python Module of the Week)** — https://pymotw.com/3/ — every stdlib module
- 📘 **Python HOWTOs** — https://docs.python.org/3/howto/ — official, underrated

**Async & concurrency**
- 📘 **asyncio docs** — https://docs.python.org/3/library/asyncio.html
- 📘 **Async IO in Python (Real Python)** — https://realpython.com/async-io-python/
- 📘 **Trio tutorial** — https://trio.readthedocs.io/ — cleaner async model, good for comparison

**Testing**
- 📘 **pytest** — https://docs.pytest.org/en/stable/ — learn fixtures + parametrize deeply
- 🏋️ **Practice Python** — https://www.practicepython.org/ — free exercises

---

### FastAPI (this project's framework)

- 📘 **Official docs / tutorial** — https://fastapi.tiangolo.com/tutorial/ — genuinely excellent
- 📘 **FastAPI Users** — https://fastapi-users.github.io/ — auth reference implementation
- 📘 **SQLAlchemy 2.0 with FastAPI** — https://fastapi.tiangolo.com/tutorial/sql-databases/
- 📘 **Pydantic v2 migration guide** — https://docs.pydantic.dev/latest/migration/
- 📘 **Deployment patterns** — https://fastapi.tiangolo.com/deployment/
- 🏖 **Awesome FastAPI** — https://github.com/mjhea0/awesome-fastapi

---

### Django (if you're branching out — this project uses FastAPI, but the skills transfer)

- 📘 **Official tutorial** — https://docs.djangoproject.com/en/stable/intro/tutorial01/ — seven-part walkthrough, builds a polls app
- 📘 **Django docs** — https://docs.djangoproject.com/ — exhaustive, readable
- 📘 **Django for Beginners (book)** — https://djangoforbeginners.com/ — William Vincent, concise
- 📘 **Django REST Framework tutorial** — https://www.django-rest-framework.org/tutorial/quickstart/ — when you want API endpoints
- 📘 **Two Scoops of Django (book)** — https://www.feldroy.com/books/two-scoops-of-django — production-grade patterns
- 📘 **HackSoftware Django styleguide** — https://github.com/HackSoftware/Django-Styleguide — opinionated project layout
- 📘 **Awesome Django** — https://github.com/wsvincent/awesome-django — library list
- 🏋️ **Django Packages** — https://djangopackages.org/ — curated reusable apps

**Django vs FastAPI (reality check)**
- Django: full-stack (ORM, admin, templating), batteries-included, great for CRUD apps + Jinja/HTMX frontends.
- FastAPI: pure API framework, async-first, Pydantic-driven. What this project uses.
- Both coexist peacefully. Many projects run Django for admin + FastAPI for high-throughput APIs.

---

### Docker

- 📘 **Docker 101 tutorial** — https://www.docker.com/101-tutorial/ — interactive
- 📘 **Docker documentation** — https://docs.docker.com/ — reference
- 📘 **Dockerfile best practices** — https://docs.docker.com/develop/develop-images/dockerfile_best-practices/
- 📘 **Play with Docker** — https://labs.play-with-docker.com/ — free 4-hour sandboxes in browser
- 📘 **Docker compose reference** — https://docs.docker.com/compose/compose-file/
- 🏋️ **Docker Curriculum** — https://docker-curriculum.com/ — Prakhar Srivastav, hands-on walkthrough
- 📘 **Awesome Docker** — https://github.com/veggiemonk/awesome-docker

**Multi-stage / production**
- 📘 **Docker image size optimization** — https://docs.docker.com/develop/develop-images/multistage-build/
- 📘 **distroless images** — https://github.com/GoogleContainerTools/distroless — smallest production images
- 📘 **buildx** — https://docs.docker.com/build/buildx/ — multi-arch builds

---

### Kubernetes

**Level 1 — get started**
- 🏖 **killercoda** — https://killercoda.com/playgrounds/scenario/kubernetes — instant in-browser cluster
- 🏖 **Play with Kubernetes** — https://labs.play-with-k8s.com/ — free 4-hour clusters
- 🏖 **k3d** — https://k3d.io/ — what we use, local k8s in Docker
- 🏖 **kind** — https://kind.sigs.k8s.io/ — alternative to k3d
- 🏖 **minikube** — https://minikube.sigs.k8s.io/ — official local cluster

**Level 2 — learn concepts**
- 📘 **Official tutorials** — https://kubernetes.io/docs/tutorials/ — genuinely good
- 📘 **kubectl cheat sheet** — https://kubernetes.io/docs/reference/kubectl/cheatsheet/ — bookmark
- 📘 **Kubernetes the Hard Way** — https://github.com/kelseyhightower/kubernetes-the-hard-way — set up from scratch, illuminating
- 📘 **learnk8s articles** — https://learnk8s.io/blog — opinionated long reads

**Level 3 — go deeper**
- 📘 **Helm docs** — https://helm.sh/docs/ — the package manager
- 📘 **Kustomize docs** — https://kustomize.io/ — what we use in the manifests
- 📘 **Argo CD** — https://argo-cd.readthedocs.io/ — GitOps
- 📘 **Awesome Kubernetes** — https://github.com/ramitsurana/awesome-kubernetes

**Books (one is enough)**
- 📚 *Kubernetes Up & Running* (3rd ed) by Burns, Beda, Hightower — the standard intro
- 📚 *The Kubernetes Book* by Nigel Poulton — shorter alternative
- 📚 *Programming Kubernetes* by Hausenblas & Schimanski — operators + controllers

---

### Databases

**Postgres**
- 📘 **Official tutorial** — https://www.postgresql.org/docs/current/tutorial.html
- 📘 **PostgreSQL Exercises** — https://pgexercises.com/ — SQL drill site, free
- 📘 **Use The Index, Luke** — https://use-the-index-luke.com/ — how indexes actually work, free book
- 📘 **The Art of PostgreSQL** — https://theartofpostgresql.com/ — Dimitri Fontaine, paid book, worth it
- 📘 **pgvector** — https://github.com/pgvector/pgvector — semantic search inside Postgres

**SQLAlchemy**
- 📘 **SQLAlchemy 2.0 tutorial** — https://docs.sqlalchemy.org/en/20/tutorial/ — start here
- 📘 **SQLAlchemy 2.0 migration guide** — https://docs.sqlalchemy.org/en/20/changelog/migration_20.html

**Alembic**
- 📘 **Official tutorial** — https://alembic.sqlalchemy.org/en/latest/tutorial.html
- 📘 **Autogenerate docs** — https://alembic.sqlalchemy.org/en/latest/autogenerate.html — read the "what it can't detect" section

**Other DB topics**
- 📘 **Database migrations without downtime** — https://gocardless.com/blog/zero-downtime-postgres-migrations-the-hard-parts/
- 📘 **SQL style guide** — https://www.sqlstyle.guide/
- 📘 **Designing Data-Intensive Applications** by Kleppmann — *the* distributed-data book 📚

---

### Machine Learning

**Starting point**
- 🏖 **Google Colab** — https://colab.research.google.com/ — free GPU Jupyter notebooks
- 🏖 **Kaggle** — https://www.kaggle.com/ — free notebooks + datasets + competitions
- 🏖 **Hugging Face Spaces** — https://huggingface.co/spaces — free hosted demos

**Courses (genuinely good, free)**
- 🏋️ **fast.ai** — https://course.fast.ai/ — practical deep learning, top-down teaching
- 🏋️ **Hugging Face course** — https://huggingface.co/learn — transformers, diffusion, audio
- 🏋️ **Andrew Ng ML Specialization** — https://www.coursera.org/specializations/machine-learning-introduction — classic foundations, audit free
- 🏋️ **DeepLearning.AI short courses** — https://www.deeplearning.ai/short-courses/

**Frameworks**
- 📘 **PyTorch tutorials** — https://pytorch.org/tutorials/ — interactive, excellent
- 📘 **TensorFlow quickstarts** — https://www.tensorflow.org/tutorials
- 📘 **scikit-learn user guide** — https://scikit-learn.org/stable/user_guide.html — classical ML
- 📘 **JAX** — https://jax.readthedocs.io/ — if you want to go deep

**Computer vision (OpenCV)**
- 📘 **OpenCV tutorials** — https://docs.opencv.org/master/d9/df8/tutorial_root.html
- 📘 **PyImageSearch** — https://pyimagesearch.com/ — Adrian Rosebrock, practical CV, paid+free
- 📘 **Roboflow tutorials** — https://blog.roboflow.com/

**LLMs / agents**
- 📘 **Hugging Face model hub** — https://huggingface.co/models — thousands of pretrained models
- 📘 **Ollama** — https://ollama.com/ — local LLM runner (you're already using it)
- 📘 **LangChain docs** — https://python.langchain.com/ — LLM orchestration
- 📘 **Anthropic cookbook** — https://github.com/anthropics/anthropic-cookbook
- 📘 **OpenAI cookbook** — https://github.com/openai/openai-cookbook

**MLOps & serving**
- 📘 **MLflow** — https://mlflow.org/docs/latest/index.html — experiment tracking
- 📘 **BentoML** — https://docs.bentoml.org/ — ML model serving
- 📘 **NVIDIA Triton** — https://github.com/triton-inference-server/server — production GPU inference
- 📘 **Weights & Biases** — https://docs.wandb.ai/ — experiment tracking SaaS

---

### Observability

- 📘 **Prometheus docs** — https://prometheus.io/docs/introduction/overview/
- 📘 **PromQL primer** — https://prometheus.io/docs/prometheus/latest/querying/basics/
- 📘 **PromLabs PromQL cheat sheet** — https://promlabs.com/promql-cheat-sheet/
- 📘 **Grafana Play** — https://play.grafana.org/ — live demo dashboards to learn from
- 📘 **The Four Golden Signals** — https://sre.google/sre-book/monitoring-distributed-systems/ — Google SRE book, ch 6, free
- 📘 **RED and USE methods** — https://www.brendangregg.com/usemethod.html
- 📘 **OpenTelemetry docs** — https://opentelemetry.io/docs/ — for tracing later

---

### Telegram bots

- 📘 **python-telegram-bot docs** — https://docs.python-telegram-bot.org/
- 📘 **python-telegram-bot examples** — https://github.com/python-telegram-bot/python-telegram-bot/tree/master/examples
- 📘 **Telegram Bot API reference** — https://core.telegram.org/bots/api

---

### DevOps / Linux / systems

- 📘 **The Missing Semester of Your CS Education (MIT)** — https://missing.csail.mit.edu/ — shell, git, vim, debugging, free videos
- 📘 **Google SRE Books (free online)** — https://sre.google/books/ — all three
- 📘 **DigitalOcean tutorials** — https://www.digitalocean.com/community/tutorials — VPS, Nginx, systemd, everything
- 📘 **Julia Evans' zines / blog** — https://jvns.ca/ — short, deep posts on Linux + systems
- 📘 **Brendan Gregg's site** — https://www.brendangregg.com/ — performance, profiling, tracing

---

### Git & collaboration

- 📘 **Pro Git (free book)** — https://git-scm.com/book/en/v2
- 📘 **Learn Git Branching** — https://learngitbranching.js.org/ — visual interactive tutorial
- 📘 **GitHub Skills** — https://skills.github.com/ — hands-on GitHub tutorials
- 📘 **Oh Shit, Git!?!** — https://ohshitgit.com/ — how to recover from common mistakes

---

### Interview / general skill building

- 🏋️ **LeetCode** — https://leetcode.com/ — algorithms, pick Go for language practice
- 🏋️ **Advent of Code** — https://adventofcode.com/ — yearly 25-day puzzle, great Go practice
- 🏋️ **HackerRank** — https://www.hackerrank.com/
- 📘 **System Design Primer** — https://github.com/donnemartin/system-design-primer — free, comprehensive

---

### Staying current

- 📰 **Hacker News** — https://news.ycombinator.com/ — firehose, but filter ruthlessly
- 📰 **Lobste.rs** — https://lobste.rs/ — smaller, technical, curated
- 📰 **TLDR Newsletter** — https://tldr.tech/ — daily digest
- 📰 **DevOps Weekly** — https://www.devopsweekly.com/ — Gareth Rushgrove's long-running newsletter
- 📰 **Golang Weekly** — https://golangweekly.com/
- 📰 **Python Weekly** — https://www.pythonweekly.com/
- 📰 **KubeWeekly** — https://www.cncf.io/kubeweekly/

---

### Learning strategy (short note to yourself)

1. **Pick one new thing per session.** Trying to learn Go + k8s + ML simultaneously means learning none of them.
2. **Do the official tutorial first.** Even if it's "boring." The ecosystem assumes you did.
3. **Build something real ASAP.** Copy-typing tutorials is not learning. Modifying working code is.
4. **Read failing production code.** Open an issue on a real open-source project. Read the PRs. That's the level you're aiming at.
5. **Have a project that forces you to use the skill.** This repo is yours. Use it.

---

## Update rules for this file

I append a new numbered section every time we ship a unit of work. Sections
never get rewritten — they're a log. If I realize something was wrong in an
old section, I add a correction note dated at the top of that section, so
you can see the evolution.

You're free to scribble in this file too — add your own notes under
"🏋️ Homework" sections once you've done them, so future-you remembers what
worked.
