CREATE TABLE public.groups (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,

    name varchar(100) NOT NULL,
    description text NULL,

    status varchar(20) NOT NULL DEFAULT 'active',

    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT groups_status_check
        CHECK (status IN ('active', 'inactive'))
);


CREATE TABLE public.group_memberships (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,

    group_id uuid NOT NULL
        REFERENCES public.groups(id),

    member_id uuid NOT NULL
        REFERENCES public.members(id),

    role varchar(20) NOT NULL DEFAULT 'member',

    status varchar(20) NOT NULL DEFAULT 'pending',

    invited_at timestamptz NULL,
    consented_at timestamptz NULL,
    joined_at timestamptz NULL,
    removed_at timestamptz NULL,

    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT group_memberships_unique
        UNIQUE (group_id, member_id),

    CONSTRAINT group_memberships_role_check
        CHECK (role IN ('member', 'moderator')),

    CONSTRAINT group_memberships_status_check
        CHECK (status IN (
            'pending',
            'active',
            'declined',
            'removed',
            'opted_out'
        ))
);