# SMS simulator

Local Vite + React UI that posts Twilio-like payloads to the TextRoute API.

Used by `docker-compose.dev.yml` on port **5173**.

```bash
npm install
npm run dev
# posts to VITE_API_BASE_URL (default http://localhost:6060)
```

Webhook path: `POST /webhook/messages` (also `/webhook/inbound`).

## The conversation is the server's, not the browser's

The phone screen shows `GET /webhook/conversation?from=<sender>&to=<group>`, so
what appears on it is what is actually in the `messages` table: the member's own
texts, plus every outbound row addressed to them — fan-out copies, moderator
clarifications, confirmations. Earlier versions kept an invented history in
browser memory and typed the webhook's JSON response into a bubble, which meant
the routing behavior worth testing never showed up on the handset.

Bubbles are drawn from `body` and nothing else. Incoming messages already name
their sender:

```
                                       Can anyone watch my dog this Sunday?

  Naruto: Can anyone watch my dog this Sunday?
  Brother Mecham (Moderator): Which day works for you?
```

The name is in the text because TextRoute puts it there when it sends the SMS —
a recipient sees only the group's number and would otherwise have no idea who is
asking. It is not a simulator affordance, and the simulator adds no label of its
own; see [Who an outbound SMS says it is from](../../textroute-api/README.md#who-an-outbound-sms-says-it-is-from).

The right-hand side has no name: those are this handset's own words, exactly as
they were received. The asymmetry above is the point — it is what a real phone
shows, so it is what you are testing.

Consequences worth knowing:

- **Switching From or To reloads.** From selects the member and To selects the
  group, so either change is a different conversation. It reloads on a
  *committed* number (blur, Enter, or picking from the dropdown), not per
  keystroke.
- **New messages arrive within about three seconds**, by polling with a
  `(created_at, id)` cursor. A reply can wait on a moderator approving it, so
  there is no request/response pairing to animate — hence no typing indicator.
  Polling pauses while the tab is hidden.
- **Sending shows an optimistic bubble, then reloads from the server.** The
  reload is authoritative; the client never tries to match its own bubble to a
  database row.
- **History is not per-browser.** Anyone pointing the simulator at the same
  number pair sees the same thread, and a page reload no longer clears it.
  Contact names are still local to the browser.

Both requests need the webhook secret. In development that is
`VITE_WEBHOOK_SECRET` in `.env.local`; in production nginx injects it
server-side for `/api/webhook/` so it never reaches the public bundle.
