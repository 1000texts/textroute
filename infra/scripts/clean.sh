#!/usr/bin/env bash

echo "🧹 Cleaning Docker artifacts..."

docker compose \
  -f infra/docker-compose.dev.yml \
  down -v --remove-orphans

docker system prune -f

echo "✅ Clean slate"
