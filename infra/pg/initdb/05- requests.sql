CREATE TABLE public.requests (
    id BIGSERIAL PRIMARY KEY,
    requester_id UUID NULL REFERENCES public.members(member_id) NOT NULL,    -- Who made the request
    request_text TEXT NOT NULL, -- Raw user input (never lose this)
    request_type TEXT NOT NULL, -- Intent classifier output 'ServiceRequest', 'ItemBorrowRequest', etc.
    extracted_filters JSONB NOT NULL, -- Structured extraction (schema varies by request_type)
    summary TEXT NULL, -- Optional: extracted short summary if present in schema
    embedding VECTOR(1536) NULL, -- Embedding of request_text or summary
    schema_version INT NOT NULL DEFAULT 1,-- Traceability & evolution
    model_name TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT extracted_filters_is_object
        CHECK (jsonb_typeof(extracted_filters) = 'object') -- Guardrails

);


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

-- Add an index on requester_id
CREATE INDEX idx_requests_requester_id
ON public.requests (requester_id);

