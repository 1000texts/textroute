#!/usr/bin/env bash

REQUIRED_VARS=(
  DATABASE_URL
  JWT_SECRET
  APP_ENV
)

for var in "${REQUIRED_VARS[@]}"; do
  if [[ -z "${!var}" ]]; then
    echo "❌ Missing required env var: $var"
    exit 1
  fi
done

echo "✅ Environment looks good"
