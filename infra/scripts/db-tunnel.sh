#!/usr/bin/env bash
#
# Open a local port onto the production database over SSH, for psql or a GUI
# client, without exposing Postgres anywhere.
#
# The production stack deliberately publishes no port for Postgres and keeps it
# on an internal Docker network, so it is unreachable from the internet and
# from the server's own host ports. Publishing a port "just for debugging" is
# how databases end up on the public internet, and it cannot work here anyway:
# Docker will not forward a port to a container attached only to an internal
# network. The host can still route to the container, so SSH forwards to the
# container address directly and nothing is left listening when you disconnect.
#
# Usage:  ./infra/scripts/db-tunnel.sh <ssh-host> [local-port]
# Then:   psql "postgresql://postgres:<password>@localhost:15432/postgres"
#
# Get the password with:
#   ssh <ssh-host> "grep POSTGRES_PASSWORD /srv/www/textroute/.env"

set -euo pipefail

SSH_HOST="${1:-}"
LOCAL_PORT="${2:-15432}"
CONTAINER="${DB_CONTAINER:-textroute-postgres-1}"

if [ -z "$SSH_HOST" ]; then
    echo "usage: $0 <ssh-host> [local-port]" >&2
    exit 1
fi

# The address changes whenever the container is recreated, so never hard-code it.
container_ip=$(ssh "$SSH_HOST" \
    "docker inspect $CONTAINER --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'" \
    | tr -d '\r')

if [ -z "$container_ip" ]; then
    echo "error: could not find $CONTAINER on $SSH_HOST. Is the stack running?" >&2
    exit 1
fi

echo "Postgres at $container_ip:5432 is now on localhost:$LOCAL_PORT"
echo "Connect with:"
echo "  psql \"postgresql://postgres:<password>@localhost:$LOCAL_PORT/postgres\""
echo
echo "Press Ctrl-C to close the tunnel."

exec ssh -N -L "${LOCAL_PORT}:${container_ip}:5432" "$SSH_HOST"
