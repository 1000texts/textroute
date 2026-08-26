# textroute-api

FastAPI service for TextRoute: inbound SMS webhooks, group creation, heuristic
intent suggestions, moderator approval, and outbound fan-out.

## Package layout

```
src/
  api/routes/     # Thin HTTP adapters
  services/       # Use-case orchestration; owns db.commit()
  core/           # *Manager (flush only), phone_normalize, MessageProcessor, SmsProvider
  models/         # SQLAlchemy ORM
  schemas/api.py  # HTTP DTOs
  schemas/intent/ # Structured AI outputs (future richer extraction)
  domain/         # Intent types + message workflow statuses
  ai/             # LLM helpers (optional; processor v1 is heuristic)
  config/         # Env + YAML loaders
  db/             # Engine + session (get_db)
tests/
```

Entry point: `src.main:app`.

## Vertical slice flow

```
SMS webhook
  → persist Message (received)
  → MessageProcessor → ProcessingResult (intent + suggested recipients)
  → awaiting_moderator
  → moderator approve/reject
  → MessagingService → SmsProvider → fan-out original body
  → recipient reply → persist (linked via parent_message_id)
```

`MessageProcessor` only recommends. It does not send SMS or commit.

## Common endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/groups` | Create group + assign TextRoute number |
| `POST` | `/groups/{id}/members` | Add an active member |
| `GET` | `/groups/{id}/members` | List active members |
| `POST` | `/webhook/messages` | Inbound SMS (`from` / `to` / `body`) |
| `POST` | `/webhook/inbound` | Alias of `/webhook/messages` |
| `GET` | `/groups/{id}/moderation/queue` | Messages awaiting moderator |
| `GET` | `/messages/{id}` | Message detail + eligible recipients |
| `POST` | `/messages/{id}/approve` | `{ "recipient_ids": [...] }` then fan-out |
| `POST` | `/messages/{id}/reject` | Mark moderator_rejected |
| `GET` | `/` | Health |

## Workflow statuses

`received` → `processing` → `awaiting_moderator` → `approved` → `delivering` → `delivered`

Failures: `processing_failed`, `moderator_rejected`, `delivery_failed`.

## Outbound SMS

```
MessagingService → SmsProvider (logging | http)
```

Set `SMS_PROVIDER=logging` (default) or `SMS_PROVIDER=http` with `SMS_PROVIDER_URL`.

## Local commands

```bash
pip install -r requirements.txt
pip install -e ".[dev]"
pytest
uvicorn src.main:app --reload --port 6060
```

Docker Compose (from repo root) is the preferred full stack. Schema lives in
`infra/postgres/initdb/` — reset with `docker compose -f docker-compose.dev.yml down -v`
after message-table changes. See [CONTRIBUTING.md](../CONTRIBUTING.md).
