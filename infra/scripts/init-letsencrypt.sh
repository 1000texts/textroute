#!/usr/bin/env bash
#
# First-time TLS setup for the production stack.
#
# Solves a chicken-and-egg problem: nginx will not start when a vhost points at
# a certificate that does not exist yet, but certbot cannot answer an HTTP-01
# challenge until nginx is serving. So we place throwaway self-signed certs at
# the expected paths, start nginx, swap them for real ones, and reload.
#
# Safe to re-run: domains that already have a real certificate are skipped, so
# this will not burn Let's Encrypt rate limits or disturb certificates issued
# for other applications on the same host.
#
# Usage:  ./infra/scripts/init-letsencrypt.sh [--staging]

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

COMPOSE="docker compose -f docker-compose.prod.yml"

if [ ! -f .env ]; then
    echo "error: .env not found. Copy .env.example and fill it in first." >&2
    exit 1
fi

set -a
# shellcheck disable=SC1091
. ./.env
set +a

STAGING_ARG=""
if [ "${1:-}" = "--staging" ]; then
    # Let's Encrypt rate limits are strict; rehearse against staging first.
    STAGING_ARG="--staging"
    echo "Using the Let's Encrypt staging environment."
fi

: "${LETSENCRYPT_EMAIL:?set LETSENCRYPT_EMAIL in .env}"
LETSENCRYPT_DIR="${LETSENCRYPT_DIR:-/etc/letsencrypt}"

DOMAINS=(
    "${API_DOMAIN:?set API_DOMAIN in .env}"
    "${MODERATOR_DOMAIN:?set MODERATOR_DOMAIN in .env}"
    "${DOCS_DOMAIN:?set DOCS_DOMAIN in .env}"
    "${SIMULATOR_DOMAIN:?set SIMULATOR_DOMAIN in .env}"
)

echo "==> Checking DNS"
missing_dns=0
for domain in "${DOMAINS[@]}"; do
    if ! getent hosts "$domain" >/dev/null 2>&1; then
        echo "    $domain does not resolve"
        missing_dns=1
    fi
done
if [ "$missing_dns" -eq 1 ]; then
    echo "error: create the A records first; HTTP-01 validation needs them." >&2
    exit 1
fi

echo "==> Creating placeholder certificates where none exist"
for domain in "${DOMAINS[@]}"; do
    live_dir="$LETSENCRYPT_DIR/live/$domain"
    if [ -f "$live_dir/fullchain.pem" ]; then
        echo "    $domain already has a certificate, leaving it alone"
        continue
    fi
    mkdir -p "$live_dir"
    openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
        -keyout "$live_dir/privkey.pem" \
        -out "$live_dir/fullchain.pem" \
        -subj "/CN=$domain" >/dev/null 2>&1
    echo "    placeholder written for $domain"
done

echo "==> Starting nginx so the ACME challenge can be served"
$COMPOSE up -d nginx

# nginx needs a moment before it will answer challenge requests.
sleep 5

echo "==> Requesting certificates"
for domain in "${DOMAINS[@]}"; do
    # A renewal config is what makes a certificate certbot's own. Its presence
    # means this domain is already managed, so leave it alone -- that is what
    # keeps this script from disturbing certificates belonging to other
    # applications on the same host.
    if [ -f "$LETSENCRYPT_DIR/renewal/$domain.conf" ]; then
        echo "    $domain is already managed by certbot, skipping"
        continue
    fi

    # Whatever is here is our placeholder, and certbot refuses to write into a
    # live directory it did not create. nginx has already loaded the old files
    # into memory, so removing them now does not interrupt it.
    rm -rf "$LETSENCRYPT_DIR/live/$domain" "$LETSENCRYPT_DIR/archive/$domain"

    $COMPOSE run --rm --entrypoint certbot certbot \
        certonly --webroot -w /var/www/certbot \
        $STAGING_ARG \
        --email "$LETSENCRYPT_EMAIL" \
        --agree-tos --no-eff-email \
        -d "$domain"

    echo "    issued for $domain"
done

echo "==> Reloading nginx"
$COMPOSE exec nginx nginx -s reload

echo
echo "Done. Bring up the rest of the stack with:"
echo "  docker compose -f docker-compose.prod.yml up -d"
