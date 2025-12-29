This project uses Postgres' vector column.
Create a Docker container by using the pgvector-enabled image.

Example:

services:
  postgres:
    image: pgvector/pgvector:pg16
    container_name: postgres
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: postgres
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
