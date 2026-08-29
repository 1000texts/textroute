CREATE TABLE public.requests (
    id bigserial NOT NULL,

    group_id uuid NOT NULL
        REFERENCES public.groups(id),

    requester_id uuid NOT NULL
        REFERENCES public.members(id),

    -- Added after messages exists; see 08_messages.sql.
    original_message_id uuid NULL,

    status varchar(20) NOT NULL DEFAULT 'open',

    request_type text NULL,
    extracted_filters jsonb NOT NULL DEFAULT '{}'::jsonb,
    summary text NULL,
    -- How sure the analyzer was about request_type. Nullable rather than
    -- defaulted: no analysis and a genuinely unsure answer are different facts.
    confidence double precision NULL,
    -- IVFFLAT requires a fixed vector dimension. 1024 matches the configured
    -- Qwen3 embedding model; changing model means changing this and reindexing.
    embedding public.vector(1024) NULL,

    schema_version int4 NOT NULL DEFAULT 1,
    model_name text NULL,

    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz NULL,
    cancelled_at timestamptz NULL,
    -- The absolute ceiling on a request's life. Not the usual way one ends: see
    -- last_activity_at below.
    expires_at timestamptz NULL,
    -- When a message last entered this request. Maintained on message insert and
    -- stored rather than derived from max(messages.created_at), so the
    -- inactivity sweep reads one indexed column instead of aggregating messages.
    last_activity_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT requests_pkey
        PRIMARY KEY (id),

    CONSTRAINT requests_status_check
        CHECK (
            status IN (
                'open',
                'completed',
                'cancelled',
                'expired'
            )
        ),

    CONSTRAINT requests_extracted_filters_is_object
        CHECK (
            jsonb_typeof(extracted_filters) = 'object'
        ),

    CONSTRAINT requests_confidence_range
        CHECK (
            confidence IS NULL
            OR (confidence >= 0 AND confidence <= 1)
        )
);

CREATE INDEX idx_requests_group_id
    ON public.requests (group_id);

CREATE INDEX idx_requests_requester_id
    ON public.requests (requester_id);

CREATE INDEX idx_requests_status
    ON public.requests (status);

CREATE INDEX idx_requests_group_created
    ON public.requests (group_id, created_at DESC);

CREATE INDEX idx_requests_embedding
    ON public.requests
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX idx_requests_filters_gin
    ON public.requests
    USING gin (extracted_filters);

CREATE INDEX idx_requests_type_created
    ON public.requests (request_type, created_at DESC);

-- Serves the inactivity sweep, which only ever asks about open requests. Partial
-- so it stays small: closed requests are the overwhelming majority over time.
CREATE INDEX idx_requests_open_last_activity
    ON public.requests (last_activity_at)
    WHERE status = 'open';

-- One live request per person, not per group: several members may be waiting
-- on unrelated things at once, and a group-wide lock would make one member's
-- open request block everyone else's.
CREATE UNIQUE INDEX idx_requests_one_open_per_requester
    ON public.requests (group_id, requester_id)
    WHERE status = 'open';
