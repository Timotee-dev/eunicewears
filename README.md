# Eunice Wears

Django + DRF store with an HTML/CSS/vanilla JS frontend. See `ARCHITECTURE.md` for the full design.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                    # then set SECRET_KEY
python manage.py migrate
python manage.py seed_demo                              # demo tees, delivery rates, owner login (DEBUG only)
python manage.py runserver
```

Open http://localhost:8000.

- Owner login from the seed: `owner@eunicewears.test` / `demo-owner-2026` (development only), then open `/dashboard/`.
- With `EMAIL_HOST` empty, emails (confirmation links, receipts) print in the terminal.
- API docs: `/api/docs/`  Health: `/api/health/`

## Payments

- **No Paystack key + DEBUG=True**: checkout goes to a local sandbox page where you approve or decline a
  test payment. It runs the same server-side verification as Paystack and cannot be enabled in production.
- **Paystack test mode**: put your `sk_test_...` and `pk_test_...` keys in `.env`. Set the webhook URL on the
  Paystack dashboard to `https://<your-domain>/api/payments/webhook/` (use a tunnel such as ngrok locally).
- An order is only marked paid after the server asks Paystack and the amount and currency match.

## Background jobs (Celery)

Locally, with `REDIS_URL` empty, emails and jobs run inline and you start nothing extra.
In production set `REDIS_URL` and run one worker alongside the web service:

```bash
celery -A config worker -B -l info
```

`-B` also runs the scheduler, which cancels unpaid orders every 15 minutes and puts their stock back.
(`python manage.py expire_unpaid_orders --minutes 60` still works if you prefer a cron job.)

## Refunds

Cancelling a paid order, or moving "Refund requested" to "Refunded", sends the refund through Paystack
automatically (admin role only). If Paystack refuses, nothing is changed and the dashboard shows why.
Paystack then takes a few working days to return the money; that final step is tracked on the Paystack dashboard.

## Tests

- `python manage.py test apps`: the full API and page suite.
- `python manage.py test e2e`: a real-browser purchase. Needs `pip install playwright && playwright install chromium`.

## Where things are managed

`/dashboard/` covers the whole business: overview, orders, products and stock, analytics, reviews, customers,
marketing (promo codes, newsletter export), content (home page, size guide, policy pages) and settings
(delivery rates, categories). `/backoffice/` (Django admin) is only needed for staff roles and collections.

`seed_demo` creates an owner login, the Tees category and starter delivery rates. It creates no products.
If an older copy seeded placeholder tees, remove them with `python manage.py clear_demo`.
