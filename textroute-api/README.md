# textroute-api

FastAPI service for TextRoute: inbound SMS webhooks, group creation, and (soon) intent-based routing with human moderation.

## Package layout

```
src/
  api/routes/     # Thin HTTP adapters
  services/       # Use-case orchestration; owns db.commit()
  core/           # *Manager (flush only), phone_normalize, MessageProcessor
  models/         # SQLAlchemy ORM
  schemas/api.py  # HTTP DTOs
  schemas/intent/ # Structured AI outputs
  domain/         # Intent types + routing maps
  ai/             # LLM / embedding helpers (future processor wiring)
  config/         # Env + YAML loaders
  db/             # Engine + session (get_db)
tests/            # Unit tests (mocked DB for inbound flow)
```

Entry point: `src.main:app`.

## Common endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/groups` | Create group + assign TextRoute number |
| `POST` | `/webhook/messages` | Inbound SMS (`from` / `to` / `body`) |
| `POST` | `/webhook/inbound` | Alias of `/webhook/messages` |
| `GET` | `/` | Health |

## Local commands

```bash
pip install -r requirements.txt
pip install -e ".[dev]"
pytest
uvicorn src.main:app --reload --port 6060
```

Docker Compose (from repo root) is the preferred full stack. See [CONTRIBUTING.md](../CONTRIBUTING.md).

## Product message flow

1. Member texts a TextRoute number.
2. API resolves line → group → member, persists the message.
3. `MessageProcessor` will classify intent / suggest recipients (stub today).
4. Moderator confirms recipients.
5. Outbound delivery goes through `MessagingService` (provider integration later).

Human-in-the-loop review is intentional: accountability and social safety over fully automated fan-out.
