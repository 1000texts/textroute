-- Machine-generated activity on a request: routing authorizations, per-recipient
-- delivery outcomes, and lifecycle transitions.
--
-- Deliberately not messages. Keeping `messages` to human communication is what
-- lets the moderator thread stay readable, and it gives the audit trail its own
-- queryable shape instead of leaving it stringified in processing_notes.

CREATE TABLE public.request_events (
    id bigserial PRIMARY KEY,

    request_id bigint NOT NULL
        REFERENCES public.requests(id),

    -- Set when the event concerns one specific message, which for `delivered`
    -- and `delivery_failed` is that recipient's fan-out copy.
    message_id uuid NULL
        REFERENCES public.messages(id),

    event_type varchar(32) NOT NULL,

    payload jsonb NOT NULL DEFAULT '{}'::jsonb,

    created_at timestamptz NOT NULL DEFAULT now(),

    -- A closed vocabulary: a seventh event should be a deliberate migration,
    -- the same bar the message roles are held to.
    --
    -- There is no 'partially_delivered'. Delivery is recorded per recipient, so
    -- a partial fan-out is a mix of 'delivered' and 'delivery_failed'; the
    -- aggregate stays on messages.workflow_status and is never stored twice.
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

CREATE INDEX idx_request_events_request_created
    ON public.request_events (request_id, created_at);

CREATE INDEX idx_request_events_message_id
    ON public.request_events (message_id);
