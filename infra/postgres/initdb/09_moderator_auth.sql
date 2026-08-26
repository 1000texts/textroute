CREATE TABLE public.moderator_login_challenges (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,

    group_id uuid NOT NULL
        REFERENCES public.groups(id) ON DELETE CASCADE,

    moderator_member_id uuid NOT NULL
        REFERENCES public.members(id) ON DELETE CASCADE,

    code_hash char(64) NOT NULL,
    expires_at timestamptz NOT NULL,
    attempt_count int NOT NULL DEFAULT 0,
    consumed_at timestamptz NULL,
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT moderator_login_challenges_attempt_count_check
        CHECK (attempt_count >= 0)
);

CREATE INDEX idx_moderator_login_challenges_lookup
    ON public.moderator_login_challenges(id, expires_at);

CREATE TABLE public.moderator_sessions (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,

    token_hash char(64) NOT NULL,

    group_id uuid NOT NULL
        REFERENCES public.groups(id) ON DELETE CASCADE,

    moderator_member_id uuid NOT NULL
        REFERENCES public.members(id) ON DELETE CASCADE,

    expires_at timestamptz NOT NULL,
    revoked_at timestamptz NULL,
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT moderator_sessions_token_hash_unique
        UNIQUE (token_hash)
);

CREATE INDEX idx_moderator_sessions_lookup
    ON public.moderator_sessions(token_hash, expires_at);
