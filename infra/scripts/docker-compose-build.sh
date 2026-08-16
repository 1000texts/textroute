#!/usr/bin/env bash

# rebuild all containers
docker compose down
docker compose up -d --build 'textroute' 'postgres' 'mkdocs'
docker compose --env-file /Users/kenjikahara/textroute/tools/sms-simulator/.env.docker -f 'docker-compose.yml' up -d --build 'sms-simulator' 
docker compose up -d

