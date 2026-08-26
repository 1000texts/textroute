# TextRoute

Route group messages to the people they are relevant to, using plain text only. No apps, accounts, or special commands.

AI infers intent and context; a human moderator still decides who receives the message.

**License:** [MIT](LICENSE) · **Contributing:** [CONTRIBUTING.md](CONTRIBUTING.md) · **Security:** [SECURITY.md](SECURITY.md)

## Layout

```
.
├── textroute-api/              # FastAPI service
│   ├── src/api/routes/         # HTTP endpoints
│   ├── src/services/           # orchestration (owns commits)
│   ├── src/core/               # managers, E.164, MessageProcessor
│   ├── src/models/             # SQLAlchemy ORM
│   ├── src/schemas/            # api DTOs + intent schemas
│   ├── src/domain/ + src/ai/   # intent stack (wired via processor later)
│   └── tests/
├── moderator-web/              # Vite React create-group UI (local)
├── tools/sms-simulator/        # local SMS webhook UI (dev)
├── docs/mkdocs/                # product documentation site
├── infra/
│   ├── postgres/initdb/        # numbered SQL applied on first Postgres boot
│   ├── nginx/
│   └── scripts/                # dev-up / dev-down helpers
├── docker-compose.dev.yml
└── docker-compose.prod.yml
```

## Run locally

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up --build
# or: ./infra/scripts/dev-up.sh
```

| Service | URL |
|---------|-----|
| API | http://localhost:6060 |
| SMS simulator | http://localhost:5173 |
| Docs | http://localhost:8000 |
| Postgres | `localhost:5432` |

Schema scripts in `infra/postgres/initdb/` run only when the Postgres volume is first created. Reset with `docker compose -f docker-compose.dev.yml down -v`.

## Develop the API

```bash
cd textroute-api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev]"
pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for layering rules and PR expectations.

## More

- Product message flow: [textroute-api/README.md](textroute-api/README.md)
- Docs source: [docs/mkdocs/](docs/mkdocs/)
