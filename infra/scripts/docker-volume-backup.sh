#!/usr/bin/env bash

# 1. Check your volume exists

docker volume ls

# Example output:
# DRIVER    VOLUME NAME
# local     docker_postgres_data
# Here docker_postgres_data is the volume you want to back up.

# 2. Backup using a temporary container
# The easiest way is to mount the volume into a temporary container and copy its contents out.

EXPORT BACKUP_DIR=$(pwd)/backup
mkdir -p $BACKUP_DIR 
EXPORT VOLUME_NAME=docker_postgres_data


docker run --rm \
  -v docker_postgres_data:/data \
  -v $(pwd)/backup:/backup \
  alpine \
  tar czf /backup/docker_postgres_data_$(date +%F).tar.gz -C /data .