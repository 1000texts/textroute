#!/usr/bin/env bash
set -e

echo "🐳 Building TextRoute image..."

docker build \
  -t kkahara/tt-textroute:local \
  apps/textroute

echo "✅ Build complete"
