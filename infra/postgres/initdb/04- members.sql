-- public.members definition
-- Drop table
-- DROP TABLE public.members;
CREATE TABLE
	public.members (
		"name" varchar NULL,
		member_id uuid DEFAULT gen_random_uuid () NULL,
		sender varchar(50) NULL,
		receiver varchar(50) NULL,
		CONSTRAINT members_unique UNIQUE (member_id),
		CONSTRAINT members_unique_1 UNIQUE (sender, receiver)
	);

--1. member_items
--Items that a member owns or can lend/share.
CREATE TABLE public.member_items (
    item_id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    member_id uuid NOT NULL REFERENCES public.members(member_id),
    name varchar(255) NOT NULL,
    description text NULL,
    item_type varchar(50) NULL,
    created_at timestamp DEFAULT now()
);

--2. member_availability
--Tracks when members are available for events, calls, etc.
CREATE TABLE public.member_availability (
    availability_id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    member_id uuid NOT NULL REFERENCES public.members(member_id),
    day_of_week varchar(10) NOT NULL, -- e.g., 'Monday', 'Tuesday'
    start_time time NOT NULL,
    end_time time NOT NULL,
    timezone varchar(50) NULL
);

--3. member_talents
--Stores skills, talents, or specializations of a member.
create table public.member_talents (
    talent_id uuid default gen_random_uuid() primary key,
    member_id uuid not null references public.members(member_id),
    talent_name varchar(100) not null,
    proficiency varchar(50) null,
-- e.g., Beginner, Intermediate, Expert
description text null
);

--4. member_contacts
--Optional: store phone/email/social handles for a member.
CREATE TABLE public.member_contacts (
    contact_id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    member_id uuid NOT NULL REFERENCES public.members(member_id),
    contact_type varchar(50) NOT NULL, -- e.g., email, phone, twitter
    contact_value varchar(255) NOT NULL,
    is_primary boolean DEFAULT false
);

--5. member_groups
--Optional: if you want members to join groups or communities.
CREATE TABLE public.member_groups (
    group_id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    group_name varchar(100) NOT NULL,
    description text NULL
);