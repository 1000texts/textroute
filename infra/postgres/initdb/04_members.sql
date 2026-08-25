CREATE TABLE public.members (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,

    phone_number varchar(16) NOT NULL,
    name varchar(100) NULL,

    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT members_phone_number_unique
        UNIQUE (phone_number)
);



CREATE TABLE public.member_profiles (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,

    membership_id uuid NOT NULL
        REFERENCES public.group_memberships(id),

    display_name varchar(100) NULL,
    bio text NULL,

    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT member_profiles_membership_unique
        UNIQUE (membership_id)
);



CREATE TABLE public.member_items (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,

    membership_id uuid NOT NULL
        REFERENCES public.group_memberships(id),

    name varchar(255) NOT NULL,
    description text NULL,
    item_type varchar(50) NULL,

    created_at timestamptz NOT NULL DEFAULT now()
);



CREATE TABLE public.member_skills (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,

    membership_id uuid NOT NULL
        REFERENCES public.group_memberships(id),

    skill_name varchar(100) NOT NULL,
    proficiency varchar(50) NULL,
    description text NULL,

    created_at timestamptz NOT NULL DEFAULT now()
);


CREATE TABLE public.member_interests (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,

    membership_id uuid NOT NULL
        REFERENCES public.group_memberships(id),

    interest_name varchar(100) NOT NULL,

    created_at timestamptz NOT NULL DEFAULT now()
);


CREATE TABLE public.member_availability (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,

    membership_id uuid NOT NULL
        REFERENCES public.group_memberships(id),

    day_of_week smallint NOT NULL,

    start_time time NOT NULL,
    end_time time NOT NULL,

    timezone varchar(50) NULL,

    CONSTRAINT member_availability_day_check
        CHECK (day_of_week BETWEEN 0 AND 6)
);

CREATE TABLE public.membership_consents (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,

    membership_id uuid NOT NULL
        REFERENCES public.group_memberships(id),

    consent_type varchar(50) NOT NULL,

    status varchar(20) NOT NULL DEFAULT 'pending',

    consent_version int NOT NULL DEFAULT 1,

    requested_at timestamptz NOT NULL DEFAULT now(),
    responded_at timestamptz NULL,

    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT membership_consents_status_check
        CHECK (status IN ('pending', 'granted', 'revoked')),

    CONSTRAINT membership_consents_version_check
        CHECK (consent_version >= 1),

    CONSTRAINT membership_consents_type_check
        CHECK (consent_type IN (
            'group_membership',
            'receive_messages',
            'profile_sharing'
        ))
);

