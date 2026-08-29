-- Requests become the parent workflow object, and every message carries an
-- explicit sender_role + kind instead of having its meaning inferred.
--
-- Safe to run against a database with live messages in it. Every constraint is
-- added NOT VALID and validated only after the backfill, so the migration
-- cannot fail halfway and leave the table unusable.
--
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
--     -f textroute-api/sql/2026-08-28_requests_as_lifecycle.sql

BEGIN;

-- ---------------------------------------------------------------------------
-- messages: the two explicit axes
-- ---------------------------------------------------------------------------

-- 'moderator_clarification' is 23 characters; the column was sized for 'reply'.
ALTER TABLE public.messages
    DROP CONSTRAINT IF EXISTS messages_kind_check;

ALTER TABLE public.messages
    ALTER COLUMN kind TYPE varchar(32);

ALTER TABLE public.messages
    ADD COLUMN IF NOT EXISTS sender_role varchar(16) NULL;

ALTER TABLE public.messages
    ADD COLUMN IF NOT EXISTS author_member_id uuid NULL
        REFERENCES public.members(id);

-- Backfill. Every outbound row that exists today is a fan-out copy: the only
-- code path that has ever written one is RoutingService via MessagingService.
UPDATE public.messages
   SET sender_role = CASE direction
                         WHEN 'inbound' THEN 'member'
                         ELSE 'system'
                     END,
       author_member_id = CASE direction
                              WHEN 'inbound' THEN member_id
                              ELSE NULL
                          END
 WHERE sender_role IS NULL;

UPDATE public.messages
   SET kind = CASE
                  WHEN kind = 'new_request' THEN 'original_request'
                  WHEN kind = 'reply' THEN 'member_reply'
                  ELSE kind
              END
 WHERE kind IN ('new_request', 'reply');

-- Outbound copies had no kind at all until now.
UPDATE public.messages
   SET kind = 'fanout_copy'
 WHERE direction = 'outbound'
   AND kind IS NULL;

-- An inbound row can still legitimately have kind NULL: the message is
-- persisted before the kind is decided, and a processing failure leaves it
-- that way. The shape constraint below tolerates it.

ALTER TABLE public.messages
    ADD CONSTRAINT messages_sender_role_check
        CHECK (sender_role IS NULL OR sender_role IN (
            'member',
            'moderator',
            'system'
        )) NOT VALID;

ALTER TABLE public.messages
    ADD CONSTRAINT messages_kind_check
        CHECK (kind IS NULL OR kind IN (
            'original_request',
            'moderator_clarification',
            'member_reply',
            'fanout_copy',
            'confirmation'
        )) NOT VALID;

ALTER TABLE public.messages
    ADD CONSTRAINT messages_role_shape_check
        CHECK (
            kind IS NULL
            OR (
                kind IN ('original_request', 'member_reply', 'confirmation')
                AND sender_role = 'member'
                AND author_member_id IS NOT NULL
                AND author_member_id = member_id
            )
            OR (
                kind = 'moderator_clarification'
                AND sender_role = 'moderator'
                AND author_member_id IS NOT NULL
            )
            OR (
                kind = 'fanout_copy'
                AND sender_role = 'system'
                AND author_member_id IS NULL
            )
        ) NOT VALID;

ALTER TABLE public.messages VALIDATE CONSTRAINT messages_sender_role_check;
ALTER TABLE public.messages VALIDATE CONSTRAINT messages_kind_check;
ALTER TABLE public.messages VALIDATE CONSTRAINT messages_role_shape_check;

CREATE INDEX IF NOT EXISTS idx_messages_fanout_recipient
    ON public.messages(member_id, created_at DESC)
    WHERE kind = 'fanout_copy';

-- ---------------------------------------------------------------------------
-- requests: analyzer confidence, one open request per person, and a usable
-- embedding width
-- ---------------------------------------------------------------------------

-- The analyzer already computed a confidence for every request and had nowhere
-- to put it. Analysis describes the request, so it belongs here rather than
-- being read sideways off the original message.
ALTER TABLE public.requests
    ADD COLUMN IF NOT EXISTS confidence double precision NULL;

ALTER TABLE public.requests
    DROP CONSTRAINT IF EXISTS requests_confidence_range;

ALTER TABLE public.requests
    ADD CONSTRAINT requests_confidence_range
        CHECK (
            confidence IS NULL
            OR (confidence >= 0 AND confidence <= 1)
        );

DROP INDEX IF EXISTS public.idx_requests_one_active_per_group;

CREATE UNIQUE INDEX IF NOT EXISTS idx_requests_one_open_per_requester
    ON public.requests (group_id, requester_id)
    WHERE status = 'open';

-- The column was sized 1536 (an OpenAI width) but the configured model emits
-- 1024, so every insert would have been rejected. No data is lost: nothing has
-- ever written an embedding.
DROP INDEX IF EXISTS public.idx_requests_embedding;

ALTER TABLE public.requests
    ALTER COLUMN embedding TYPE public.vector(1024) USING NULL;

CREATE INDEX idx_requests_embedding
    ON public.requests
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ---------------------------------------------------------------------------
-- request_events
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.request_events (
    id bigserial PRIMARY KEY,

    request_id bigint NOT NULL
        REFERENCES public.requests(id),

    message_id uuid NULL
        REFERENCES public.messages(id),

    event_type varchar(32) NOT NULL,

    payload jsonb NOT NULL DEFAULT '{}'::jsonb,

    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT request_events_event_type_check
        CHECK (event_type IN (
            'authorized',
            'delivered',
            'delivery_failed',
            'completed',
            'cancelled',
            'expired'
        )),

    CONSTRAINT request_events_payload_is_object
        CHECK (jsonb_typeof(payload) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_request_events_request_created
    ON public.request_events (request_id, created_at);

CREATE INDEX IF NOT EXISTS idx_request_events_message_id
    ON public.request_events (message_id);

COMMIT;
