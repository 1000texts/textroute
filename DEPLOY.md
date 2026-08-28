# Deploying TextRoute

This deploys the whole stack to a single Linux server with Docker: the API,
Postgres, the moderator UI, the documentation site, and the SMS simulator, all
behind nginx with Let's Encrypt certificates.

Nothing here is specific to one host. Every domain and secret comes from `.env`.

## What you need

- A server with Docker Engine and the Compose plugin, ports 80 and 443 free.
- Four DNS A records pointing at it (AAAA too if the server has IPv6):

  | Record | Serves |
  |---|---|
  | `API_DOMAIN` | the FastAPI application |
  | `MODERATOR_DOMAIN` | the moderator web UI |
  | `DOCS_DOMAIN` | the documentation site |
  | `SIMULATOR_DOMAIN` | the SMS simulator |

Use subdomains of one registrable domain. The moderator session cookie is
`SameSite=Lax`, which works across sibling subdomains because they are
same-site. Putting the UI on a different apex domain would require changing the
cookie to `SameSite=None`.

## First install

```bash
sudo mkdir -p /srv/www/textroute
sudo git clone https://github.com/1000texts/textroute.git /srv/www/textroute
cd /srv/www/textroute

cp .env.example .env
```

Edit `.env`. At minimum set the four domains, `LETSENCRYPT_EMAIL`, and generate
two secrets plus a database password:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"   # AUTH_SECRET
python3 -c "import secrets; print(secrets.token_hex(32))"   # WEBHOOK_SECRET
```

Set `AUTH_COOKIE_SECURE=true` and `AUTH_EXPOSE_DEVELOPMENT_CODE=false` for a
public deployment, and make `DATABASE_URL_DOCKER` match your Postgres password.

Create the simulator's Basic auth credentials:

```bash
docker run --rm httpd:alpine htpasswd -nb <user> '<password>' \
  | sudo tee infra/nginx/secrets/simulator.htpasswd
```

Build the static sites, obtain certificates, and start:

```bash
docker compose -f docker-compose.prod.yml --profile build run --rm moderator-web-build
docker compose -f docker-compose.prod.yml --profile build run --rm sms-simulator-build
docker compose -f docker-compose.prod.yml --profile build run --rm mkdocs-build

./infra/scripts/init-letsencrypt.sh          # add --staging to rehearse first
docker compose -f docker-compose.prod.yml up -d
```

`init-letsencrypt.sh` writes throwaway self-signed certificates first, because
nginx will not start pointing at a certificate that does not exist, and certbot
cannot answer a challenge until nginx is serving. It skips domains that already
have a certificate, so it is safe to re-run and will not touch certificates
belonging to other applications on the same host.

## Deploying changes

```bash
cd /srv/www/textroute
git pull
./infra/scripts/deploy.sh
```

This rebuilds the static sites and the API, restarts them, and reloads nginx.
Postgres keeps running throughout, so the data volume is never at risk.

## Logging in the first time

`SMS_PROVIDER` defaults to `logging`, which writes outbound messages to the log
instead of sending them, and `AUTH_EXPOSE_DEVELOPMENT_CODE` is false in
production, so the API will not return the login code either. **The moderator
login code appears only in the API logs:**

```bash
docker compose -f docker-compose.prod.yml logs -f textroute
```

Configure a real SMS provider before anyone other than you needs to log in.

## The database

Postgres stores its data in the `postgres_data` Docker volume, which survives
`up`, `down`, `build`, and reboots. Two things will still lose it:

- **`docker compose down -v` deletes the volume.** Never pass `-v` to this
  stack.
- **`infra/postgres/initdb` only runs when the volume is empty**, i.e. on the
  very first start. Schema changes made later are not applied by editing those
  files; run migrations against the live database.

Take backups regardless, since a single volume on a single machine is one
mistake away from gone:

```bash
./infra/scripts/backup-db.sh
```

Run it nightly from cron:

```
15 3 * * * cd /srv/www/textroute && ./infra/scripts/backup-db.sh >> /var/log/textroute-backup.log 2>&1
```

## Security notes

**The inbound webhook is authenticated by a shared secret.** `POST /webhook/*`
requires an `X-Webhook-Secret` header matching `WEBHOOK_SECRET`. Without it,
anyone who knows your API URL could forge inbound messages into a group, and
under the `auto_group` routing policy those fan out as real SMS. If
`WEBHOOK_SECRET` is unset the webhook rejects everything rather than running
open. Configure your SMS provider to send the header, and replace this with
provider signature verification when you move to a real carrier.

**The simulator is doubly gated** because it can inject messages into live
groups: HTTP Basic auth on the vhost, and the webhook secret injected by nginx
rather than shipped in the browser bundle. It is built with
`VITE_API_BASE_URL=/api` so it calls its own origin.

## Running another application on the same server

`infra/nginx/local.d/` is mounted into the proxy and ignored by git. Drop a
vhost there for any other app, then attach that app's container to the proxy
network so nginx can reach it by container name:

```yaml
# the other application's compose file
services:
  yourapp:
    networks: [edge]

networks:
  edge:
    external: true
    name: textroute_web        # EDGE_NETWORK_NAME in .env
```

Publishing the other app to `127.0.0.1` is not enough on its own: the nginx
container cannot reach the host's loopback interface, so it must share a Docker
network instead.

If that application already has certificates issued with certbot's nginx
plugin, switch its renewal to webroot, since the host nginx that plugin drives
is no longer running:

```bash
sudo sed -i 's/^authenticator = nginx/authenticator = webroot/' \
  /etc/letsencrypt/renewal/<domain>.conf
echo 'webroot_path = /var/www/certbot,' | sudo tee -a /etc/letsencrypt/renewal/<domain>.conf
```

## Certificate renewal

The `certbot` container renews every certificate in `/etc/letsencrypt` twice a
day, including ones belonging to other applications. Check it:

```bash
docker compose -f docker-compose.prod.yml run --rm --entrypoint certbot certbot \
  renew --webroot -w /var/www/certbot --dry-run
```

## Troubleshooting

| Symptom | Cause |
|---|---|
| nginx will not start, "cannot load certificate" | Certificates missing; run `init-letsencrypt.sh` |
| Certificate request fails | DNS not resolving yet, or port 80 blocked |
| Moderator UI loads but every call fails | UI built with the wrong `API_DOMAIN`; Vite inlines it at build time, so rebuild |
| Login succeeds then immediately logs out | `AUTH_COOKIE_SECURE=true` without HTTPS, or UI and API not on sibling subdomains |
| Webhook returns 401 | Missing or wrong `X-Webhook-Secret` |
| Webhook returns 503 | `WEBHOOK_SECRET` is not set in `.env` |
