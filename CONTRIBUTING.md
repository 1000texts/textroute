# Contributing to TextRoute

Thanks for helping improve TextRoute. This monorepo is designed so contributors can land small, reviewable changes.

## Prerequisites

- Docker + Docker Compose
- Python 3.13+ (for API unit tests outside Docker)
- Node 20+ (optional: `moderator-web`, `tools/sms-simulator`)

## Quick start

```bash
cp .env.example .env
# Edit LLM_MODELS_HOST_PATH (or point it at an empty dir for API-only work)

docker compose -f docker-compose.dev.yml up --build
```

| Service | URL |
|---------|-----|
| API | http://localhost:6060 |
| SMS simulator | http://localhost:5173 |
| Docs | http://localhost:8000 |
| Moderator UI | run locally — see `moderator-web/` |

Postgres schema is applied from `infra/postgres/initdb/` on **first** volume create. To reset schema: `docker compose -f docker-compose.dev.yml down -v` then bring the stack up again.

Helper scripts (from repo root):

```bash
./infra/scripts/dev-up.sh
./infra/scripts/dev-down.sh
./infra/scripts/log.sh textroute
```

## API development conventions

Layers (do not skip or invert):

```
api/routes  →  services  →  core (*_manager)  →  models / db
```

| Layer | Responsibility |
|-------|----------------|
| `api/routes` | HTTP only: parse request, map domain errors → status codes |
| `services` | Orchestration; owns `db.commit()` / `db.rollback()` |
| `core` | Persistence managers (`flush` only), phone normalize, `MessageProcessor`, `SmsProvider` |
| `models` | SQLAlchemy ORM |
| `schemas/api` | HTTP DTOs |
| `schemas/intent` + `domain` + `ai` | Intent / matching (processor v1 is heuristic; LLM stack optional) |

Rules of thumb:

- Phone numbers are identity keys — always normalize to E.164 via `normalize_phone_number`.
- Managers never commit.
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

## Questions

Open a GitHub Discussion or issue. Prefer issues with a clear reproduction over large speculative redesigns.
