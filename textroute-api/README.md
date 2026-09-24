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

### Requests, messages, and roles

**The request is the thing with a lifecycle. Messages are events within it.**

```text
Request  (open → completed | cancelled | expired)
  ├── Message 1  member asks for an axe          original_request
  ├── Message 2  copy sent to Bob                fanout_copy
  ├── Message 3  moderator asks "which day?"     moderator_clarification
  ├── Message 4  Bob says "I have one"           member_reply
  └── Message 5  requester says "got it, thanks" confirmation
```

`messages.request_id` expresses **parentage only**. Every message in a thread
carries it, including the original, so it cannot tell you what a message *is*.
Never infer a message's role from `request_id`, `parent_message_id`,
`direction`, or timestamps.

A message's meaning lives in two explicit columns, stamped once by whichever
path creates the row and never re-derived:

| `sender_role` | `kind` | `member_id` | `author_member_id` |
|---|---|---|---|
| `member` | `original_request` | sender | = `member_id` |
| `moderator` | `moderator_clarification` | recipient | the moderator |
| `member` | `member_reply` | sender | = `member_id` |
| `system` | `fanout_copy` | recipient | NULL |
| `member` | `confirmation` | sender | = `member_id` |

`member_id` keeps its established meaning — the member the row is *about* —
while `author_member_id` answers the different question of who wrote it, and is
NULL exactly when nobody did. These five shapes are enforced in two places:
`build_message_role()` in `src/domain/message_role.py`, and the
`messages_role_shape_check` constraint. Several code paths create messages, and
a wrong pairing would quietly corrupt the meaning of a thread.

`parent_message_id` remains the message graph (a star: replies and fan-out
copies point at the original). It is now redundant for threading, which
`request_id` owns.

The inbound path makes three separate decisions rather than one:

1. **Which request does this belong to?** — the sender's own open request,
   plus every open request `find_open_for_participant` finds via a fan-out
   copy. One candidate is a reply. None is a new request. Two or more are
   weighed by embedding similarity; a close call asks the sender to reply
   with a letter.
2. **What is this message?** — `determine_inbound_kind`, at the boundary, then
   stamped into `kind`.
3. **How should an `original_request` be routed?** — `groups.routing_policy`,
   which asks `is_routable(kind)` and so can never broadcast a reply.

A request's lifecycle now bounds reply collection, replacing the old two-hour
timing window: once a request is completed, cancelled, or expired, the next
message from those members starts a new one.

#### How an open request ends

Two bounds, both closing it as `expired`, both swept by
`RequestService.sweep_expired`:

- **Inactivity** (`REQUEST_INACTIVITY_AFTER_HOURS`, default 2) — the normal
  ending, measured from `requests.last_activity_at`. A conversation that has
  gone quiet is over.
- **Maximum lifetime** (`REQUEST_EXPIRES_AFTER_HOURS`, default 72) — the ceiling,
  stamped into `expires_at` at creation, for a request that keeps seeing
  activity yet never resolves.

They share a status because they mean the same thing to a moderator: closed
without resolution. The `expired` event's payload carries `reason`
(`inactivity` or `maximum_lifetime`) along with both timestamps it was judged
against, which keeps the status vocabulary at four values and the event
vocabulary at six.

`last_activity_at` is stored, not derived from `max(messages.created_at)`, so
the sweep is one indexed read. It is maintained inside
`MessageManager.create_inbound` / `create_outbound` because those are the only
way a row enters a request, which makes the invariant true by construction
rather than dependent on every service remembering to bump it.

**The sweep must be scheduled to have any effect.** Nothing in the request path
closes a request on a timer; see `scripts/sweep_requests.py` and the scheduled
jobs section of `DEPLOY.md`. Unscheduled, a stale open request keeps absorbing
its members' later messages as replies — which looks like a classification bug
and is not one. `determine_inbound_kind` is correct; it was handed an open
request that should have closed hours earlier.

**Deliberately narrow rules (change only on purpose):**

- `confirmation` is assigned only when the requester sends the inbound message
  accompanying explicit request resolution. Other inbound messages remain
  `member_reply` regardless of their natural-language semantics. Do not add
  keyword detection for "thanks" or "got one" — that puts semantic inference
  back at the boundary this design just removed it from.
- **`member_reply` bypasses moderation as a slice-level product policy**, not
  because it belongs to a request. A future reply-intent analyzer may find a new
  request inside one; "I have one. Also, anyone have a pressure washer?" is both,
  and is handled today only as a reply.

### request_events

Machine-generated activity — `authorized`, `delivered`, `delivery_failed`,
`completed`, `cancelled`, `expired` — kept out of `messages` so that table stays
human communication and the moderator thread stays readable.

`delivered` and `delivery_failed` are recorded **per recipient**, each pointing
at that recipient's fan-out copy. There is deliberately no
`partially_delivered` event: a partial fan-out is a mix of the two, and the
aggregate lives on `messages.workflow_status` rather than being stored in a
second place where it could drift.

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
| `POST` | `/webhook/messages` | Inbound SMS (`from` / `to` / `body`); requires `X-Webhook-Secret` |
| `POST` | `/webhook/inbound` | Alias of `/webhook/messages` |
| `GET` | `/webhook/conversation` | One handset's thread: `?from=<member>&to=<group>`; requires `X-Webhook-Secret` |
| `GET` | `/moderation/queue` | Authenticated group's review queue (source of truth for the needs-review count) |
| `GET` | `/messages` | All inbound messages for the group, any status (max 100) |
| `GET` | `/messages/{id}` | Message detail + eligible recipients |
| `POST` | `/messages/{id}/approve` | `{ "recipient_ids": [...] }` then fan-out |
| `POST` | `/messages/{id}/reject` | Mark moderator_rejected |
| `GET` | `/requests` | Requests for the group; `?status=open` to filter |
| `GET` | `/requests/{id}` | Request + full thread + audit trail |
| `POST` | `/requests/{id}/messages` | `{ "body": "..." }` — moderator speaks into the thread |
| `POST` | `/requests/{id}/complete` | Requester got what they needed |
| `POST` | `/requests/{id}/cancel` | Request withdrawn |
| `GET` | `/` | Health |

## Reading one handset's conversation

`GET /webhook/conversation` exists for the SMS simulator, which stands in for a
real phone in development. It is a read, but it lives under `/webhook` because
the simulator's only credential is the webhook shared secret, and the production
nginx vhost injects that secret for `/api/webhook/` and deliberately nothing
else. Putting the route anywhere else would mean widening that scope.

The conversation is `messages` filtered by `group_id` and `member_id`, which is
sufficient because `member_id` is the member a row is *about*: the sender on
inbound, the recipient on outbound. Nothing filters on `kind` — a fan-out copy,
a moderator clarification and a confirmation all reach the handset, so all of
them are returned. Which of them mattered is the request's concern, not the
phone's.

`body` is returned verbatim, and there is no accompanying sender field. There
does not need to be: an outbound message already names its sender, because that
is part of the SMS (see [Who an outbound SMS says it is from](#who-an-outbound-sms-says-it-is-from)).
The simulator's job is to show what a real handset would, so it decorates
nothing.

Paging uses a `(created_at, id)` keyset cursor, both halves or neither:

```
?after_created_at=2026-08-29T12:00:00Z&after_id=<uuid>
```

`created_at` alone is not a continuation point. A fan-out writes its copies in
one transaction and `func.now()` is transaction time, so the siblings share a
timestamp exactly and `created_at > cursor` would step over all but one of them
permanently. `scripts/verify_conversation_cursor.py` demonstrates this against a
real database; on a four-row conversation it reports three rows that a
timestamp-only cursor would strand.

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

Per-recipient outcomes now live in `request_events` (`delivered` /
`delivery_failed`, one per recipient). A `MessageDelivery` model for carrier
receipts remains a possible follow-up.

## Request analysis

```
RequestAnalyzer → src/ai (LangChain + Ollama) → requests.{request_type,
                                                summary, extracted_filters,
                                                embedding, model_name}
```

Off by default (`REQUEST_ANALYSIS_ENABLED=false`) so a checkout with no Ollama
running still handles inbound SMS: the keyword classifier in `MessageProcessor`
supplies the fallback. A model failure is logged and downgraded, never raised —
the request is the durable object, and its analysis can be recomputed.

`requests.model_name` is NULL for the fallback, which is how you tell a real
analysis from a degraded one.

The embedding must be 1024-dimensional to match the column and its `ivfflat`
index; a wrong-width vector is dropped with an error rather than stored.
Changing `OLLAMA_EMBEDDING_MODEL` means a migration, not just an env var.

## Outbound SMS

```
MessagingService → SmsProvider (logging | http)
```

Set `SMS_PROVIDER=logging` (default) or `SMS_PROVIDER=http` with `SMS_PROVIDER_URL`.

### Who an outbound SMS says it is from

A member who receives a routed message sees only the group's TextRoute number.
Nothing else in an SMS identifies the person asking, so the sender is part of the
text:

```
Naruto: Can anyone watch my dog this Sunday?
Brother Mecham (Moderator): Which day works for you?
```

`src/domain/outbound_text.py` composes this and `MessagingService.send_message`
applies it — once, in the one place every outbound message passes through, so the
string handed to the provider and the one stored in `messages.body` are the same.
Anything else would leave the record claiming something other than what was sent.

Three consequences worth knowing:

- **Inbound is never touched.** What a member wrote is what arrived. Only the two
  outbound kinds that carry someone's words get a prefix.
- **The name is group-scoped.** It comes from `member_profiles.display_name`,
  falling back to `members.name`, because the same person is `Brother Mecham` in
  one group and `shasta` in another. The moderator UI resolves names the same
  way, so a thread and the SMS it produced agree.
- **A `fanout_copy` is credited to the author it copies.** The copy itself must
  have no `author_member_id` — the system generated it — so `RoutingService`
  reads the name off the message being fanned out and passes it explicitly. On a
  recipient's handset the copy therefore reads as the person who asked, not as
  nobody.

`(Moderator)` is derived from `kind`, so no particular person is special-cased,
and a member with no name on record sends an unprefixed body rather than a bare
`": "`. Note that the prefix consumes characters from the 160-character SMS
segment; nothing truncates today.

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
