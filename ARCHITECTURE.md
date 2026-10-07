# Eunice Wears: system architecture

Single brand, single owner. Plain round neck tees (oversized and regular fits) today; the catalog model
is general enough to take other product types later without a rewrite.

## 1. System architecture

```
Browser (HTML + CSS + vanilla JS)
   |  pages: server-rendered shells        |  data + actions: fetch() to /api/*
   v                                       v
Django  ── apps.pages (templates) ── Django REST Framework (session auth, CSRF, throttles)
   |                                       |
   |                         service layer (pricing, inventory, orders, payments)
   v                                       v
PostgreSQL (source of truth)     Redis (cache, throttles, Celery broker)     Celery workers (email, webhooks follow-up, reminders)
                                           |
                     Paystack (payments)   Cloudinary (product media)   SMTP provider (email)
```

One Django service serves both the pages and the API from the same origin. That is what makes this
stricter than a token-in-localStorage setup: the session lives in an HttpOnly cookie that JavaScript
cannot read, CSRF protection applies to every write, and there is no CORS surface to misconfigure.

Rule that holds everywhere: the browser only displays and asks. Prices, discounts, shipping, stock,
totals, promo validity and permissions are computed by the backend from database state.

## 2. Database (ERD description)

Phase 1 (built):
- **User** (email login, role: customer / staff / admin / super_admin, email_verified_at)
- **CustomerProfile** 1:1 User (marketing opt-in; later: preferences)
- **Address** N:1 User (partial unique index: one default per user)
- **SiteSetting** (key -> JSON; owner-editable content)
- **AuditLog** (actor, action, object, changes, IP; append-only)

Phase 2, catalog and stock:
- **Category** (tree via parent), **Collection**, **Product** N:1 Category, M:N Collection, tags, flags
  (featured, best seller, new arrival, published), soft-delete via `archived_at`
- **ProductImage** N:1 Product (position for ordering, alt text, optional variant link)
- **ProductVariant** N:1 Product (fit, size, colour, SKU unique, optional price override, `stock` with
  CHECK stock >= 0, low-stock threshold). Stock always lives on the variant; a product with no options
  gets one default variant so there is a single code path.
- **InventoryTransaction** N:1 Variant (delta, reason: restock / sale / refund / adjustment, order ref,
  actor). Stock history is this ledger; `variant.stock` is the running total.
- **SizeGuide**, **ProductView**, **BackInStockRequest**

Phase 3 to 5, selling:
- **Cart** (user or anonymous session key) -> **CartItem** (variant, qty; unique per cart+variant)
- **Wishlist** 1:1 User -> **WishlistItem**
- **ShippingMethod** (zone: Lagos / other states / international / pickup; flat rate; free threshold)
- **PromoCode** (percent or fixed, min order, max discount, window, limits, scoped products and
  categories) -> **PromoCodeUsage** (code, user, order)
- **Order** (number `EW-2026-000001`, user, status, payment status, money snapshot: subtotal, discount,
  shipping, total, currency; address snapshot as JSON so later edits never rewrite history)
  -> **OrderItem** (variant, name/SKU/price snapshot, qty) -> **OrderEvent** (status timeline)
- **Payment** N:1 Order (provider, reference unique, amount, currency, status, raw payload)
- **Review** (user, product, order item; unique per purchase) -> **ReviewImage**
- **NewsletterSubscriber**, **Notification**

Money is stored as integer kobo (`BigIntegerField`) with a currency code beside it. No floats.
Orders, payments and inventory transactions are never hard-deleted.

## 3. Folder structure

```
config/            settings, urls, wsgi
apps/
  core/            shared: base models, audit log, permissions, error format, health, security headers
  accounts/        users, roles, auth API, addresses, account emails
  pages/           page shells (templates only, no business logic)
  catalog/         (P2) products, variants, categories, collections, search, filters
  inventory/       (P2) stock ledger and reservation service
  cart/            (P3) cart, wishlist
  checkout/        (P3) totals, shipping, promo validation
  payments/        (P4) PaymentProvider interface, PaystackProvider, webhook
  orders/          (P4) orders, lifecycle, tracking
  reviews/         (P5)
  dashboard/       (P6) owner dashboard API and pages, analytics
  notifications/   (P7) email, in-app, events
templates/         base, pages, emails
static/css|js|img  design system and page scripts
```

Each app keeps `models.py`, `serializers.py`, `views.py`, `services.py` (business rules), `tests/`.
Views stay thin; anything touching money or stock goes through a service function.

## 4. API architecture

- REST under `/api/`, JSON only, session-authenticated, page-number pagination.
- One error shape everywhere: `{"error": {"code", "message", "fields"}}`.
- Public reads: products, categories, collections, search. Customer: cart, wishlist, checkout, orders,
  reviews, account. Owner: `/api/admin/*`, guarded by role permissions on the server.
- Throttling: global anon/user limits plus tight scoped limits on login, register and email-sending.
- OpenAPI schema at `/api/schema/`, Swagger UI at `/api/docs/`.

## 5. Authentication architecture

- Email + password. Passwords hashed by Django (PBKDF2), validated against length, common-password and
  similarity rules.
- Registration always creates a `customer`; role can never be set from the API body.
- Email must be confirmed before sign-in. Confirmation and reset links are signed, expire in 24 hours
  and are single use.
- Login rotates the session key. Changing a password signs out every other device.
- Login, reset and resend responses do not reveal whether an email has an account.
- Cookies: HttpOnly session, SameSite=Lax, Secure in production, HSTS, strict Content-Security-Policy
  (no inline scripts).

## 6. Payment architecture

```
checkout  -> Order(pending_payment) + stock reserved
          -> PaymentProvider.initialize(order) -> Paystack authorization URL
customer pays on Paystack
callback  -> POST /api/payments/verify/ {reference}  ─┐
webhook   -> POST /api/payments/webhook/ (HMAC-SHA512 ─┴-> same service: confirm_payment(reference)
             signature checked with the secret key)
confirm_payment: lock the Payment row, call Paystack verify, require status=success AND amount == order
total AND currency == order currency, then mark paid, commit stock, write OrderEvent, queue email.
```

`confirm_payment` is idempotent: a payment already marked successful returns early, so the callback and
the webhook can both arrive, in any order, any number of times. The browser's word is never used.
`PaymentProvider` is an interface (`initialize`, `verify`, `parse_webhook`, `refund`); Flutterwave or
Stripe become new classes, not checkout changes.

## 7. Order lifecycle

`pending_payment -> paid -> processing -> ready_for_delivery -> shipped -> delivered`
Side exits: `cancelled` (before shipping), `refund_requested -> refunded`.
Transitions are a whitelist in one service function; every transition writes an OrderEvent (timestamp,
actor) which is what the customer's tracking timeline shows. Unpaid orders expire after a set window and
release their reserved stock.

## 8. Inventory lifecycle

- Restock or adjustment by the owner -> InventoryTransaction(+/-) -> variant.stock updated in the same
  database transaction.
- Checkout reserves stock: `SELECT ... FOR UPDATE` on the variant rows, check, decrement, write ledger
  rows. Two buyers racing for the last tee are serialised by the row lock; the second sees zero stock
  and gets a clear "sold out" error. The CHECK constraint is the final backstop.
- Payment success keeps the decrement. Expiry, cancellation or refund writes a compensating ledger row.
- Stock rising from zero triggers back-in-stock notifications.

## 9. Admin permission model

| Role        | Can do |
|-------------|--------|
| customer    | own account, cart, orders, reviews |
| staff       | view and fulfil orders, manage stock, moderate reviews |
| admin       | + products, promo codes, content, customers, analytics, refunds |
| super_admin | + staff accounts, settings, audit log (the business owner) |

Roles are ranked; each admin endpoint declares its minimum role and the API enforces it. Hiding a menu
item is presentation only. Sensitive actions write to the audit log.

## 10. Deployment architecture

- **Web**: Render web service running gunicorn; WhiteNoise serves hashed static files.
- **Database**: managed PostgreSQL with daily backups. **Cache/broker**: managed Redis.
- **Worker**: Render background worker running Celery (from Phase 7).
- **Media**: Cloudinary. **Email**: SMTP provider.
- All configuration through environment variables (`.env.example` lists them). `DEBUG=False` switches on
  HTTPS redirect, secure cookies and HSTS automatically.
- `/api/health/` for uptime monitoring.

## Build phases

1. Architecture, accounts, base UI  **(done)**
2. Catalog, variants, inventory  **(done)**
3. Cart, checkout  **(done)**
4. Paystack, webhooks, orders  **(done)**
5. Wishlist, reviews, promo codes, size guide  **(done)**
6. Owner dashboard, analytics, customers, settings  **(done)**
7. Content pages, newsletter, back-in-stock, status emails, search suggestions, SEO  **(done)**
8. Celery email queue, automatic refunds, full API docs, browser test  **(done)**; deployment remains

`apps/marketing/` holds wishlist, reviews, promo codes, newsletter and back-in-stock.
Owner-editable text lives in `apps/core/content.py` (schema and defaults) and the `SiteSetting` table.
