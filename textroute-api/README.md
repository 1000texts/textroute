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
| `POST` | `/auth/challenge` | Request moderator confirmation code |
| `POST` | `/auth/verify` | Verify code and create HttpOnly session |
| `GET` | `/auth/session` | Read current moderator/group context |
| `POST` | `/auth/logout` | Revoke moderator session |
| `GET` | `/members` | List members in the authenticated group |
| `POST` | `/members` | Add consented members to authenticated group |
| `POST` | `/webhook/messages` | Inbound SMS (`from` / `to` / `body`) |
| `POST` | `/webhook/inbound` | Alias of `/webhook/messages` |
| `GET` | `/moderation/queue` | Authenticated group's review queue |
| `GET` | `/messages/{id}` | Message detail + eligible recipients |
| `POST` | `/messages/{id}/approve` | `{ "recipient_ids": [...] }` then fan-out |
| `POST` | `/messages/{id}/reject` | Mark moderator_rejected |
| `GET` | `/` | Health |

## Workflow statuses

Inbound routing message:

`received` → `processing` → `awaiting_moderator` → `approved` → `delivering` → `delivered`

Partial fan-out success uses `partially_delivered`. Outbound copies use `sent`
when the provider accepts the send (not carrier delivery confirmation).

Failures: `processing_failed`, `moderator_rejected`, `delivery_failed`.

Per-recipient delivery receipts (`MessageDelivery`) are a near-term follow-up;
do not block the current moderator + SMS + fan-out slice on that model.

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
after message/auth-table changes. See [CONTRIBUTING.md](../CONTRIBUTING.md).

## Development moderator login

Set a random `AUTH_SECRET` (at least 32 characters). For local development,
`SMS_PROVIDER=logging` prints the six-digit challenge through the provider.
`AUTH_EXPOSE_DEVELOPMENT_CODE=true` may also include it in the challenge
response. Production forces response exposure off and should configure the
HTTP SMS provider.

Codes and session tokens are never stored directly: PostgreSQL stores HMAC
hashes, expirations, attempt counts, and revocation state. The browser receives
the session token only as an HttpOnly cookie and sends it automatically.

The auth and consent tables are init scripts. Existing local databases must be
recreated after pulling this schema:

```bash
docker compose -f docker-compose.dev.yml down -v
docker compose -f docker-compose.dev.yml up --build
```
