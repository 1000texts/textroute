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
    -- IVFFLAT requires a fixed vector dimension.
    embedding public.vector(1536) NULL,

    schema_version int4 NOT NULL DEFAULT 1,
    model_name text NULL,

    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz NULL,
    cancelled_at timestamptz NULL,
    expires_at timestamptz NULL,

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

CREATE UNIQUE INDEX idx_requests_one_active_per_group
    ON public.requests (group_id)
    WHERE status = 'open';
