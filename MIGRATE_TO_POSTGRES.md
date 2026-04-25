# Postgres migration runbook

One-time steps to switch this stack from SQLite to Postgres 16 with Alembic.
Existing SQLite data in `data/ai_ops.db` is **not** migrated — you chose a fresh start.

## 1. Set secrets in `.env`

Add these lines (or copy from the updated `.env.example`):

```
DATABASE_URL=postgresql+psycopg://aiops:CHANGE_ME@postgres:5432/aiops
POSTGRES_DB=aiops
POSTGRES_USER=aiops
POSTGRES_PASSWORD=CHANGE_ME
```

Replace `CHANGE_ME` in **both** places with the same strong password.

## 2. Tear down any existing stack

```
docker compose down
```

If you want to drop the old SQLite file as well:

```
rm data/ai_ops.db data/ai_ops.db-wal data/ai_ops.db-shm 2>/dev/null || true
```

## 3. Rebuild the image (pulls in `psycopg` and `alembic`)

```
docker compose build api
```

## 4. Start Postgres first

```
docker compose up -d postgres
docker compose logs -f postgres   # wait for "database system is ready to accept connections", then Ctrl-C
```

## 5. Generate the baseline Alembic migration from current models

```
docker compose run --rm api alembic revision --autogenerate -m "initial_schema"
```

This creates `alembic/versions/<hash>_initial_schema.py` covering every model
currently registered in `app/models/__init__.py`. **Open that file and skim it**
before committing — autogenerate is good but not perfect (it ignores indexes on
unmapped columns, enum renames, etc.). Commit it to git.

## 6. Bring up the rest of the stack

```
docker compose up -d
```

The `api` container runs `alembic upgrade head` before starting uvicorn, so the
schema is created on first boot. Subsequent boots are a no-op.

## 7. Verify

```
docker compose exec postgres psql -U aiops -d aiops -c "\dt"
```

You should see `agents`, `tasks`, `calendar_events`, `finance_entries`, etc., plus
an `alembic_version` table holding the current revision hash.

## Future schema changes

1. Edit a SQLAlchemy model.
2. `docker compose run --rm api alembic revision --autogenerate -m "describe change"`
3. Review the generated file in `alembic/versions/`.
4. Commit.
5. On deploy, the `api` container auto-runs `alembic upgrade head` on start.

## If autogenerate misses something

Autogenerate cannot detect: column renames (shows up as drop+add), some index
changes, server-side defaults, check constraints. For those, hand-edit the
generated migration file before committing.
