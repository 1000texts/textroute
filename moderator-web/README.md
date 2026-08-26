# moderator-web

Vite + React UI for creating TextRoute groups (`POST /groups`).

Not part of the Docker Compose stack yet — run it locally while the API is up:

```bash
cp .env.example .env   # point at http://localhost:6060
npm install
npm run dev
```

Default Vite port is **5174** (see `vite.config.ts`).
