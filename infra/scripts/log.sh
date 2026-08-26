#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

SERVICE=${1:-textroute}
docker compose -f docker-compose.dev.yml logs -f "$SERVICE"
