#!/usr/bin/env bash
set -e

docker compose \
  -f infra/docker-compose.dev.yml \
  down

echo "🛑 Dev stack stopped"
