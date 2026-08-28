#!/usr/bin/env bash
#
# Deploy the current checkout: rebuild the static sites, rebuild the API, and
# restart. Postgres is left running so the data volume is never at risk.
#
# Usage:  ./infra/scripts/deploy.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

COMPOSE="docker compose -f docker-compose.prod.yml"

echo "==> Building static sites"
# Each builder writes into the volume nginx serves, then exits.
$COMPOSE --profile build build moderator-web-build sms-simulator-build mkdocs-build
$COMPOSE --profile build run --rm moderator-web-build
$COMPOSE --profile build run --rm sms-simulator-build
$COMPOSE --profile build run --rm mkdocs-build

echo "==> Building and restarting services"
$COMPOSE build textroute
$COMPOSE up -d

echo "==> Reloading nginx"
$COMPOSE exec nginx nginx -t
$COMPOSE exec nginx nginx -s reload

echo
echo "Deployed. Recent API logs:"
$COMPOSE logs --tail 20 textroute
