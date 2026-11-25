# Air Roam backend

Django + DRF API for the Air Roam web store (`/api/v1`) and admin dashboard (`/api/v1/staff`).
Design: `../docs/superpowers/specs/2026-11-23-air-roam-backend-design.md`.

## Run locally

```powershell
docker compose up -d                      # Postgres 17 on DB_PORT, Redis 7 on :6379
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env                    # then set DJANGO_SECRET_KEY to a long random string
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py create_staff --email you@example.com --password "a-long-password" --admin
.venv\Scripts\python manage.py runserver 8000
```

- API: http://localhost:8000/api/v1/ · OpenAPI: http://localhost:8000/api/schema/ (also committed as `schema.yml`; the frontend generates types from it)
- Django admin (developers only, superusers, only when `ADMIN_ENABLED=true`): http://localhost:8000/dev-admin/ — create a superuser with `manage.py createsuperuser`. Staff never use it; they use the admin dashboard.

## Tests

```powershell
.venv\Scripts\python -m pytest -q
```

Tests need the Docker Postgres running (ArrayField). Redis is optional: without `REDIS_URL` the cache falls back to in-memory.

## PayMongo (test mode)

Set `PAYMONGO_SECRET_KEY` (a `sk_test_…` key) from the PayMongo dashboard in test mode, and `PAYMONGO_METHODS` to methods enabled on the account (listing any other makes checkout fail).
Create a webhook for `checkout_session.payment.paid` at `https://<public-url>/api/v1/payments/paymongo/webhook` (use a tunnel such as `cloudflared` or `ngrok` locally) and put its secret in `PAYMONGO_WEBHOOK_SECRET`. Test and live mode each have their own key and webhook secret.

PayMongo checkouts never expire by themselves: schedule `manage.py expire_unpaid_orders` hourly (expires orders unpaid for 24 hours; `--hours` changes that).

## Production switches (hosting is decided later)

`DEBUG=false`, `COOKIE_SECURE=true`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS` (`https://airroam.ph`, `https://admin.airroam.ph`), `CSRF_COOKIE_DOMAIN=.airroam.ph`, `SECURE_SSL_REDIRECT=true`, `SECURE_HSTS_SECONDS`, `ADMIN_ENABLED=false`, `WEB_REBUILD_HOOK_URL` (Cloudflare Pages deploy hook). Run `manage.py check --deploy` with those set.
