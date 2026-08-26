# SMS simulator

Local Vite + React UI that posts Twilio-like payloads to the TextRoute API.

Used by `docker-compose.dev.yml` on port **5173**.

```bash
npm install
npm run dev
# posts to VITE_API_BASE_URL (default http://localhost:6060)
```

Webhook path: `POST /webhook/messages` (also `/webhook/inbound`).
