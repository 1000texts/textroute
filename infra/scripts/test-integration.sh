#!/usr/bin/env bash
set -e

echo "🧪 Running integration test..."

./scripts/dev-up.sh

sleep 5

curl -f http://localhost:8080/health
curl -f http://localhost:9090/simulate

echo "✅ Integration test passed"
