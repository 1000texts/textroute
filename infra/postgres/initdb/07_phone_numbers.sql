CREATE TABLE public.phone_numbers (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,

    phone_number varchar(16) NOT NULL,

    status varchar(20) NOT NULL DEFAULT 'available',

    provider varchar(50) NULL,

    group_id uuid NULL
        REFERENCES public.groups(id),

    assigned_at timestamptz NULL,
    released_at timestamptz NULL,

    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT phone_numbers_phone_unique
        UNIQUE (phone_number),

    CONSTRAINT phone_numbers_status_check
        CHECK (status IN (
            'available',
            'assigned',
            'released'
        ))
);

-- Dev seed pool (E.164). Replace with real Twilio numbers in production.
INSERT INTO public.phone_numbers (phone_number, status, provider)
VALUES
    ('+15550001001', 'available', 'dev'),
    ('+15550001002', 'available', 'dev'),
    ('+15550001003', 'available', 'dev'),
    ('+15550001004', 'available', 'dev'),
    ('+15550001005', 'available', 'dev');
