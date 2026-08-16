-- public.inbound_messages definition
-- Drop table
-- DROP TABLE public.inbound_messages;
CREATE TABLE
	public.inbound_messages (
		id serial4 NOT NULL,
		sender varchar(50) NOT NULL,
		receiver varchar(50) NOT NULL,
		message text NOT NULL,
		received_at timestamptz DEFAULT CURRENT_TIMESTAMP NULL,
		CONSTRAINT inbound_messages_pkey PRIMARY KEY (id)
	);