CREATE TABLE public.messages (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,

    group_id uuid NOT NULL
        REFERENCES public.groups(id),

    member_id uuid NULL
        REFERENCES public.members(id),

    direction varchar(20) NOT NULL,

    from_phone_number varchar(16) NOT NULL,
    to_phone_number varchar(16) NOT NULL,

    body text NOT NULL,

    provider_message_id varchar(64) NULL,

    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT messages_direction_check
        CHECK (direction IN ('inbound', 'outbound')),

    CONSTRAINT messages_provider_message_id_unique
        UNIQUE (provider_message_id)
);

CREATE INDEX idx_messages_group_id
    ON public.messages(group_id);

CREATE INDEX idx_messages_member_id
    ON public.messages(member_id);

CREATE INDEX idx_messages_group_created
    ON public.messages(group_id, created_at DESC);
