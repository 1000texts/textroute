# TextRoute

Route group messages to the people they are relevant to, using plain text only. No apps, accounts, or special commands.

AI infers intent and context; a human moderator still decides who receives the message.

## Layout

```
.
├── textroute-api/          # FastAPI app
│   ├── src/api/            # HTTP routes
│   ├── src/services/       # inbound flow and use cases
│   ├── src/ai/             # intent, extraction, embeddings
│   ├── src/domain/         # intent routing rules
│   ├── src/schemas/        # Pydantic models
│   ├── src/db/             # SQLAlchemy
│   ├── src/config/         # YAML + env
│   └── src/workers/        # offline jobs (faction graph, later)
├── docs/mkdocs/            # documentation site
├── infra/                  # nginx, postgres, scripts
├── tools/sms-simulator/    # local SMS UI (dev only)
├── docker-compose.dev.yml
└── docker-compose.prod.yml
```

## Run locally

```bash
docker compose -f docker-compose.dev.yml up --build
```

- API: http://localhost:6060
- SMS simulator: http://localhost:5173
- Docs: http://localhost:8000

## More

- Message flow: [textroute-api/README.md](textroute-api/README.md)
- Docs source: [docs/mkdocs/](docs/mkdocs/)
