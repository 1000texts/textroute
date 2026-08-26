CREATE TABLE public.messages (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,

    group_id uuid NOT NULL
        REFERENCES public.groups(id),

    member_id uuid NULL
        REFERENCES public.members(id),

    -- Link replies / fan-out copies back to the originating inbound message
    parent_message_id uuid NULL
        REFERENCES public.messages(id),

    direction varchar(20) NOT NULL,

    from_phone_number varchar(16) NOT NULL,
    to_phone_number varchar(16) NOT NULL,

    body text NOT NULL,

    provider_message_id varchar(64) NULL,

    -- Explicit workflow lifecycle for inbound routing messages
    workflow_status varchar(32) NOT NULL DEFAULT 'received',

    intent varchar(64) NULL,
    constraints jsonb NULL,
    confidence double precision NULL,
    suggested_recipient_ids uuid[] NULL,
    approved_recipient_ids uuid[] NULL,
    processing_notes text NULL,

    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT messages_direction_check
        CHECK (direction IN ('inbound', 'outbound')),

    CONSTRAINT messages_workflow_status_check
        CHECK (workflow_status IN (
            'received',
            'processing',
            'awaiting_moderator',
            'approved',
            'delivering',
            'sent',
            'delivered',
            'partially_delivered',
            'processing_failed',
            'moderator_rejected',
            'delivery_failed'
        )),

    CONSTRAINT messages_provider_message_id_unique
        UNIQUE (provider_message_id)
);

CREATE INDEX idx_messages_group_id
    ON public.messages(group_id);

CREATE INDEX idx_messages_member_id
    ON public.messages(member_id);

CREATE INDEX idx_messages_group_created
    ON public.messages(group_id, created_at DESC);

CREATE INDEX idx_messages_workflow_status
    ON public.messages(workflow_status);

CREATE INDEX idx_messages_parent_message_id
    ON public.messages(parent_message_id);
