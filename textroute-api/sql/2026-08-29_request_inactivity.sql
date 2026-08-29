-- Requests gain a durable last_activity_at, so inactivity can close them.
--
-- Until now the only closing mechanism was the 72-hour expires_at, which made a
-- request that nobody answered keep capturing its members' unrelated messages as
-- replies for three days. Inactivity becomes the normal closure; expires_at stays
-- as the absolute ceiling. Both still resolve to status 'expired', so no status
-- or event vocabulary changes and no check constraint is touched.
--
-- Safe to run against a live database: the column is added with a default, then
-- backfilled from the real message history before anything reads it.
--
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
--     -f textroute-api/sql/2026-08-29_request_inactivity.sql

BEGIN;

ALTER TABLE public.requests
    ADD COLUMN IF NOT EXISTS last_activity_at timestamptz NOT NULL DEFAULT now();

-- Backfill from the message history rather than leaving the now() default in
-- place. Without this every open request would carry the migration's own
-- timestamp: an abandoned three-day-old request would look freshly active and
-- survive another two hours, while the genuinely active ones would be
-- indistinguishable from it.
--
-- COALESCE covers a request whose messages are all gone, and requests.created_at
-- is the correct floor there: the request existed from that moment.
UPDATE public.requests r
   SET last_activity_at = COALESCE(
           (SELECT max(m.created_at)
              FROM public.messages m
             WHERE m.request_id = r.id),
           r.created_at
       );

-- Serves the sweep, which only ever asks about open requests. Partial so it
-- stays small as closed requests accumulate.
CREATE INDEX IF NOT EXISTS idx_requests_open_last_activity
    ON public.requests (last_activity_at)
    WHERE status = 'open';

COMMIT;

-- After this runs, requests that have been quiet longer than
-- REQUEST_INACTIVITY_AFTER are immediately eligible for closure. That is the
-- intent, but it means the first sweep may close a backlog in one pass; expect a
-- burst of 'expired' events with reason 'inactivity'.
