--- group table
CREATE TABLE public.member_groups (
    group_id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    group_name varchar(100) NOT NULL,
    outbound_number varchar(15) NULL,
    description text NULL
);
--- Junction table for many-to-many relationship between members and groups
CREATE TABLE public.member_group_members (
    group_id uuid NOT NULL REFERENCES public.member_groups(group_id),
    member_id uuid NOT NULL REFERENCES public.members(member_id),
    joined_at timestamp DEFAULT now(),
    PRIMARY KEY(group_id, member_id)
);
