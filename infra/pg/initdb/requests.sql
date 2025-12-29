CREATE TABLE public.requests (
    id BIGSERIAL PRIMARY KEY,

    -- Who made the request
    requester_id BIGINT NULL
        REFERENCES public.members(id),

    -- Raw user input (never lose this)
    request_text TEXT NOT NULL,

    -- Intent classifier output
    request_type TEXT NOT NULL,
    -- examples:
    -- 'ServiceRequest'
    -- 'ItemBorrowRequest'
    -- 'AnnouncementRequest'
    -- 'GeneralRequest'

    -- Structured extraction (schema varies by request_type)
    extracted_filters JSONB NOT NULL,

    -- Optional: extracted short summary if present in schema
    summary TEXT NULL,

    -- Embedding of request_text or summary
    embedding VECTOR(1536) NULL,

    -- Traceability & evolution
    schema_version INT NOT NULL DEFAULT 1,
    model_name TEXT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Guardrails
    CONSTRAINT extracted_filters_is_object
        CHECK (jsonb_typeof(extracted_filters) = 'object')
);

ALTER TABLE public.requests ADD CONSTRAINT requests_requester_id_fkey FOREIGN KEY (requester_id) REFERENCES members(id)

-- Intent + time
CREATE INDEX idx_requests_type_created
ON public.requests (request_type, created_at DESC);

-- JSONB filtering (urgency, category, etc.)
CREATE INDEX idx_requests_filters_gin
ON public.requests
USING GIN (extracted_filters);

-- Vector search
CREATE INDEX idx_requests_embedding
ON public.requests
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
-- (Tune lists later.)


-- 🔍 Example queries (from your schemas)
-- High-urgency service requests
SELECT *
FROM public.requests
WHERE request_type = 'ServiceRequest'
AND extracted_filters->>'urgency' = 'high';

-- Borrow requests for tools > 7 days
SELECT *
FROM public.requests
WHERE request_type = 'ItemBorrowRequest'
AND (extracted_filters->>'duration_days')::int > 7
AND extracted_filters->>'item_category' = 'tools';
