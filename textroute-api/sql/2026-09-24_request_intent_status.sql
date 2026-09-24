-- Intent discovery is enrichment, not a delivery gate.
--
-- requests.intent_status says whether request_type has been committed.
-- pending and failed may be retried. ready means the analysis on that row
-- is usable. Existing rows that already have a request_type are ready;
-- the rest start pending so the sweep can discover them.
--
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
--     -f textroute-api/sql/2026-09-24_request_intent_status.sql

BEGIN;

ALTER TABLE public.requests
    ADD COLUMN IF NOT EXISTS intent_status text NOT NULL DEFAULT 'pending';

UPDATE public.requests
   SET intent_status = 'ready'
 WHERE request_type IS NOT NULL
   AND intent_status = 'pending';

ALTER TABLE public.requests
    DROP CONSTRAINT IF EXISTS requests_intent_status_check;

ALTER TABLE public.requests
    ADD CONSTRAINT requests_intent_status_check
        CHECK (intent_status IN ('pending', 'ready', 'failed'));

CREATE INDEX IF NOT EXISTS idx_requests_intent_discovery
    ON public.requests (intent_status)
    WHERE intent_status IN ('pending', 'failed');

COMMIT;
