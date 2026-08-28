FROM python:3.12-slim AS base

WORKDIR /app

RUN pip install --no-cache-dir mkdocs mkdocs-material

COPY mkdocs.yml .
COPY docs/ docs/

# ----------------------------------------------------------------------------
# dev: live-reloading docs server.
# ----------------------------------------------------------------------------
FROM base AS dev

EXPOSE 8000
CMD ["mkdocs", "serve", "--dev-addr=0.0.0.0:8000"]

# ----------------------------------------------------------------------------
# build: static site published into the volume nginx serves.
# ----------------------------------------------------------------------------
FROM base AS build

RUN mkdocs build --site-dir /site

CMD ["sh", "-c", "rm -rf /out/* && cp -a /site/. /out/"]
