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

1. From the repository root, run `python -m pip install -r requirements.txt`, `python manage.py migrate`, and `python manage.py check`. Use the existing React build and deployment steps above. For local frontend development, start Django with `python manage.py runserver 127.0.0.1:8000` and run `npm ci` in `frontend`. In PowerShell, set `$env:REACT_APP_API_URL = 'http://127.0.0.1:8000/api/'` in the frontend terminal before running `npm start`.
2. Sign in as a system manager with the configured staff OTP delivery channel. In `/admin/access`, grant the vehicle owner and driver their transport roles. Grant the conductor role if the vehicle uses one. An account can hold both owner and driver roles.
3. In `/admin/transport`, create an active route and vehicle, then assign a driver and optionally a conductor. Supply both the start and end in Africa/Nairobi time. An assignment conflicts if its time window overlaps another assignment for the vehicle or either crew member. Use the audited end action when a started assignment needs to end early. For a clerk to create assignments from `/staff/clerk/assignments`, grant the clerk role and an effective transport assignment duty scoped to that vehicle in `/admin/access`.
4. Sign in as assigned crew and open `/transport/crew` to view the shift, record KES collections, review assignment history, or report a missing assignment. Collection submissions to `/api/transport/collections/` carry the assignment ID, amount, optional notes, and a UUID `client_key`. Retry the identical payload with the same key after a lost response. Use a fresh key for each new collection. Offline drafts are stored for the signed-in account in the same browser. A draft saved on the phone still needs to sync to the server.

On Windows, `scripts/prepare_transport_acceptance.ps1` migrates and seeds a synthetic SQLite database under `.recovery/transport-acceptance`. It prompts for a private sample password and prints the sample usernames. Run Django against that database with `python manage.py runserver --settings=sacco.acceptance_settings`. These settings disable external OTP and M-Pesa delivery. The seeded crew account can sign in for manual checks. Staff endpoints can be exercised through the automated API tests, and interactive staff sign-in requires an environment with configured OTP delivery.

Run backend transport and staff scope tests with `python manage.py test core.tests_transport core.tests_transport_calculations accounts.test_workspaces --settings=sacco.acceptance_settings`. From `frontend`, run `npm test -- --watchAll=false --runInBand TransportCrew TransportOperations TransportReconciliation`.

Collections are operational totals. The repository also has shift closure, expense review, cash confirmation, owner views, and M-Pesa and reconciliation code. Remittance calculation requires a versioned, approved deduction rule with eligible expense categories. Settlement also requires approved allocation destinations and amounts, partial and excess payment rules, and an authorized ledger correction workflow. Validate these flows with the cooperative's policies and provider sandbox before launch.

## Integration limits to close with providers

- M-Pesa callbacks are checked against the requested amount, phone, and receipt before any ledger credit. A mismatch stays pending for manual reconciliation. Confirm callback reachability and reconciliation procedures with a real sandbox transaction before launch.
- CRB provider adapters are generic integration scaffolds. Validate authentication, consent, response fields, error handling, and scoring policy with the selected bureau; a successful HTTP response alone is not a production approval policy.
- ID verification uses the configured external provider only when credentials and provider behavior are confirmed. Keep staff review available for pending or flagged results.
- Back up the production database and private document store, define retention/access policies, and configure monitoring and alerting for failed OTP delivery, M-Pesa reconciliation, and provider outages.
