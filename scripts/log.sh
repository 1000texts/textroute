#!/usr/bin/env bash

SERVICE=${1:-textroute}

docker compose \
  -f infra/docker-compose.dev.yml \
  logs -f $SERVICE
