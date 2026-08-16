#!/usr/bin/env bash
set -e

echo "🚀 Starting TextRoute dev environment..."

docker compose \
  -f infra/docker-compose.dev.yml \
  up --build -d

echo "✅ Dev stack running"
