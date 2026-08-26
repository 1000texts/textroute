#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

echo "Starting TextRoute dev environment..."
docker compose -f docker-compose.dev.yml up --build -d
echo "Dev stack running (API :6060, SMS sim :5173, docs :8000)"
