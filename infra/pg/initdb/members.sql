-- public.members definition
-- Drop table
-- DROP TABLE public.members;
CREATE TABLE
	public.members (
		"name" varchar NULL,
		member_id uuid NULL,
		CONSTRAINT members_unique UNIQUE (member_id)
	);