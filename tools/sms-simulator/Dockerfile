# Dependencies are installed once and shared by both targets.
FROM node:20-alpine AS deps

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

# ----------------------------------------------------------------------------
# dev: Vite dev server with HMR.
# ----------------------------------------------------------------------------
FROM deps AS dev

ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
# Dev only: the simulator posts straight to the API, so the browser needs the
# webhook secret. Production injects it in nginx instead.
ARG VITE_WEBHOOK_SECRET
ENV VITE_WEBHOOK_SECRET=${VITE_WEBHOOK_SECRET}

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host"]

# ----------------------------------------------------------------------------
# build: production static output.
#
# In production VITE_API_BASE_URL is a same-origin path ("/api"), not the API's
# public URL. The simulator's own vhost proxies that path and injects the
# webhook secret server-side, so the secret never reaches the browser -- a Vite
# build would inline it into public JavaScript.
# ----------------------------------------------------------------------------
FROM deps AS build

ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

COPY . .
RUN npm run build

CMD ["sh", "-c", "rm -rf /out/* && cp -a dist/. /out/"]
