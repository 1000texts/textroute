select distinct
	m.phone_number as member_number , pn.phone_number as inbound_number, m."name" , g."name" 
from
	public.members m
inner join public.group_memberships gm 
on
	m.id = gm.member_id
inner join public."groups" g 
on
	gm.group_id = g.id
inner join public.phone_numbers pn 
on
	pn.group_id = g.id
where
	gm.status = 'active'
	and gm."role" = 'moderator'
	
	
	
	
	truncate table messages cascade
	
	truncate table request_events cascade
	
	truncate table requests cascade