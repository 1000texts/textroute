CREATE TABLE public.members (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,

    phone_number varchar(16) NOT NULL,
    name varchar(100) NULL,

    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT members_phone_number_unique
        UNIQUE (phone_number)
);
