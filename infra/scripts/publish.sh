#!/usr/bin/env bash
set -e

IMAGE=kkahara/tt-textroute
TAG=${1:-latest}

echo "📦 Publishing $IMAGE:$TAG"

docker buildx build \
  --platform linux/amd64 \
  -t $IMAGE:$TAG \
  --push \
  apps/textroute

echo "✅ Published $IMAGE:$TAG"
