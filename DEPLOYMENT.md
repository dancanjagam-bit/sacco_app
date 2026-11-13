# Deployment and integration readiness

## Before deploying

1. Copy `.env.example` to `.env` for local use, or set the same values in the deployment secret store. Never commit `.env` or real provider credentials.
2. Generate a unique Django `SECRET_KEY`; set `DEBUG=False`, an explicit `ALLOWED_HOSTS`, and the HTTPS frontend origin in both `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS`.
3. Configure PostgreSQL for a shared deployment (`USE_POSTGRES=1`) and provide database credentials. The default SQLite database is intended for local development.
4. Configure SMTP before enabling email recovery. Configure Africa's Talking and install its Python SDK before offering SMS recovery. The app does not return OTPs in API responses or print OTP messages to logs.
5. Keep `CRB_PROVIDER=stub` only in development. It now records a `not_configured` result and cannot produce a clear credit decision. Before loan decisions rely on a bureau, obtain provider credentials and confirm the provider's current API contract and required member consent.
6. Use Daraja sandbox credentials first. For production, set `MPESA_ENV=production`, production shortcode/passkey/consumer credentials, and an externally reachable HTTPS `MPESA_CALLBACK_BASE_URL`. The callback route must be reachable at `/api/payments/mpesa/<payment-type>/`.
7. Configure the Smile Identity keys, API URL, and production environment only after confirming the partner account and verification flow. Without them, ID review remains manual/pending; do not treat a stubbed or incomplete provider response as verified identity.
8. Store ID documents and selfies in private storage. The authenticated protected-media endpoint checks ownership; the public web server must not expose the `media/` directory directly.

## Release steps

From the repository root, install `requirements.txt`, apply database migrations, collect static files, and run Django's deployment checks with the production environment loaded. Build the React frontend and serve it over HTTPS behind the same-origin API proxy (or configure the exact allowed frontend origin). Run the application with a production WSGI server and a persistent database; do not use Django's development server for public traffic.

## Transport operations phase 1

Apply the new migration with `python manage.py migrate`. Assign explicit `owner` and `driver` (and optional `conductor`) rows in `TransportRole` before creating vehicles or assignments; vehicle/route/assignment creation is available to active secretary, accountant, or superadmin staff through `/api/transport/vehicles/`, `/api/transport/routes/`, and `/api/transport/assignments/`. A crew member signs in and opens `/transport/crew` to see today's assignment and record collections. Each collection request requires a UUID `client_key`; clients should reuse that key for retries. Route and vehicle history is retained through protected foreign keys and assignment label snapshots.

The transport phase does not settle money. No approved deductions, collection allocation, or remittance formula was present in the repository; configure and approve those rules before shift closure or remittance calculation is enabled. Owner/crew portals beyond today's shift, expenses, cash handovers, M-Pesa remittance linkage, payment reconciliation, offline drafts, and linked ledger reversals remain later phases.

## Integration limits to close with providers

- M-Pesa callbacks are checked against the requested amount, phone, and receipt before any ledger credit. A mismatch stays pending for manual reconciliation. Confirm callback reachability and reconciliation procedures with a real sandbox transaction before launch.
- CRB provider adapters are generic integration scaffolds. Validate authentication, consent, response fields, error handling, and scoring policy with the selected bureau; a successful HTTP response alone is not a production approval policy.
- ID verification uses the configured external provider only when credentials and provider behavior are confirmed. Keep staff review available for pending or flagged results.
- Back up the production database and private document store, define retention/access policies, and configure monitoring and alerting for failed OTP delivery, M-Pesa reconciliation, and provider outages.
