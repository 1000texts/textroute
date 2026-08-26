#!/usr/bin/env bash
set -euo pipefail

# Load .env from repo root when present
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

REQUIRED_VARS=(
  DATABASE_URL
  POSTGRES_USER
  POSTGRES_PASSWORD
  POSTGRES_DB
)

missing=0
for var in "${REQUIRED_VARS[@]}"; do
  if [[ -z "${!var:-}" ]]; then
    echo "Missing required env var: $var"
    missing=1
  fi
done

if [[ "$missing" -ne 0 ]]; then
  echo "Copy .env.example to .env and fill in values."
  exit 1
fi

echo "Environment looks good"
