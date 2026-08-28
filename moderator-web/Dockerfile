# Dependencies are installed once and shared by both targets.
FROM node:20-alpine AS deps

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

# ----------------------------------------------------------------------------
# dev: Vite dev server with HMR.
# docker-compose.dev.yml bind-mounts the source over /app and keeps this image's
# Linux-built node_modules in a named volume.
# ----------------------------------------------------------------------------
FROM deps AS dev

COPY . .

EXPOSE 5174
CMD ["npm", "run", "dev", "--", "--host"]

# ----------------------------------------------------------------------------
# build: production static output.
#
# Vite inlines env vars at build time, so VITE_API_BASE_URL must be correct
# here; it cannot be changed later by setting it on the running container. A
# wrong value fails silently -- the build succeeds and the app calls the wrong
# host at runtime.
# ----------------------------------------------------------------------------
FROM deps AS build

ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

COPY . .
RUN npm run build

# Publish into the volume nginx serves. Run as a one-shot task, not a service.
CMD ["sh", "-c", "rm -rf /out/* && cp -a dist/. /out/"]
