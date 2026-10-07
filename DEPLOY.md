# Deploying Eunice Wears to Render

You need four free accounts: GitHub, Render, Cloudinary (product photos) and Brevo (emails). Paystack you already have.

## 1. Put the code on GitHub

In the project folder:

```bat
git init
git add .
git commit -m "Eunice Wears"
git branch -M main
git remote add origin https://github.com/<your-username>/eunice-wears.git
git push -u origin main
```

Create the empty `eunice-wears` repository on GitHub first. `.env` and `db.sqlite3` are ignored and must stay off GitHub.

## 2. Collect the keys

| Value | Where to get it |
|---|---|
| `CLOUDINARY_URL` | Cloudinary dashboard > API Keys > "API environment variable". Looks like `cloudinary://<key>:<secret>@<cloud>` |
| `BREVO_API_KEY` | Brevo > SMTP & API > API Keys > Generate. Starts with `xkeysib-` |
| `DEFAULT_FROM_EMAIL` | An address you verified in Brevo (Senders), written as `Eunice Wears <you@example.com>` |
| `PAYSTACK_PUBLIC_KEY`, `PAYSTACK_SECRET_KEY` | Paystack > Settings > API Keys & Webhooks. Start with the **test** keys |
| `OWNER_EMAIL`, `OWNER_PASSWORD` | You choose. The owner's dashboard login; password at least 10 characters |

Email matters: customers cannot sign in until they open the confirmation email. Render's free plan blocks
ordinary SMTP, which is why this uses Brevo's HTTPS API.

## 3. Create the service

1. Render > New > Blueprint > choose the repository. Render reads `render.yaml` and proposes a web service and a database.
2. Fill in the values it asks for (the table above) and click Apply.
3. The first build takes a few minutes. It installs packages, collects static files, sets up the database and creates the owner account.
4. Open `https://<your-service>.onrender.com`. Sign in with the owner email and password, then go to `/dashboard/`.

## 4. Point Paystack at the site

Paystack > Settings > API Keys & Webhooks > Webhook URL:

```
https://<your-service>.onrender.com/api/payments/webhook/
```

Then make one full test purchase with a Paystack test card, and cancel that order from the dashboard to test the refund.

## 5. Before taking real money

- Dashboard > Settings: real delivery fees.
- Dashboard > Content: returns, shipping, privacy and terms pages; size guide.
- Dashboard > Products: real tees with photos; Home page: choose the ten per category.
- Swap the Paystack test keys for the live keys in Render > Environment (the service redeploys by itself).

## Good to know about the free plan

- The service sleeps after about 15 minutes without visitors; the next visit takes up to a minute to wake it.
- Render's free PostgreSQL database expires after a limited period (check the date on its page). Upgrade it or
  move the data before then, or the store's data is deleted.
- There is no background worker. Emails send during the request, and unpaid orders are cleaned up whenever
  someone checks out or the owner opens the dashboard.
- Custom domain: Render > Settings > Custom Domains, then set `SITE_URL=https://yourdomain` and add the domain
  to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` (as `https://yourdomain`) in Environment.
