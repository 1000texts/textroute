# moderator-web

Vite + React UI for creating TextRoute groups and managing members.

Not part of the Docker Compose stack yet — run it locally while the API is up:

```bash
cp .env.example .env   # point at http://localhost:6060
npm install
npm run dev
```

Default Vite port is **5174** (see `vite.config.ts`).

## Routes

- `/` — create a group
- `/login` — verify an existing moderator using the group inbound number,
  moderator phone, and a six-digit code
- `/review` — protected review/approve/reject queue for the authenticated group
- `/add-member` — protected bulk member enrollment with consent attestation

Authentication uses an HttpOnly session cookie. API requests include
credentials automatically; no access token is stored in browser storage.

Local development uses `SMS_PROVIDER=logging`, which prints the challenge send.
It may also set `AUTH_EXPOSE_DEVELOPMENT_CODE=true` so the login page displays
the code returned by `/auth/challenge`. Production uses the configured HTTP
provider and never exposes the code in the response.
