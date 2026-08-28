# textroute-api

FastAPI service for TextRoute: inbound SMS webhooks, group creation, heuristic
intent suggestions, moderator approval, and outbound fan-out.

## Package layout

```
src/
  api/
    routes/
      public/     # Unauthenticated onboarding
      moderator/  # Authenticated moderator web app
      webhooks/   # Provider callbacks
      health.py
  services/       # Use-case orchestration; owns db.commit()
  core/
    managers/     # Focused DB operations; flush only, never commit
    providers/    # External integration contracts and adapters
    processors/   # Pure analysis and recommendation logic
    phone_normalize.py  # E.164 identity keys
  models/         # SQLAlchemy ORM
  schemas/api.py  # HTTP DTOs
  schemas/intent/ # Structured AI outputs (future richer extraction)
  domain/         # Intent types, message kind, workflow statuses, routing policy
  ai/             # LLM helpers (optional; processor v1 is heuristic)
  config/         # Env + YAML loaders
  db/             # Engine + session (get_db)
tests/
```

Entry point: `src.main:app`.

## Transaction boundary

The transaction boundary is intentionally one layer above persistence:

```text
service use case
  → one or more manager operations
      → db.add(...) / db.flush()
  → service db.commit() or db.rollback()
```

Managers flush only. `flush()` sends pending SQL to the current transaction
and makes generated values available; it does not make changes durable.
Services decide the business transaction, including any deliberate checkpoint
commits required by a workflow such as durable inbound-message persistence.
Routes may defensively call `rollback()` while mapping an exception to HTTP,
but do not commit or split the service transaction.

## Vertical slice flow

```
SMS webhook
  → persist Message (received)
  → determine inbound kind
      ├── REPLY       → persist linked, stop (not re-routed for now)
      └── NEW_REQUEST → MessageProcessor → intent + suggested recipients
            → group routing policy
                ├── moderator_required → awaiting_moderator → approve/reject
                └── auto_group         → auto_authorized
            → RoutingService.fan_out → SmsProvider → original body unchanged
  → recipient reply → persist (linked via parent_message_id)
```

`MessageProcessor` only recommends. It does not send SMS or commit.
`RoutingService` is the single fan-out path shared by both routes above.

## Requests and messages

`messages` stores the communication; `requests` stores the workflow object
and its AI-derived interpretation. The original text is not duplicated:

```text
requests.original_message_id → messages.id
messages.request_id           → requests.id
messages.parent_message_id    → messages.id
```

`request_id` answers which request a message belongs to. `parent_message_id`
answers which specific message it relates to. The request schema currently
allows one `open` request per group, enforced by a partial unique index.

### Routing philosophy (new requests)

A **new routing request** treats the group as the safe/default audience:

```
new topic → processor suggests all other active members
         → moderator reviews (may narrow/expand)   [moderator_required]
           or the group policy authorizes routing  [auto_group]
         → fan-out original body
```

Suggestions are recommendations, not irreversible decisions. Member profiles
and past successful responses are future *signals* for smarter narrowing —
when the system is not confident, the community is the search engine.
TextRoute optimizes **who gets asked**, not who it assumes can help.

Role does not fork the inbound path: moderators and members who text the group
line both need an active membership and share the same pipeline. Moderator
authority is the web UI session, not a separate SMS handler.

### Group routing policy

`groups.routing_policy` decides **how a new request is routed** — not merely
whether a moderator is involved:

| Policy | Behavior |
|--------|----------|
| `moderator_required` (default) | Queue at `awaiting_moderator` for human review |
| `auto_group` | Policy authorizes routing to the suggested audience; fan out immediately |
| `auto_matched` | Reserved. Accepted by the DB constraint, not implemented — falls back to moderation |

Unknown or unimplemented values fail **safe**: `requires_moderation()` returns
True, so TextRoute never fails open into an unreviewed broadcast.

The policy is consulted for `NEW_REQUEST` only. Replies are never policy-routed,
so `auto_group` cannot broadcast someone's "I have one." to the whole group.

Read/change it at `GET`/`PATCH /group/settings` (moderator session required).

#### Approval is not authorization

A **moderator approves**; a **group policy authorizes**. Different actors, so
they never share a status:

```
awaiting_moderator → approved        → delivering → delivered / ...
received           → auto_authorized → delivering → delivered / ...
```

Both are in `PRE_DELIVERY_STATUSES` and converge at `RoutingService.fan_out`,
but only `approved` implies a human saw the message. `messages.routed_recipient_ids`
is named for what it holds under either route; pair it with `workflow_status` to
tell which happened. `messages.routing_policy` snapshots the policy in force at
handling time, so changing a group's policy never rewrites history.

### Message graph vs conversation

`parent_message_id` is a **message relationship** edge (star: replies and
outbound fan-out copies point at the original routed inbound). It is **not**
a complete Conversation/Thread model — do not introduce a `conversations`
table until product needs (active topics, who responded, resolve/summarize)
justify it. Get the message graph right first.

> **`parent_message_id` represents message relationship, not moderation state.**
> A non-null parent does not by itself mean the message is exempt from
> moderation. Finding a related original request and deciding
> moderation/routing policy are separate concerns.

The inbound path therefore makes three separate decisions rather than one:

1. **Is there an original request candidate?**
   (`find_original_request_candidate_for_member`) — sets the relationship only.
2. **What kind of inbound message is this?** (`determine_inbound_kind` →
   `messages.kind`) — selects the workflow.
3. **How should a `NEW_REQUEST` be routed?** (`groups.routing_policy`) — never
   consulted for replies.

The first step is named for what the lookup *discovers* — which request reached
this member recently — rather than for what the new message might turn out to
be. It returns the original request itself, not the per-recipient fan-out copy
that evidenced it, so replies parent directly to the request.

**Temporary scaffolding (replace before intelligent routing):**

- Candidate detection ≈ “member received this request within
  `InboundMessageService.ORIGINAL_REQUEST_CANDIDATE_WINDOW_HOURS` (2h)”. A
  candidate is a signal, not proof: time alone still false-positives, so the
  window stays short.
- **`REPLY` currently bypasses moderation as a slice-level behavior, not because
  `parent_message_id` is present.** Future reply analysis may classify a message
  as `REPLY`, `NEW_REQUEST`, or `REPLY_WITH_NEW_REQUEST` — "I have one. Also,
  anyone have a pressure washer?" is both, and is handled today only as the
  former. Linked replies stay at `possible_reply_persisted_unprocessed`.

Next evolution: replace `determine_inbound_kind` with a real relationship
resolver, then reply-intent analysis — not a giant schema rewrite.

## Common endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/groups` | Create group + assign TextRoute number |
| `POST` | `/auth/challenge` | Request moderator confirmation code |
| `POST` | `/auth/verify` | Verify code and create HttpOnly session |
| `GET` | `/auth/session` | Read current moderator/group context |
| `POST` | `/auth/logout` | Revoke moderator session |
| `GET` | `/group/settings` | Read group settings incl. `routing_policy` |
| `PATCH` | `/group/settings` | `{ "routing_policy": "auto_group" }` |
| `GET` | `/members` | List members in the authenticated group |
| `POST` | `/members` | Add consented members to authenticated group |
| `POST` | `/webhook/messages` | Inbound SMS (`from` / `to` / `body`) |
| `POST` | `/webhook/inbound` | Alias of `/webhook/messages` |
| `GET` | `/moderation/queue` | Authenticated group's review queue (source of truth for the needs-review count) |
| `GET` | `/messages` | All inbound messages for the group, any status (max 100) |
| `GET` | `/messages/{id}` | Message detail + eligible recipients |
| `POST` | `/messages/{id}/approve` | `{ "recipient_ids": [...] }` then fan-out |
| `POST` | `/messages/{id}/reject` | Mark moderator_rejected |
| `GET` | `/` | Health |

## Workflow statuses

Inbound routing message, moderated:

`received` → `processing` → `awaiting_moderator` → `approved` → `delivering` → `delivered`

Inbound routing message, policy-authorized (`auto_group`):

`received` → `processing` → `auto_authorized` → `delivering` → `delivered`

`approved` and `auto_authorized` are both transitional and both clear a message
for delivery, but only `approved` means a human reviewed it.

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

Sessions use `created_at`, `expires_at`, and optional `revoked_at`. Auth requires
`revoked_at IS NULL` and `expires_at > now()` (plus an active moderator membership).

### CSRF (cookie sessions)

Moderator auth is cookie-based, so browsers attach the session cookie on
credentialed requests. State-changing routes include:

- `POST /messages/{id}/approve`
- `POST /messages/{id}/reject`
- `POST /members`
- `POST /auth/logout`

**Current decision:** rely on `SameSite=Lax` plus a **same-site** deployment
topology (`MODERATOR_WEB_ORIGIN` and the API share a site, e.g. local `localhost`
ports or `app.example.com` / `api.example.com`). Lax blocks cross-site POSTs from
foreign origins from sending the cookie, which is the primary CSRF mitigation
for this vertical slice.

This is intentional, not accidental. If the UI and API become cross-site
(`SameSite=None; Secure`), add an explicit CSRF defense (synchronizer token or
equivalent) before shipping — do not only flip the cookie attribute.

CORS is locked to `MODERATOR_WEB_ORIGIN` with `allow_credentials=True`; that does
not replace SameSite/CSRF analysis.

The auth and consent tables are init scripts. Existing local databases must be
recreated after pulling this schema:

```bash
docker compose -f docker-compose.dev.yml down -v
docker compose -f docker-compose.dev.yml up --build
```
