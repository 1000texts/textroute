# Postgres + pgvector init scripts
#
# Files in this directory are mounted to /docker-entrypoint-initdb.d
# and run once when the Postgres data volume is first created.
#
# Order matters (lexicographic). Current sequence:
#   01_vector          — pgvector extension
#   02_crypto          — pgcrypto (gen_random_uuid)
#   03_members         — members
#   04_requests        — AI request archive (depends on members)
#   05_groups          — groups + group_memberships
#   06_member_profiles — profiles / skills / consent (depends on memberships)
#   07_phone_numbers   — TextRoute number pool
#   08_messages        — inbound/outbound SMS + workflow lifecycle
#   09_moderator_auth  — hashed login challenges + timed sessions
#
# Reset local schema: docker compose -f docker-compose.dev.yml down -v
