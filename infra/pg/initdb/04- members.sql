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