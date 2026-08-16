#!/usr/bin/env bash


# 3. Restore a named volume
# Create a new (or empty) volume:

docker volume create docker_postgres_data_restore

# Restore the backup:

docker run --rm \
  -v docker_postgres_data_restore:/data \
  -v $(pwd)/backup:/backup \
  alpine \
  sh -c "cd /data && tar xzf /backup/docker_postgres_data_2025-12-29.tar.gz --strip 1"

# --strip 1 removes the leading folder structure from the archive.
# The volume docker_postgres_data_restore now contains all your backed-up data.

# 4. Optional: Use docker cp
# If a container is already using the volume, you can copy data out:
docker cp $(docker create -v docker_postgres_data:/data alpine:latest):/data ./backup

# Slightly less flexible than tar, but works for quick copies.