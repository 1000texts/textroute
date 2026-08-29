# Contributing to TextRoute

Thanks for helping improve TextRoute. This monorepo is designed so contributors can land small, reviewable changes.

## Prerequisites

- Docker + Docker Compose
- Python 3.13+ (for API unit tests outside Docker)
- Node 20.19+ (optional: `moderator-web`, `tools/sms-simulator`)

## Quick start

```bash
cp .env.example .env
# Edit LLM_MODELS_HOST_PATH (or point it at an empty dir for API-only work)

docker compose -f docker-compose.dev.yml up --build

# Include the moderator UI in the stack (optional)
docker compose -f docker-compose.dev.yml --profile ui up --build
```

| Service | URL |
|---------|-----|
| API | http://localhost:6060 |
| SMS simulator | http://localhost:5173 |
| Docs | http://localhost:8000 |
| Moderator UI | http://localhost:5174 (`--profile ui`, or run locally — see `moderator-web/`) |

The moderator UI is behind the `ui` profile so the default stack stays lean. Running
it on the host with `npm run dev` is still supported and gives faster hot reload; either
way it must be served from `http://localhost:5174`, since that origin is what the API
allows for CORS and scopes the session cookie to.

Postgres schema is applied from `infra/postgres/initdb/` on **first** volume create. To reset schema: `docker compose -f docker-compose.dev.yml down -v` then bring the stack up again.

There is no Alembic, so any change under `infra/postgres/initdb/` needs that reset before it takes effect locally.

For a database with data worth keeping, one-off scripts under `textroute-api/sql/` migrate in place instead. The latest is `2026-08-28_requests_as_lifecycle.sql`, which adds `messages.sender_role` and `messages.author_member_id` with the `messages_role_shape_check` constraint, widens `messages.kind` to the five roles, creates `request_events`, swaps the one-open-per-group index for one-open-per-requester, and narrows `requests.embedding` to 1024 dimensions:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f textroute-api/sql/2026-08-28_requests_as_lifecycle.sql
```

Every constraint in it is added `NOT VALID` and validated after the backfill, so it is safe to run against live messages. Keep both paths in sync: `initdb/` is the definition for a fresh database, and the script is how existing ones catch up.

Generate a local moderator-auth secret before starting:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
# copy the result to AUTH_SECRET in .env
```

With `AUTH_EXPOSE_DEVELOPMENT_CODE=true`, moderator-web displays the login code
returned by the API. This is local-only behavior; production must keep it
disabled. `SMS_PROVIDER=logging` prints the local challenge send; production
should configure `SMS_PROVIDER=http`. The raw code and session token are never
stored in PostgreSQL.

Helper scripts (from repo root):

```bash
./infra/scripts/dev-up.sh
./infra/scripts/dev-down.sh
./infra/scripts/log.sh textroute
```

## API development conventions

Layers (do not skip or invert):

```
api/routes  →  services  →  core (managers/providers/processors)  →  models / db
```

| Layer | Responsibility |
|-------|----------------|
| `api/routes` | HTTP only: grouped by trust boundary; parse request, map domain errors → status codes |
| `services` | Orchestration; owns `db.commit()` / `db.rollback()` |
| `core` | Persistence managers (`flush` only), phone normalize, `MessageProcessor`, `SmsProvider` |
| `models` | SQLAlchemy ORM |
| `schemas/api` | HTTP DTOs |
| `schemas/intent` + `domain` + `ai` | Intent / matching (processor v1 is heuristic; LLM stack optional) |

Rules of thumb:

- Phone numbers are identity keys — always normalize to E.164 via `normalize_phone_number`.
- Managers use `db.flush()` only: flush makes generated values available within
  the current transaction; it does not make changes durable.
- Services own the business transaction and decide when to `db.commit()` or
  `db.rollback()`. Routes may defensively roll back after an exception, but
  must not commit or split a service transaction.
- Protected group mutations derive `group_id` from the moderator's server-side
  session; never trust a group ID or inbound number supplied by the browser.
- Cookie auth CSRF stance is documented in `textroute-api/README.md` (SameSite=Lax
  + same-site UI/API). Revisit before any cross-site cookie deployment.
- `parent_message_id` = message-graph link to the original routed inbound (not a
  Conversation entity). The 72h fan-out reply heuristic is temporary scaffolding;
  see `textroute-api/README.md`.
- New routing requests default to group-wide suggestions; the processor recommends,
  the moderator decides. Do not treat profile matches as the only recipients.
- Prefer small PRs that touch one concern (schema, route, service, tests).

Product vision and message flow live in [textroute-api/README.md](textroute-api/README.md) and [docs/mkdocs/](docs/mkdocs/).

## Tests

```bash
cd textroute-api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev]"   # optional; pytest is also in requirements.txt
pytest
```

CI runs the same `pytest` job on pull requests.

## Pull requests

1. Branch from `main` (or the current default branch).
2. Keep the diff focused; update or add tests for behavior changes.
3. Describe **why** in the PR body; link issues when relevant.
4. Do not commit `.env`, secrets, or nested vendor clones (e.g. `infra/postgres/pgvector/`).
   Put credentials only in `.env` (gitignored). Tracked `.vscode/launch.json` files must
   load secrets via `"envFile"` — never hard-code `DATABASE_URL`, passwords, or `AUTH_SECRET`.

## Debugging the API in VS Code / Cursor

Use the **TextRoute API** launch config (loads `${workspaceFolder}/.env`).
`DATABASE_URL` must use host `localhost` for host-run debugging. Compose sets
the API container to `DATABASE_URL_DOCKER` (host `postgres`). See `.env.example`.

## Questions

Open a GitHub Discussion or issue. Prefer issues with a clear reproduction over large speculative redesigns.
