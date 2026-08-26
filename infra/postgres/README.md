This service uses the published `pgvector/pgvector:pg17` image (see root
`docker-compose.*.yml`). Schema lives in `initdb/` and is applied on first boot.

Do not vendor the pgvector source tree into this repo.
