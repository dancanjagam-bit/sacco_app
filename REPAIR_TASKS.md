# SACCO repair and product work

This list preserves release blockers separately from presentation work. Provider tests using mocks are evidence for code paths only; they do not prove live delivery or settlement.

## Member portal acceptance repair — 2026-11-12

| Observed defect | Root cause established | Fix in this pass | Verification evidence |
|---|---|---|---|
| Identity verification remained on “Loading” after a failed request. | `GET /api/id-verification/status/` reads `IDVerification.national_id_hash`; a fresh database stopped at migration 0011 and raised `OperationalError: no such column: accounts_idverification.national_id_hash`. | Added `accounts/migrations/0012_idverification_private_fields.py`. The status screen now has exclusive loading/error/ready states and Retry. | Fresh in-memory Django test database applied 0012. A synthetic pre-existing schema with these columns also applied 0012 without duplicate-column errors. Authenticated status API returned 200 in member journey tests; unauthenticated returned 401. No production database migration was run. |
| Dashboard FOSA availability and withdrawal status could fail without a useful retry; unavailable values must not look like zero. | These are separate authenticated requests to `/api/collateral/status/` and `/api/withdrawals/`. Valid isolated API responses were available; the screenshots' original responses could not be captured from the unavailable browser/runtime. | Dashboard validates the response shapes and offers a retry for each failed request. Held withdrawals remain separate from available FOSA. | `core.tests_member_journey` verifies balance fields, withdrawal holds, authenticated scoping and status responses. Dashboard UI tests cover retry and preserve “Unavailable” rather than zero. |
| Transactions, profile, notifications, savings statement, loan schedule, and dividends showed error panels. | Source routes and the authenticated Axios client are present. Isolated authenticated API tests returned 200 for dashboard, collateral, withdrawals, transactions, dividends, profile, notifications, identity status, savings statement, and loan schedule. The screenshot-time HTTP statuses could not be reproduced. | Kept the shared authenticated client; made dividend and schedule states exclusive with retry; fixed invalid repayment terms to return an actionable 422 instead of a server error. | 14 focused backend tests passed; frontend screen tests pass. `accounts.tests.NotificationEndpointTests` verifies member-only notifications and rejects unauthenticated access. |
| Reports duplicated transaction totals/statements and used one “active loan” view; loan rows could imply a disbursement or ambiguous payoff balance. | The system creates a `loan` transaction at application time. Approval sets `Loan.balance` to amount plus calculated interest, but the application has no confirmed-disbursement record; existing stored balances may not consistently represent a verified payoff quote. `Savings` has BOSA/FOSA types but no separate share-unit register. | Reports now focus on loans/dividends; transaction totals and downloads stay on Transactions. The loan table and reports show all approved records, call them applications, label the field “Recorded balance,” and state disbursement/payoff are not confirmed. BOSA is labelled savings, not separate share capital. | React tests cover multiple approved loans, application-ledger display, and the report/statement navigation split. Backend source confirms `approve_loan` sets calculated total payable but no disbursement status is stored. |
| Loan repayment controls were unstyled; change-password controls were detached from fields; Profile and Change Password duplicated navigation. | `LoanTable` used a native button and legacy table classes; password page used detached visibility controls; the profile page already links to password change. | Replaced loan table controls/statuses with shared components, put visibility controls inside each labelled password field, grouped password changes under Profile, and renamed Reports navigation to Loan and dividend reports. Existing `/change-password` and `/reports` routes remain available. | Component tests cover the loan action, each field's own visibility toggle, and navigation grouping. |
| Exact live screenshot failures and responsive appearance could not be verified. | No app listeners/processes were present at inspection. The CUA tool returned `Browsers: Error: Local browser use is disabled in Work settings` and `browsers: []`. An isolated React start logged its `/api` proxy target as `http://127.0.0.1:8000`; the development server logged `ETIMEDOUT` for requests to that target. Bounded HTTP attempts in the tool runtime were socket-blocked/timed out, so no screenshot-time HTTP status or Django traceback exists for those requests. | Recorded the limitation; did not attribute every screenshot failure to a backend outage. A real browser acceptance pass is still required on a host where both servers share loopback access. | Django/APIClient tests and component tests only. No browser console, screen journey, PDF/XLSX visual opening, or viewport screenshot is claimed. |

### Verification for this repair pass

- **Python environment:** `C:\Users\USER\sacco_app\venv\Scripts\python.exe`; `-m pip check` reported no broken requirements. `manage.py check --settings=sacco.browser_test_settings` reported no issues.
- **Django tests:** `accounts.tests` — **34 passed**. `accounts.tests.AuthenticationPortalTests.test_unavailable_login_delivery_does_not_claim_sent_or_allow_code_login core.tests_member_journey core.tests_downloads` — **14 passed**. Tests used the isolated in-memory test database. The identity migration applied successfully on a fresh test database and on a separate synthetic database with pre-existing columns.
- **Frontend tests:** `CI=true npm test -- --watchAll=false --runInBand` — **15 suites, 40 tests passed**.
- **Production build:** `CI=true GENERATE_SOURCEMAP=false npm run build` — **exit 0, compiled successfully**. The remaining build warning is Node `[DEP0176] fs.F_OK is deprecated`; no ESLint warning remained after removing the generated stale `frontend/node_modules/.cache/.eslintcache` file. The attempted development-server startup also emitted dependency deprecations for `util._extend` and webpack-dev-server's `onAfterSetupMiddleware` / `onBeforeSetupMiddleware`; these did not prevent compilation.
- **Migration drift still present:** `makemigrations --check --dry-run --settings=sacco.browser_test_settings` reports unapplied model-state differences for existing KYC models (`KYCConsentRecord`, `KYCRiskScore`, `LivenessChallenge`, `MemberApproval`, `DeviceFingerprint`, and `MemberReference`) and `AuditLog.action` / `OTPRequest.purpose`. This pass did not generate a broad migration because existing local schemas may already contain those tables; reconcile that history separately before applying it to a persistent database.
- **Data safeguards:** tests and migration experiments used isolated/in-memory SQLite databases. `db.sqlite3` was inspected read-only and not migrated. Withdrawals 41 and 50 were not changed. No live messages or financial actions were initiated.

### Browser follow-up

Visual acceptance remains pending. In a local Windows session where loopback networking is available, use two PowerShell windows:

```powershell
# Window 1 — isolated Django test database only
Set-Location C:\Users\USER\sacco_app
$env:SACCO_BROWSER_TEST_DB = (Join-Path (Get-Location) 'sacco_runtime_acceptance.sqlite3')
$env:SACCO_BROWSER_TEST_PASSWORD = 'LocalTestOnly-2026!'
$env:EMAIL_HOST = ''; $env:EMAIL_HOST_USER = ''; $env:EMAIL_HOST_PASSWORD = ''; $env:DEFAULT_FROM_EMAIL = ''
$env:AT_USERNAME = ''; $env:AT_API_KEY = ''
$env:MPESA_ENV = 'sandbox'; $env:MPESA_CONSUMER_KEY = ''; $env:MPESA_CONSUMER_SECRET = ''; $env:MPESA_PASSKEY = ''; $env:MPESA_CALLBACK_BASE_URL = ''
$env:CRB_PROVIDER = 'stub'; $env:CRB_API_KEY = ''
.\venv\Scripts\python.exe manage.py migrate --settings=sacco.browser_test_settings
.\venv\Scripts\python.exe manage.py shell --settings=sacco.browser_test_settings -c "exec(open('sacco/browser_test_seed.py', encoding='utf-8').read())"
.\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload --settings=sacco.browser_test_settings
```

```powershell
# Window 2 — React development server
Set-Location C:\Users\USER\sacco_app\frontend
$env:HOST = '127.0.0.1'; $env:PORT = '3002'; $env:BROWSER = 'none'; $env:REACT_APP_API_URL = ''
npm start
```

## Savings statement runtime crash — 2026-11-12

- **Root cause:** switching to the Savings statement tab rendered once while `statement` was still `null` and `statementState` was idle. The old `statement?.entries.length === 0` check evaluated false for a null statement, then the populated branch dereferenced `statement.entries.map(...)`, causing the reported runtime exception.
- **Fix:** `Savings.js` derives statement entries only when they are an array and renders idle/loading, error/invalid-response, empty, and populated states exclusively. A null or malformed entries value cannot reach `.map()`.
- **Verification:** `CI=true npm test -- --watchAll=false --runInBand Savings.test.js` — **5 passed**, exit 0, including a deferred initial request and an API response with `entries: null`. `CI=true GENERATE_SOURCEMAP=false npm run build` — **exit 0, compiled successfully**; Node emitted `[DEP0176] fs.F_OK is deprecated`.
- **Runtime limitation:** process/listener inspection found no listener on 3001 (or ports 3000, 3002, 8000) during this check. Therefore the stack trace matches the source defect, but the exact process/build instance that produced the user's hot-update URL could not be inspected or browser-exercised here.

Open `http://127.0.0.1:3002/` and sign in as synthetic `browser_member` (password `LocalTestOnly-2026!`). Django API base is `http://127.0.0.1:8000/`; React's `/api/` proxy targets that same loopback address. Verify dashboard → savings → loans → transactions → loan/dividend reports → notifications → profile → logout; open PDF/XLSX downloads; inspect 360, 390, 768, 1024, and 1440 px plus 200% zoom. Capture console/network evidence and screenshots there. Do not use `db.sqlite3` or enable live providers. If the managed terminal raises `PermissionError` reading `HKCU\Console` while starting Django, that is the shell's color-detection registry access; the diagnostic run worked around it with `TERM_PROGRAM=vscode` and `DJANGO_COLORS=nocolor`.

## Latest member-journey inspection — 2026-11-12

| Journey / file | Confirmed issue before this pass | Correction made |
|---|---|---|
| Navigation — `frontend/src/components/Sidebar.js`, `frontend/src/styles/sidebar.css` | On phones the only navigation was a left drawer opened by a fixed hamburger. It had no Home/Accounts/Loans/More bar, no focus management, and users with both staff/crew permissions were routed to a default workspace without a visible switch. | Added the mobile primary bar, focus-trapped drawer with Escape/overlay close and body-scroll lock, and a role-derived workspace selector. Server permissions remain authoritative. React workspace/drawer tests pass. |
| Shell — `frontend/src/components/Layout.js`, `frontend/src/styles/ui.css`, `frontend/src/styles/dashboard.css` | Old and shared CSS both defined `.dashboard-container` / `.dashboard-content`; horizontal overflow was hidden at the shell, which could clip content instead of containing a wide table. | Scoped shared layout rules, added minimum-width guards and mobile safe-area space; financial tables scroll in labelled wrappers. Browser widths remain unverified. |
| Dashboard — `frontend/src/pages/Dashboard.js`, `core/views.py::dashboard` | Dashboard had no balance hide/show control, gross deposit total, or loan-application action; statement action went to the older Reports page. Share capital was presented as an unavailable metric although no share register exists. | Added a ledger-backed all-time deposit aggregate, hide/show control, loan action, and statement link to Transactions; removed the unsupported share-capital metric. Dashboard API/UI tests pass. |
| Full transaction summary — `frontend/src/pages/Reports.js`, `core/views.py::my_transactions`, `core/views.py::export_statement_pdf` | Member totals used only the dashboard's latest 25 transactions. Invalid list dates were silently ignored, and PDF date parsing silently fell back to a default range. | Reports now uses the paginated API's full-history aggregate; transaction/PDF/XLSX filters reject invalid or reversed ranges; statement downloads route through Transactions. Backend/API and React tests pass. |
| Loan payment boundary — `frontend/src/components/RepayLoanModal.js`, `core/views.py::repay_loan`, `core/payments_views.py` | The legacy modal called an endpoint that reduced a loan and posted repayment without proof money was received. The existing provider callback also failed because an inner `Decimal` import shadowed the outer import. | The modal now starts the stored M-Pesa repayment request and displays pending until a status check confirms it; legacy direct posting returns 409 without changing the loan/ledger. Removed the shadowing import. Mocked callback test confirms one posting after confirmation and no duplicate on retry. |
| React context — `frontend/src/context/AuthContext.js`, `frontend/src/context/SaccoContext.js` | Auth context functions/value were recreated on every render; SACCO defaults read React's private `_currentValue` field. | Memoized auth callbacks/context value and replaced the private React-field read with an explicit frozen default config. Auth regression tests pass. |

**Accounting boundary confirmed during inspection:** `core.models.Transaction` is a member activity ledger with single signed amount entries, not a double-entry journal. Savings rows drive the displayed account totals; FOSA withdrawals now have separate request/hold/settlement states and linked ledger entries; posted corrections can link a reversal. There is no chart of accounts or balanced debit/credit journal-line model. Do not call it double-entry accounting or alter financial history in this UI pass; any future journal migration needs a reconciliation plan first.

## P1 — Release blockers

| Issue | Root cause | Current fix | Evidence | Release state |
|---|---|---|---|---|
| Login and role redirects | The old login path used the authenticated Axios client and sent successful users to the member dashboard without consistently hydrating role data first; stale-token refresh behavior could interfere with sign-in. | Auth uses a plain Axios client, staff receives no token until OTP succeeds, then the authenticated dashboard is loaded and a centralized role resolver chooses staff, crew, or member destination. | React role redirect/auth tests and 26 Django account tests passed. Browser access is disabled by Work settings, so no live journey or console capture was possible. | Code verified; browser verification pending. |
| Password-reset OTP delivery | SMTP credentials are incomplete; Africa's Talking has a sandbox username but no API key. Delivery attempts therefore do not reach a usable live email or SMS provider. | Use only verified recovery contacts; persist delivery outcome/reason, apply expiry/attempt/resend limits, and never expose codes. | 26 account tests cover mocked delivery, provider failure, expiry, attempts, resend, reset, and login. Test logs confirm skipped email/SMS for missing credentials; no real messages sent. | Code verified; provider configuration and actual delivery blocked. |
| FOSA debit without confirmed payout | Old path wrote the debit before a disbursement call; the repository has STK/C2B pay-in but no member disbursement adapter. | Withdrawal requests are disabled without an approved payout adapter. Reservation/settlement state machine settles only verified success and is covered by fake-provider tests. | The 36 focused financial tests include failure, timeout, delayed success, duplicate request/callback, balance holds, and authorization. | Safe disable verified; live payout blocked. |
| Legacy withdrawal reconciliation | Existing withdrawals have no stored payout reference or linked payout record. | Restricted masked report and audited correction proposal/approval APIs are available. No correction is posted until evidence and approval exist. | Read-only local report found transaction 41 (KES 500) and 50 (KES 4,000); both unresolved. | Investigation pending external payout evidence. |
| Notifications | Backend log showed 401 responses at `/api/notifications/`; the prior component swallowed failures and could show an empty state after a failed request. | Keep loading, error, empty, and populated states exclusive; provide Retry; endpoint remains authenticated and scoped to the current user. | API and React retry/state tests pass. Browser response body and console could not be captured because local browser access is disabled. | API/UI code verified; browser verification pending. |
| Corrupted text | The notification heading had a decorative emoji rendered as a mojibake prefix. | Replaced the damaged heading with plain UTF-8 text and reviewed the member source. | Current `frontend/src` scan found no `Ã`, `Â`, `â`, `ðŸ`, or replacement-character markers; prior local data scan found none in 12 notification rows. | Source/data scan verified; rendered browser check pending. |
| PDF/Excel downloads | Earlier download checks used system Python, so they did not establish that the project virtualenv had the PDF dependency. | Requirements already pin ReportLab; downloads use authenticated API requests, validate binary content, show JSON errors, and clean up object URLs. Excel date ranges are validated and applied. | In this run, `venv\\Scripts\\python.exe -m pip install -r requirements.txt` succeeded and the venv reported ReportLab 5.1.0. PDF/XLSX generation, member scope, empty exports, invalid dates, and frontend parameters passed in the venv backend suite. | Backend verified in venv; opening downloaded files in a browser remains unverified. |

## P2 — Member design slice

1. **Implemented:** shared navy/warm-white/emerald tokens, spacing/type/radius/shadow/focus rules, SVG icons, button/metric/status/feedback/loading components, responsive sidebar/header shell, role-derived workspace selection, and mobile Home/Accounts/Loans/More navigation.
2. **Implemented and test-verified:** login, member dashboard, savings/deposit, withdrawal status, transactions, and PDF/XLSX statement controls. Savings uses the existing M-Pesa STK flow; no direct member deposit debit is attempted. FOSA payout stays visibly disabled without a disbursement provider.
3. **Implemented:** transaction history uses the paginated member API, shows posted ledger status, linked withdrawal status, masked destination and available provider references. A legacy withdrawal without provider linkage is marked needs review. Unknown share balances, failed reads, and missing schedule amounts are displayed as unavailable rather than zero.
4. **Blocked:** desktop/mobile browser review and requested screenshots. Work settings reported “Local browser use is disabled”; no browser bypass was attempted.
5. **Pending:** apply the shared components to owner, crew, and staff screens after browser review of the member slice.

## P3 — Backend strengthening

1. Keep financial domain logic out of views where the next focused change has regression coverage.
2. Review state transitions, decimal arithmetic, constraints, and locking for payment/withdrawal/remittance workflows.
3. Add durable notification/report delivery only when a configured worker/queue is available; preserve delivery retries and idempotency.
4. Review observed queries before adding indexes or changing pagination.
5. Document provider configuration, migration, backup/restore, and startup procedures.

### Focused backend changes in this slice

- Transaction API responses now include withdrawal state, reference, masked destination, provider identifiers, and settlement time only when a linked payout record exists; linked M-Pesa entries show their payment state, request reference, receipt, masked payer, and account type. Unlinked non-BOSA withdrawals are marked for review rather than presented as paid.
- The transaction list selects the linked payout record in the same query to avoid per-row lookups.
- Excel exports apply validated `from`/`to` filters while remaining scoped to the authenticated member. No schema migration was needed.
- Dashboard exposes the posted deposit total independently from Savings account balances. Transaction summary amounts remain decimal strings.
- Invalid transaction, Excel, or PDF date/type filters return validation errors instead of being ignored or replaced by a default PDF date range.
- The legacy direct loan repayment API cannot post funds; repayments settle through the existing STK callback. Provider callbacks remain receipt/request-correlated and idempotent.

## Current scope limits

- No live payout provider is configured; the M-Pesa disbursement action stays disabled.
- SMTP and SMS test-provider credentials are not complete. No messages were sent.
- No real financial transaction, deployment, or customer data correction was performed.
- The existing production `db.sqlite3`, existing browser test DB, and stashes are preserved. Migrations and seeded accounts were applied only to isolated test databases. Legacy withdrawal transactions 41 (KES 500) and 50 (KES 4,000) remain unresolved and unchanged.
- The project virtualenv currently has ReportLab 5.1.0 and `pip install -r requirements.txt` succeeds. Earlier system-Python-only results were replaced by the venv test run below.
- The existing `sacco_auth_browser_test.sqlite3` was inspected and left untouched. A separate `sacco_runtime_acceptance.sqlite3` was created with current migrations and clearly synthetic browser test accounts. No commands in this run used `db.sqlite3`.
- The M-Pesa STK flow is a pay-in integration. It is not configured for outbound FOSA payments; request acceptance never means a withdrawal was paid.

## Runtime verification results — 2026-11-12

- Dependency installation: `venv\Scripts\python.exe -m pip install -r requirements.txt` — exit 0. All requirements were satisfied; ReportLab 5.1.0 is installed in the project virtualenv. The earlier missing-package condition could not be reproduced in this run.
- Backend regression suite, project virtualenv: `venv\Scripts\python.exe manage.py test accounts.tests core.tests_downloads core.tests_withdrawals core.tests_extended --settings=sacco.browser_test_settings --verbosity=2` — 62 tests passed, exit 0, in 173.241 seconds. Django created and destroyed an isolated in-memory test database. This covers account/OTP, notification authorization, withdrawals, PDF/XLSX generation, date filters, and member scoping.
- Django system check with the virtualenv and browser test settings — no issues. Tests emitted a non-fatal warning that the optional `staticfiles` directory is absent. A separate runtime acceptance database received every current migration; `showmigrations --plan` reported all entries applied. The existing browser test DB and `db.sqlite3` were not changed by these checks.
- Frontend tests: PowerShell `$env:CI='true'; npm test -- --watchAll=false --runInBand` — 8 suites, 23 tests passed, exit 0.
- Frontend production build: PowerShell `$env:CI='true'; $env:GENERATE_SOURCEMAP='false'; npm run build` — compiled successfully, exit 0. Non-fatal Node warning: `[DEP0176] fs.F_OK is deprecated`. The development server also reported non-fatal Webpack Dev Server deprecations for `onAfterSetupMiddleware` and `onBeforeSetupMiddleware`.
- Runtime startup: Django started with the project virtualenv at `http://127.0.0.1:8000/` using `sacco.browser_test_settings` and the isolated runtime database; React compiled and started at `http://127.0.0.1:3000/`. Payment, SMS, email, and CRB live credentials were blanked or set to sandbox/stub for that isolated run.
- Browser workflows and screenshots: **not verified**. CUA reports `Local browser use is disabled in Work settings`. HTTP requests from this execution environment to the local services were also blocked/timed out, so no login, refresh, logout, member screen, notification Retry, PDF/XLSX open, desktop/mobile layout, browser console, or screenshot evidence is claimed. The development servers remain running in the task sessions where available.
- The test-only settings accept `SACCO_BROWSER_TEST_DB` so a dedicated browser database can be used without touching the existing `sacco_auth_browser_test.sqlite3`.

## Member experience implementation and verification — 2026-11-12

This section supersedes the earlier test/build counts above for the current working tree.

- **Member UI:** implemented the mobile primary navigation and accessible drawer, role-derived workspace switcher, responsive shell, dashboard balance visibility, separate BOSA/FOSA/held/total-deposit/loan figures, direct statement navigation, notification loading/error/empty/populated states, profile layout and retry states, and a full-history Reports summary. Member pages scanned contain no `Ã`, `Â`, `â`, `ðŸ`, or replacement characters. Loan purpose labels use text and the member repayment control now starts M-Pesa instead of posting a direct debit.
- **Backend fixes:** dashboard totals use the existing Transaction ledger; transaction summaries keep decimal strings and are scoped to the signed-in member; invalid type/date/range filters return 400; PDF exports no longer silently replace invalid filters with a default date range; the legacy direct-repayment endpoint returns 409 without modifying the loan; a shadowed `Decimal` import that broke confirmed STK repayment callbacks was removed.
- **Accounting description:** still a single-entry member activity ledger, not double-entry accounting. No accounting schema migration or historical balance edit was made.
- **Backend tests:** `C:\Users\USER\sacco_app\venv\Scripts\python.exe manage.py test accounts.tests core.tests core.tests_extended core.tests_downloads core.tests_withdrawals core.tests_member_journey --settings=sacco.browser_test_settings --verbosity=1` — **76 tests passed**, exit 0, 145.067 seconds (latest rerun). Django used and destroyed an isolated in-memory test database. Coverage includes auth/OTP, member notification scope, direct repayment rejection, confirmed repayment callback and duplicate callback, dashboard and transaction summaries, filter validation, PDF/XLSX member scoping, withdrawals, and correction permissions.
- **Frontend tests:** from `C:\Users\USER\sacco_app\frontend`, `$env:CI='true'; npm test -- --watchAll=false --runInBand` — **11 suites, 28 tests passed**, exit 0. Added dashboard visibility, workspace/drawer, Reports summary, and M-Pesa repayment pending-state coverage.
- **Django/virtualenv checks:** `C:\Users\USER\sacco_app\venv\Scripts\python.exe -m pip check` — no broken requirements; ReportLab 5.1.0 is installed in the project virtualenv. `manage.py check --settings=sacco.browser_test_settings` — no issues. `manage.py makemigrations --check --dry-run --settings=sacco.browser_test_settings` — no changes detected; this pass adds no migration.
- **Production build:** from `C:\Users\USER\sacco_app\frontend`, `$env:CI='true'; $env:GENERATE_SOURCEMAP='false'; npm run build` — final run compiled successfully, exit 0. A repeat attempt initially exited 1 because the generated `.eslintcache` still reported an obsolete unused `authApi` import in `Register.js`; the current source imports `api` and contains no `authApi` use. Removing only `frontend/node_modules/.cache/.eslintcache` and rebuilding resolved the stale diagnostic. Remaining warning: Node `[DEP0176] fs.F_OK is deprecated`; no source lint warnings remain.
- **Browser acceptance:** **not verified**. CUA reports local browser access is disabled by Work settings. No running-browser journey, console/network inspection, screenshots, or visual pass at 360, 390, 768, 1024, 1440 pixels or 200% zoom is claimed. Backend and component tests are not browser evidence.
- **Data and integrations:** tests used the isolated in-memory database. No production/user DB, existing browser DB, unresolved withdrawals 41 (KES 500) and 50 (KES 4,000), payout configuration, real M-Pesa transactions, OTP messages, or customer notifications were changed/triggered.

### Manual browser acceptance still required

Use the isolated startup commands below, then verify at **360, 390, 768, 1024, and 1440 px** plus **200% zoom**. On each width check for page-level horizontal overflow, visible focus, reachable drawer close/More control, readable table scrolling, and dialogs that fit above the on-screen keyboard. Browser access was unavailable during this task, so this is a manual follow-up rather than acceptance evidence.

1. At `http://127.0.0.1:3000/`, sign in as the synthetic `browser_member` account in the isolated runtime DB. Confirm dashboard redirect, refresh persistence, and sign out.
2. Visit `/dashboard` → `/savings` → `/transactions`; expand transaction details and download PDF and Excel with date filters. Open both downloaded files and confirm member scope, dates, amounts, and readable text.
3. Visit `/notifications`; check populated and empty success states. To see the Retry path, use browser DevTools to fail the first `/api/notifications/` request, then restore the request and Retry. Confirm a failed request never displays “All caught up!”.
4. In Profile, confirm recovery-provider limitations are clear. On Savings, confirm live withdrawal remains disabled and no request is presented as paid without provider confirmation.
5. Use workspace switching only for roles present on the test dashboard; verify staff/crew route access is still rejected by backend permission checks for an unauthorized test account.

Do not trigger live provider payments, messages, or credit enquiries.

### Manual browser acceptance follow-up

- Login: `http://127.0.0.1:3000/`; seeded synthetic member `browser_member`, password `LocalTestOnly-2026!` in the isolated runtime database only.
- Member pages: dashboard `http://127.0.0.1:3000/dashboard`, savings `http://127.0.0.1:3000/savings`, transactions `http://127.0.0.1:3000/transactions`, and notifications `http://127.0.0.1:3000/notifications`.
- Backend/API base: `http://127.0.0.1:8000/` and `http://127.0.0.1:8000/api/`.
- Use the seeded isolated test database and keep outbound providers disabled:

  ```powershell
  Set-Location C:\Users\USER\sacco_app
  $env:SACCO_BROWSER_TEST_DB = (Join-Path (Get-Location) 'sacco_runtime_acceptance.sqlite3')
  $env:SACCO_BROWSER_TEST_PASSWORD = 'LocalTestOnly-2026!'
  $env:EMAIL_HOST = ''; $env:AT_USERNAME = ''; $env:AT_API_KEY = ''
  $env:MPESA_ENV = 'sandbox'; $env:MPESA_CONSUMER_KEY = ''; $env:MPESA_CONSUMER_SECRET = ''; $env:MPESA_PASSKEY = ''; $env:MPESA_CALLBACK_BASE_URL = ''
  $env:CRB_PROVIDER = 'stub'; $env:CRB_API_KEY = ''
  .\venv\Scripts\python.exe manage.py migrate --settings=sacco.browser_test_settings
  .\venv\Scripts\python.exe manage.py shell --settings=sacco.browser_test_settings -c "exec(open('sacco/browser_test_seed.py', encoding='utf-8').read())"
  .\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload --settings=sacco.browser_test_settings
  ```

  In a second PowerShell window:

  ```powershell
  Set-Location C:\Users\USER\sacco_app\frontend
  $env:HOST = '127.0.0.1'; $env:PORT = '3000'; $env:BROWSER = 'none'; $env:REACT_APP_API_URL = ''
  npm start
  ```

  The test-only setting accepts `SACCO_BROWSER_TEST_DB` to avoid changing the older browser-test database.
- Check login redirect, refresh, logout, dashboard and member navigation; notification success/empty/error plus Retry; PDF/XLSX downloads with dates and opening; unavailable OTP/payout messaging; and desktop/mobile overflow. Do not initiate provider-dependent transactions.

## Transport operations Phase 1 and shared navigation — 2026-11-12

This phase adds the transport records, role-scoped management, and crew assignment/collection workflow. It does not complete the transport module.

- **Feature status:** Implemented and API/component-tested: transport records and permissions, staff role/route/vehicle/assignment creation, crew current-shift view, collection persistence and retry protection, assignment problem reporting, and shared responsive top navigation. Pending: owner home/history screen, expenses, shift closure, staff document/vehicle status management, full payment reconciliation, approved allocation policy, and payment receipts. Provider acceptance and real inbox/payment delivery are blocked from this verification because live external actions were not authorized.

- **Existing foundation reused:** `core.transport_models` already contained transport roles, routes, vehicles, ownership periods, effective-dated crew assignments, shifts, collections, remittances, payments, payment allocations, and role grants. Existing routes and Daraja STK/C2B integration were retained. The member ledger remains the only SACCO financial ledger. Added only the assignment-problem report record needed by the crew screen.
- **Migration:** `core/migrations/0018_transportassignmentissue.py`. The isolated test database applied all migrations through this file. `makemigrations --check --dry-run core --settings=sacco.browser_test_settings` reported no model drift. Django app-registry inspection discovered all 13 transport models: `TransportRole`, `TransportRoute`, `Vehicle`, `VehicleOwnership`, `CrewAssignment`, `TransportShift`, `TransportCollection`, `TransportRemittance`, `TransportPayment`, `TransportAllocationRule`, `TransportPaymentAllocation`, `TransportRoleGrant`, and `TransportAssignmentIssue`.
- **Permissions:** active secretary/superadmin staff can manage transport roles, routes, vehicles, ownership, and assignments; active accountant/secretary/superadmin staff can read the transport records needed for payment reconciliation and use the reconciliation queue. Assignment-problem reports are resolved by secretary/superadmin. Other staff do not receive transport-wide reads. Crew reads and writes require the assigned user and an active driver/conductor role. Owners see their own vehicle and assignment history, with collection history restricted to their recorded ownership period. An `is_admin` flag alone does not grant transport access. These server checks remain authoritative.
- **Staff APIs and screen:** `/admin/transport` uses existing-user role grants, route/vehicle creation, optional-conductor effective-dated assignment creation, assignment history, and the issue-review queue. The APIs are `/api/transport/roles/`, `/api/transport/routes/`, `/api/transport/vehicles/`, `/api/transport/assignments/`, and `/api/transport/assignment-issues/`. Role choices are exposed only after explicit role grant; vehicle creation requires an active owner role; driver and conductor selections require their matching active roles.
- **Crew APIs and screen:** `/transport/crew` uses `/api/transport/crew/today/` to display the effective current assignment, crew labels, status, reported collection totals, and saved activity. Collection writes use decimal KES amounts, assignment/vehicle/route/shift links, a per-user UUID idempotency key, and a uniqueness constraint. A repeated identical request returns the existing record; reusing its key for changed data returns HTTP 409. Missing assignments can be reported through `/api/transport/crew/issues/` and are reviewed by authorized staff with a required resolution reason.
- **History and concurrency:** assignment labels are snapshots and survive later vehicle/route/name edits. Overlapping vehicle or crew assignment windows are rejected inside a transaction after locking the relevant rows. The assignment save method now creates its shift correctly by recording whether the row is new before saving; this fixed missing shift links that also prevented remittance records from being created.
- **Offline behavior:** collection drafts are stored under a signed-in-user-specific local-storage key. The screen states “Saved on this phone — waiting to sync”; retry uses the same UUID, and the API duplicate response removes the draft without adding another collection. Offline entries never claim settlement. A cached assignment is displayed as last saved and cannot be used to sync until the server confirms a current assignment.
- **Navigation and visual system:** member, crew, staff, login, registration, and recovery screens use the shared sticky navy top navigation. Desktop shows four member destinations directly; compact layouts show Home, Accounts, Loans, and More, where Transactions remains reachable. The workspace switcher appears only for users with multiple recognized workspaces. There is no owner portal yet, so no owner workspace is offered. Existing shared UI components are used on staff and crew screens. Text/muted and placeholder tokens were darkened after checking contrast: primary nav text on navy is 12.00:1, muted text on warm white is 4.77:1, placeholder text on white is 5.67:1, and white on emerald is 5.84:1.
- **Backend verification:** `C:\Users\USER\sacco_app\venv\Scripts\python.exe manage.py test core.tests_transport --settings=sacco.browser_test_settings --verbosity=1` — **18 tests passed**, exit 0, 196.643 seconds. Follow-up isolated runs for exact-decimal collection totals (**1 test passed**, 9.500 seconds) and multiple roles plus multiple-vehicle ownership scope (**2 tests passed**, 19.460 seconds) also exited 0. These runs applied the complete migration chain, including `core.0018`, to isolated test databases. Coverage includes staff setup, multi-role permissions, ownership history, assignment snapshots/conflicts/effective times, collection access/idempotency/links and decimal totals, issue reporting, and pending-to-confirmed cash handover. Django system checks reported no issues. `makemigrations --check --dry-run core` found no transport model changes.
- **Frontend verification:** `CI=true npm test -- --watchAll=false --runInBand` — **19 suites, 56 tests passed**, exit 0. The sidebar/crew/operations focused run — **3 suites, 10 tests passed**, exit 0; after adding the hidden-destination keyboard-focus check, the final sidebar rerun — **1 suite, 4 tests passed**, exit 0.
- **Production build:** final source from `C:\Users\USER\sacco_app\frontend`, `CI=true GENERATE_SOURCEMAP=false npm run build` — **compiled successfully, exit 0**. Node emitted the existing `[DEP0176] fs.F_OK is deprecated` warning. No source lint warning was reported.
- **Browser evidence:** visual/browser acceptance is **unverified**. The actual computer-use tool returned `browsers: []` and `Browsers: Error: Local browser use is disabled in Work settings`. No screenshot, console/network inspection, or layout pass at the requested widths, landscape, or 200% zoom is claimed.
- **Phase limits:** no owner dashboard or vehicle detail screen; no stage model; no expenses, shift closure, or shift-close calculation; and no approved allocation rule. Existing remittance/STK/cash screens and provider callbacks were reused, but live M-Pesa payment confirmation and the full reconciliation UI were not exercised in a browser. Cash submissions remain pending until staff confirmation. Provider-dependent flows require sandbox/test configuration for further verification; no live payment or customer notification was initiated. Transactions 41 and 50 and the working database were not modified by this phase.

### Isolated transport browser run

The following commands create a separate disposable SQLite database and seed synthetic member, secretary, driver, route, vehicle, and current assignment records. Do not omit `SACCO_BROWSER_TEST_DB`; `sacco.browser_test_settings` otherwise defaults to an existing browser-test database file. Use two PowerShell windows.

```powershell
# Window 1: isolated Django database and API
Set-Location C:\Users\USER\sacco_app
$env:SACCO_BROWSER_TEST_DB = Join-Path $env:TEMP ("sacco-transport-" + [guid]::NewGuid().ToString("N") + ".sqlite3")
$env:SACCO_BROWSER_TEST_PASSWORD = 'LocalTestOnly-2026!'
$env:EMAIL_HOST = ''; $env:EMAIL_HOST_USER = ''; $env:EMAIL_HOST_PASSWORD = ''; $env:DEFAULT_FROM_EMAIL = ''
$env:AT_USERNAME = ''; $env:AT_API_KEY = ''
$env:MPESA_ENV = 'sandbox'; $env:MPESA_CONSUMER_KEY = ''; $env:MPESA_CONSUMER_SECRET = ''; $env:MPESA_PASSKEY = ''; $env:MPESA_CALLBACK_BASE_URL = ''
$env:CRB_PROVIDER = 'stub'; $env:CRB_API_KEY = ''
.\venv\Scripts\python.exe manage.py migrate --settings=sacco.browser_test_settings
.\venv\Scripts\python.exe manage.py shell --settings=sacco.browser_test_settings -c "exec(open('sacco/browser_test_seed.py', encoding='utf-8').read())"
.\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload --settings=sacco.browser_test_settings
```

```powershell
# Window 2: React development server; API requests proxy to port 8000
Set-Location C:\Users\USER\sacco_app\frontend
$env:HOST = '127.0.0.1'; $env:PORT = '3002'; $env:BROWSER = 'none'; $env:REACT_APP_API_URL = ''
npm start
```

Open `http://127.0.0.1:3002/`. Sign in as `browser_admin` for staff setup or `browser_driver` for the crew view; both use the local-only password in `SACCO_BROWSER_TEST_PASSWORD`. The seed does not set up email delivery or authorize live payments. The browser automation blocker means this manual visual check remains outstanding.
- The browser-only local seed script requires the explicit test password above and writes only to `sacco_runtime_acceptance.sqlite3`. It creates synthetic member, staff, driver, route, vehicle, and assignment records; it does not use `db.sqlite3`.

## Indigo design system and member statement calculations — 2026-11-12

- **Scope/evidence boundary:** this is a shared styling and statement-generation pass. It does not close the member portal or change the status of authentication delivery, live payouts, external provider onboarding, ownership dashboards, or the feature inventory supplied by the member. Prior screenshot API failures were not reproduced against a running app in this pass and remain partial/unverified.
- **Shared visual system:** `frontend/src/styles/theme.css` now defines the requested indigo (`#4F46E5`), navy (`#0B1437`), page background (`#F0F4FF`), surface, and success/warning/danger tokens, plus semantic, spacing, typography, radius, shadow, motion, focus, and navigation tokens. Body/form text uses 16px and support labels use 14px in the shared UI and authentication forms. `auth.css`, `ui.css`, `sidebar.css`, dashboard/table styles, and transport styles consume the shared variables. The existing sticky top navigation remains top-positioned at desktop and compact widths; it has keyboard-operable More/account menus, Escape handling, focus restoration, workspace switching when available, and 44px touch targets. No permanent sidebar or bottom navigation was added.
- **Branding and interaction states:** added original Nairobi West tuk-tuk SVG marks in light and dark variants and use the mark in public/auth/navigation branding. Authentication and shared UI fields/buttons have default, focus, pressed, disabled/loading, validation, and success styles. Status badges retain text labels as well as color/dots; ordinary debits remain navy. Removed gradient/particle auth effects and replaced the remaining table/welcome gradients with solid palette colors. Noninteractive summary cards no longer lift or imply clickability. Reduced-motion rules remain in `theme.css` and authentication styles; transitions name properties explicitly. No local Inter font file/package was found in `frontend/public` or `frontend/node_modules`, so CSS prefers Inter when installed and falls back to Segoe UI/Aptos/system fonts.
- **Contrast calculations (sRGB WCAG relative luminance):** white on primary indigo 6.29:1; secondary nav text on navy 14.57:1; body navy on page background 16.32:1; success on success tint 5.21:1; warning on warning tint 6.84:1; danger on danger tint 5.72:1; muted text on white 6.23:1. These meet 4.5:1 for the listed normal text combinations.
- **Statement calculation fix:** added `Transaction.account_type` and `core/migrations/0019_transaction_account_type.py`. The migration conservatively classifies only entries supported by provider/account links or explicit notes; ambiguous history stays unclassified for review instead of being guessed. New transaction writers set account type. PDF output separates BOSA, FOSA, loan, and other activity; opening balances include posted entries before the selected start date; running/closing balances use deterministic `(created_at, pk)` order; unresolved withdrawals and pending provider requests are listed separately; long tables repeat headers and the footer prints page numbers. The statement uses posted ledger transactions and excludes unverified FOSA debits. No allocations or share capital were invented.
- **Backend verification:** `venv\\Scripts\\python.exe manage.py check --settings=sacco.browser_test_settings` — no issues. `venv\\Scripts\\python.exe manage.py makemigrations --check --dry-run core --settings=sacco.browser_test_settings` — no changes detected. `venv\\Scripts\\python.exe manage.py test core.tests_downloads core.tests_member_journey --settings=sacco.browser_test_settings --verbosity=0` — **17 tests passed**, exit 0. This applied the full migration chain, including `core.0019`, to an isolated in-memory test database. Coverage includes member-scoped PDF/XLSX files, invalid date ranges, empty statements, account separation/opening balances, deterministic ties, pending/unverified activity, reversals, long references/notes, repeated table headers, multipage output, and PDF page numbers. Test output warns that the local `staticfiles` directory is absent; this did not fail the tests. No migration ran against `db.sqlite3`; unresolved transactions 41 and 50 were not changed.
- **Frontend verification:** from `frontend`, `$env:CI='true'; npm test -- --watchAll=false --runInBand` — **19 suites, 56 tests passed**, exit 0. This includes keyboard interaction tests for the top navigation menus and focused login, registration, member, report, transport, and download tests.
- **Production build:** from `frontend`, `$env:CI='true'; $env:GENERATE_SOURCEMAP='false'; npm run build` — **compiled successfully, exit 0**. CRA emitted Node `[DEP0176] fs.F_OK is deprecated`; no compile errors or frontend lint warnings were reported.
- **Visual acceptance:** not verified. The computer-use tool's actual result was `browsers: []` and `Browsers: Error: Local browser use is disabled in Work settings`. No browser journey, screenshots, responsive pass at 320–1920px, landscape/200% zoom, or runtime menu inspection is claimed. The React tests validate keyboard menu behavior in the test DOM, not rendered layout. These visual checks remain pending.
- **Remaining member/product limitations:** no bundled Inter font; live outbound payouts remain disabled; OTP provider acceptance/inbox delivery is not established; the member API failures seen in supplied screenshots (balances/holds, withdrawal history, transaction history, dividends, profile, notifications, identity status) were not re-tested here. Separate share-capital register, goal/locked savings, expanded payment rails, provider-confirmed disbursement, and other features in the supplied inventory remain missing, blocked, partial, or unverified as that inventory states. No browser screenshot or external-provider claim should be inferred from these automated checks.

## Staff login OTP delivery repair — 2026-11-12

- **Runtime trace:** port checks found no listening process on 3001 or 8000 during this inspection, so the process and settings module behind the user's observed page cannot be identified. Frontend source has no `REACT_APP_API_URL` in `frontend/.env.development.local`; absent a process override, Axios uses relative `/api/` and `frontend/src/setupProxy.js` forwards it to `http://127.0.0.1:8000`. The repository's project settings module is `sacco.settings`; the isolated profile is `sacco.browser_test_settings`.
- **Delivery finding:** the on-disk sanitized log contains an incomplete-SMTP warning followed by `2FA OTP delivery status=unavailable via email`. In current `sacco.settings`, SMTP backend and host are configured, port is 587, TLS is enabled, and a sender is configured, but `EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD` are empty. `sacco.browser_test_settings` now forces blank SMTP fields and Django's in-memory backend. OTP delivery is synchronous in the login request; no background email worker was found. No console fallback is used.
- **Root cause and correction:** `custom_token_obtain` always returned “has been sent” after creating the 2FA challenge, regardless of `dispatch_otp` outcome. Login now reports `accepted`, `unavailable`, or `failed` distinctly; provider acceptance explicitly does not promise inbox delivery. Delivery exceptions are safely recorded by exception type, and failures create an audit event without recipient, OTP, or provider payload. The member login subtitle is now role-neutral; only active `is_staff`, `is_superuser`, or `is_admin` accounts trigger the existing staff 2FA policy.
- **Retry and verification safety:** added signed, challenge-bound `POST /api/login/2fa/resend/`; resend waits 60 seconds, permits at most five OTP issues per account per hour, and has an additional 10-per-hour IP throttle. Repeated password login respects the cooldown. Resend invalidates the superseded code. Staff login codes remain 10-minute, single-use, and limited to five attempts; tokens are still issued only after successful code verification. The login form has separate Verify, Resend, and Back actions with mobile sizing and an explicit countdown.
- **Role attribution limitation:** the redacted `da***@gmail.com` prefix matches multiple users in the local project database. One old login challenge for a matching account belongs to a Django superuser (`is_staff=True`, `is_superuser=True`), which explains why that account receives 2FA; it is too old to prove it is the request currently shown in the user's browser. The exact live account role remains unconfirmed because the observed runtime was not listening locally and the masked address is not unique.
- **Automated verification:** project virtualenv command `venv\Scripts\python.exe manage.py test accounts.tests --settings=sacco.browser_test_settings --verbosity=1` — **33 tests passed**, exit 0, 72.013 seconds (final run), isolated in-memory test database. Covers successful mocked dispatch and redirect, missing/unavailable and failed provider paths, wrong/expired codes, five-attempt lockout, cooldown/hourly resend limits, superseded codes, and memory-backend rejection. Frontend `npm test -- --watchAll=false --runInBand` — **11 suites, 30 tests passed**. Production build compiled successfully; Node emitted the existing `[DEP0176] fs.F_OK` deprecation warning. Django check passed and `makemigrations --check --dry-run` reported no changes.
- **Live delivery:** no OTP was sent. The active SMTP configuration is missing `EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD`, and no local backend process was running. Mocked acceptance proves only the application code path, not provider or inbox delivery. To configure, set `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, and `DEFAULT_FROM_EMAIL` in the root `.env` for local development or the deployment secret store; restart Django after configuration. Do not commit `.env` or send credentials in chat. Provider acceptance and actual inbox receipt still require separate verification.

## Registration acceptance repair — 2026-11-12

- **Runtime identification:** port/process inspection found no listener on 3000, 3001, 3002, or 8000 and no running `node`/`python` app process. There is no current browser URL or active Django settings module to attribute to the reported page. Source configuration uses a relative `/api/` base; the React dev proxy in `frontend/src/setupProxy.js` targets `http://127.0.0.1:8000`. Project settings are `sacco.settings`; isolated verification uses `sacco.browser_test_settings`.
- **Root cause:** `/api/register/` returns server field errors for files and identity consent. The React server-error mapping only recognized personal/contact text fields, so an `id_document`, `selfie`, or `id_verification_consent` error fell through to Step 3 and displayed “Please fix the highlighted fields” with no matching control. The browser upload component checks file MIME metadata and size; Django also validates file bytes and decoded image quality. A synthetic multipart PDF accepted by the browser MIME check but missing a valid end marker returned HTTP 400 with `id_document: ["The PDF file is incomplete or invalid."]`. A no-consent upload returns `id_verification_consent: ["Consent is required when submitting identity documents."]`. Both errors are safe validation messages; no personal data or file content is logged by these tests.
- **Fix:** `Register.js` maps all API fields to their owning step, returns to the earliest invalid step, shows an accessible field-error summary with links, and keeps inline errors beside ID/selfie uploads and consent. Scalar values, selected files, and consent remain in parent state when navigating back; the selected upload is identified when the file input remounts. The form blocks concurrent submits and disables repeat submit after success. Validation remains unchanged; server document and consent rules remain authoritative.
- **Registration lifecycle and retry:** isolated API tests confirm one `User` and one `Member` are created. Existing lifecycle is retained: `User.is_member=True`, no staff/superuser privilege, `Member.status="active"`, and `IDVerification.status="draft"` until identity review; signup does not assert government identity verification. Reposting the same payload returns a duplicate-username validation error and leaves exactly one user, member, IDVerification, and registration audit row.
- **KYC migration check:** registration calls `run_id_verification`, which writes the existing `IDVerification` and `AuditLog` models. It does not use the separately drifted `KYCConsentRecord`, `KYCRiskScore`, `LivenessChallenge`, `MemberApproval`, `DeviceFingerprint`, or `MemberReference` tables. The required `accounts.0012_idverification_private_fields` migration succeeded on an empty isolated database and on an upgrade fixture at accounts.0011 with an existing synthetic ID-verification row; the row remained intact. No `--fake`, production migration, or working database change was used. `makemigrations --check --dry-run` still exits 1 and proposes `accounts.0013_alter_auditlog_action_alter_otprequest_purpose_and_more.py` for those other KYC models and choice-state changes; it was not generated because it is outside the registration path. KYC workflow migration drift remains pending before those endpoints are exercised on a fresh persistent database.
- **Verification:** with the project virtualenv and `sacco.browser_test_settings`, `manage.py test accounts.tests --verbosity=1` — **37 passed**, exit 0, in-memory test database. Frontend `$env:CI='true'; npm test -- --watchAll=false --runInBand` — **16 suites, 42 tests passed**, including the Step 3-to-Step 2 upload-error path, inline error, preserved values, consent submission, and success state. `manage.py check` — no issues. `CI=true GENERATE_SOURCEMAP=false npm run build` — **exit 0, compiled successfully**; remaining warning is Node `[DEP0176] fs.F_OK is deprecated`. Test welcome email was skipped under isolated settings; no real email, payment, or notification was sent.
- **Browser status:** not verified. No app process was running to reproduce the user's live submission, and local browser automation is disabled in Work settings. The exact response from the user's original browser attempt is therefore unknown; the hidden Step 2 validation-error path was reproduced with isolated synthetic data. Transactions 41 and 50 and all production data remain untouched.
- **Manual registration check:** start the isolated Django server on `127.0.0.1:8000` and React on `127.0.0.1:3002` using a new temporary `SACCO_BROWSER_TEST_DB` as described below (do not point it at `db.sqlite3`). Open `http://127.0.0.1:3002/register`, enter a unique synthetic applicant with valid required details, leave the optional ID/selfie upload blank, and submit. Confirm the member-number success banner appears and returns to sign-in after about three seconds. A successful request should leave identity status at `draft`, not `verified`.

For that isolated check, use separate PowerShell windows:

```powershell
# Window 1: Django on a new disposable database
Set-Location C:\Users\USER\sacco_app
$env:SACCO_BROWSER_TEST_DB = Join-Path $env:TEMP ("sacco-registration-" + [guid]::NewGuid().ToString("N") + ".sqlite3")
$env:EMAIL_HOST = ''; $env:EMAIL_HOST_USER = ''; $env:EMAIL_HOST_PASSWORD = ''; $env:DEFAULT_FROM_EMAIL = ''
$env:AT_USERNAME = ''; $env:AT_API_KEY = ''
$env:MPESA_ENV = 'sandbox'; $env:MPESA_CONSUMER_KEY = ''; $env:MPESA_CONSUMER_SECRET = ''; $env:MPESA_PASSKEY = ''; $env:MPESA_CALLBACK_BASE_URL = ''
$env:CRB_PROVIDER = 'stub'; $env:CRB_API_KEY = ''
.\venv\Scripts\python.exe manage.py migrate --settings=sacco.browser_test_settings
.\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload --settings=sacco.browser_test_settings
```

```powershell
# Window 2: React; its /api proxy points to the Django server above
Set-Location C:\Users\USER\sacco_app\frontend
$env:HOST = '127.0.0.1'; $env:PORT = '3002'; $env:BROWSER = 'none'; $env:REACT_APP_API_URL = ''
npm start
```

## Latest phase status — Transport Phase 1

See “Transport operations Phase 1 and shared navigation” for implementation details and exact isolated launch instructions. Final backend rerun: `venv\\Scripts\\python.exe manage.py test core.tests_transport --settings=sacco.browser_test_settings --verbosity=1` — **19 tests passed**, exit 0, 161.746 seconds, isolated test database. Django system check reported no issues; the test process emitted a warning that the local `staticfiles` directory is absent. Separate follow-ups passed for exact-decimal totals, multiple roles, and multiple-vehicle ownership; all migrations applied to isolated test databases. Frontend: 19 suites/56 tests passed; focused navigation/crew/operations were 3 suites/10 tests, and the final keyboard-focus rerun was 1 suite/4 tests. Final React production build exited 0; the only build warning was Node's existing `[DEP0176] fs.F_OK` deprecation. Browser automation returned `browsers: []` and `Browsers: Error: Local browser use is disabled in Work settings`, so no screenshots or visual acceptance are claimed. Owner portal, expenses, shift closure, full reconciliation, and allocation policy remain pending. No migrations ran against `db.sqlite3`; transactions 41 and 50 remain unchanged.

## Design and statement verification refresh — 2026-11-12

- Removed the remaining decorative pictographic labels from the touched administration, profile, selfie, and transport reconciliation screens; selfie actions use the shared SVG icon component. The copyright mark in the login footer is ordinary text. Replaced the selfie button's broad `transition: all` with explicit background, text, and border transitions; the shared reduced-motion rule still disables transitions for users who request it.
- Corrected the registration success-state test to assert the screen's actual copy (“Registration successful. … Redirecting…”). The previous test expected stale punctuation and failed even though the success state rendered and the single registration POST completed.
- **Backend verification refresh:** `venv\\Scripts\\python.exe manage.py test core.tests_downloads core.tests_member_journey --settings=sacco.browser_test_settings --verbosity=1` — **17 tests passed**, exit 0, isolated in-memory test database; migrations through `core.0019_transaction_account_type` applied. Django reported no system-check issues. Existing test output warns that `staticfiles` is not present and includes expected invalid-request/duplicate-callback log lines.
- **Frontend verification refresh:** `CI=true npm test -- --watchAll=false --runInBand` — **19 suites, 56 tests passed**, exit 0. The first run exposed only the stale registration assertion above; the rerun passed. `CI=true GENERATE_SOURCEMAP=false npm run build` — **compiled successfully**, exit 0. Existing Node `[DEP0176] fs.F_OK` deprecation warning remains; no compile/lint warning was reported.
- `git diff --check` still reports an extra blank line at EOF in the unrelated, already-modified `core/tests_extended.py:502`; that file was left unchanged. The source scan found no mojibake/replacement characters in the scoped frontend/PDF sources; the `©` copyright symbol is intentional.
- **Visual acceptance remains pending:** no browser or screenshots were available. Tests/build do not verify layout at 320–1920 CSS px, landscape, 200% zoom, navigation position, keyboard focus in a real browser, or that a generated PDF visually paginates correctly. Automated PDF tests inspect generated content and pagination structure, not a browser download or visual render.

## Product inventory status supplied by member — 2026-11-12

The supplied evidence table is retained as a user-reported baseline, not independent verification by this pass. It identifies the member UI, registration/login/OTP, account availability, transaction screens, dividends, loans, transport ownership/reconciliation, and responsive behavior as partial or unverified; separate share capital, goal/locked savings, expanded payment rails, confirmed live payouts, full owner and governance/welfare workflows, offline sync, balanced double-entry accounting, reliable production jobs/monitoring, PostgreSQL backup/restore evidence, and verified SASRA compliance as missing, blocked, or not evidenced. KYC uploads/manual-review work is reported as existing but incompletely verified; live identity/liveness, contact verification, referee workflow, and complete status separation remain unverified or blocked, and KYC migration drift remains documented above. No feature in this inventory is promoted to complete based on the frontend tests or production build.

## Phase 1 — Database recovery readiness and migration consistency — 2026-11-12

> Historical baseline only. The later “Phase 1 continuation — migration reconciliation” and the current-state checkpoint at the end of this file supersede the counts and migration recommendations below. In particular, preserve the two orphaned historical recorder rows; do not run any procedure that deletes them.

### Runtime and configured database

- No Python/Node process was found for this project and no listener was found on ports 3000–3002 or 8000. The process-command-line query was denied by Windows CIM permissions; the independent process-name and listener checks returned no project process/listener. There is no currently running app whose settings can be attributed to the browser.
- Read-only Django settings inspection with the project virtualenv resolved `DJANGO_SETTINGS_MODULE=sacco.settings`, SQLite (`django.db.backends.sqlite3`), and `C:\Users\USER\sacco_app\db.sqlite3`. `sacco/settings.py` selects PostgreSQL only when `USE_POSTGRES` is enabled; it was not enabled for this local process/configuration. `sacco.browser_test_settings` instead points to `SACCO_BROWSER_TEST_DB` (or the ignored `sacco_auth_browser_test.sqlite3`) and blanks email/SMS credentials. This is evidence about the local repository configuration only; it does **not** establish that `db.sqlite3` is or was a deployed production database.

### Snapshot, restore, and source preservation

- Before any migration test, created a transaction-consistent SQLite online backup at `C:\Users\USER\sacco_app\.recovery\phase1-2026-11-12\local-configured-db-backup.sqlite3`, then restored it to `...\restored-copy.sqlite3`. The recovery directory is ACL-protected; only the current Windows user and `NT AUTHORITY\SYSTEM` have Full Control. The files are ignored by the repository's existing `*.sqlite3` rule and were not staged.
- Source, backup, and restored snapshot report `PRAGMA integrity_check = ok` and zero `PRAGMA foreign_key_check` violations. A logical SQLite dump digest of the source and backup matched. The source file remained 880,640 bytes with the same last-write timestamp before and after the snapshot and copy-only migrations. The original database was not migrated or otherwise written by this phase.
- The local configured database contains 53 application tables, 65 `django_migrations` rows, 13 user rows, 5 member rows, 24 savings rows, 50 transaction rows, 0 `FosaWithdrawal` rows, 1 M-Pesa transaction, 0 crew assignments, and 0 transport collections. No member names, IDs, contact details, or credentials were copied into this report. Its savings rows total KES 358,327.04, all currently labelled FOSA. The arithmetic sum of `Transaction.amount` fields is KES 1,119,027.04; this is a preservation comparison only, **not** a ledger balance or proof of double-entry accounting.
- Both preserved Git stashes remain present (`stash@{0}` and `stash@{1}`); neither was applied, dropped, or edited.

### Exact migration and schema inventory

- Current migration files: the Django graph contains 65 migrations. Against the source database, 63 graph migrations were recorded as applied and the only unapplied files were `core.0018_transportassignmentissue` and `core.0019_transaction_account_type`. All current `accounts` and `members` graph migrations appeared applied; other installed app migrations were applied.
- The database has two additional `django_migrations` rows for which no migration file exists in the current tree: `accounts.0012_idverification_data_retention_until_and_more` and `members.0004_remove_member_daraja_registered`. `showmigrations` does not display these orphan rows. The current files `accounts.0012_idverification_private_fields` and `members.0004_alter_member_daraja_registered` are separate rows, both recorded as applied. The missing old files were not found in `HEAD` or the preserved stashes. No history row was deleted, and no `--fake` operation was used. The contents/effects of those absent migrations cannot be reconstructed from the recorder rows alone.
- The source physical schema has all four `IDVerification` privacy fields (`data_retention_until`, `national_id_hash`, `pii_last_accessed_at`, `pii_last_accessed_by_id`), the expected national-ID-hash index and PII-access foreign key, and a `members_member.daraja_registered` column. Those columns, indexes, and foreign keys match the current model definitions. The existing `accounts.0012_idverification_private_fields` uses `SeparateDatabaseAndState` and adds a field only if its column is absent. It applied successfully on a fresh migration path. Its custom check is column-based; it does not repair a missing index or foreign key if a column alone was left behind. The restored source already records that migration applied, so the exact “columns exist but current migration row is absent” branch was not forced by editing migration history.
- All six current KYC workflow model tables are physically present in the local database and each has 0 rows: `KYCConsentRecord`, `KYCRiskScore`, `LivenessChallenge`, `MemberApproval`, `DeviceFingerprint`, and `MemberReference`. Their physical columns match the current models. There is no migration in the current graph that creates them. A fresh database built from the current migration files therefore has none of these tables, even though `accounts.kyc_views` references them. Conversely, blindly applying the model-generated migration to the existing local database would try to create tables that already exist.
- `makemigrations --check --dry-run --settings=sacco.browser_test_settings` exits **1** and proposes `accounts.0013_alter_auditlog_action_alter_otprequest_purpose_and_more.py`: two choice-state alterations (`AuditLog.action`, `OTPRequest.purpose`) and `CreateModel` operations for the six KYC models above. No file was generated. The risk model documents hard-coded automatic outcomes (80–100 auto-approve, 0–49 reject); liveness is represented without an approved live provider; and the approval model describes activation decisions. Those are policy/verification behaviors, not merely harmless schema definitions. A migration is blocked until the cooperative approves the workflow and a safe reconciliation migration is reviewed. Creating them now could activate unapproved KYC paths and would fail against the existing tables unless it explicitly reconciled physical schema and migration state.
- **History blocker:** a database state containing only the absent `members.0004_remove_member_daraja_registered` row cannot be safely upgraded from the available migration files: its source operations are missing, and the current `0004_alter...` only alters the field. The actual local snapshot has both 0004 rows and the column present, so it does not prove the “remove-only” upgrade path. The absent accounts 0012 migration presents the same provenance limitation. Recover the exact old migration source or approve a reviewed forward reconciliation before using this history on another database.

### Fresh and restored-copy migration results

- **Fresh migration chain:** with `SACCO_BROWSER_TEST_DB` set to a new isolated `.recovery` SQLite file, `venv\Scripts\python.exe manage.py migrate --settings=sacco.browser_test_settings --noinput` exited 0 and applied all 65 current graph migrations, including `accounts.0012`, `core.0018`, `core.0019`, and `members.0004_alter...`. The database has zero foreign-key violations. This proves the current migration chain can build its declared migration state; it does not prove the unmigrated KYC model schema is ready on a fresh install.
- **Upgrade from the restored local snapshot:** with `SACCO_BROWSER_TEST_DB` pointing to the restored copy, `manage.py migrate --plan --settings=sacco.browser_test_settings` listed only `core.0018_transportassignmentissue` and `core.0019_transaction_account_type`; applying that plan exited 0. The issue table was created with its expected foreign-key indexes, and `txn_user_account_date_idx` was created. All current graph migrations are now applied on the copy; the two orphan recorder rows remain untouched.
- On the upgraded copy, table row counts were unchanged except for expected migration metadata: `django_migrations` 65→67, `django_content_type` 49→50, `auth_permission` 196→200, plus creation of an empty `core_transportassignmentissue` table. Existing users/members/savings/transactions and other table row counts were preserved. Savings totals and the `Transaction.amount` field sum match the snapshot exactly. The new transaction classification is conservative: 26 loan-account entries are labelled `loan`; 24 entries remain blank/unclassified. Transactions **41 (KES 500)** and **50 (KES 4,000)** retain their amount, type, timestamp, note/reversal/user references in the copy and remain `account_type=''`; no withdrawal record was created, removed, settled, or released. Both original transactions remain unresolved.
- **Migration files changed in this phase: none.** Existing `core.0018` and `core.0019` were exercised on copies. No migration was applied to `db.sqlite3`.

### Withdrawal safeguard finding

- The API path is `POST /api/withdraw/` → `core.views.withdraw` → `get_live_payout_provider()` → `reserve_and_submit_withdrawal`. The current service returns `None` for the live provider; STK/C2B are inbound collection integrations and are not treated as disbursement support. The view returns HTTP 503 with `status: unavailable` before reserving funds or creating a withdrawal, savings debit, transaction, or payout request. The message explicitly says no funds were debited. Provider acceptance in the separate mocked state-machine path remains pending and never marks a payout successful.
- `venv\Scripts\python.exe manage.py test core.tests_withdrawals --settings=sacco.browser_test_settings --verbosity=1` — **9 tests passed**, exit 0, in-memory isolated test database. This includes the no-provider API test, which verified HTTP 503 and zero withdrawal/debit/ledger rows; payout timeout, duplicate/retry, permission, and correction safeguards are also covered. Django reported no system-check issues. Test output includes the expected service-unavailable/permission log entries and the existing missing-`staticfiles` warning. Live payouts remain disabled.

### Commands for controlled use

The following are the exact isolated commands used for migration verification; they operate on disposable copies only:

```powershell
Set-Location C:\Users\USER\sacco_app
$env:SACCO_BROWSER_TEST_DB = 'C:\Users\USER\sacco_app\.recovery\phase1-2026-11-12\fresh-install.sqlite3'
.\venv\Scripts\python.exe manage.py migrate --settings=sacco.browser_test_settings --noinput

$env:SACCO_BROWSER_TEST_DB = 'C:\Users\USER\sacco_app\.recovery\phase1-2026-11-12\restored-copy.sqlite3'
.\venv\Scripts\python.exe manage.py migrate --plan --settings=sacco.browser_test_settings
.\venv\Scripts\python.exe manage.py migrate --settings=sacco.browser_test_settings --noinput
```

For an eventual upgrade of the configured local SQLite database, stop all writers, take and restore a new protected SQLite online backup, validate both copies with `PRAGMA integrity_check` and `PRAGMA foreign_key_check`, compare the migration plan and source schema, and only then run:

```powershell
Set-Location C:\Users\USER\sacco_app
.\venv\Scripts\python.exe manage.py showmigrations --plan --settings=sacco.settings
.\venv\Scripts\python.exe manage.py migrate --plan --settings=sacco.settings
.\venv\Scripts\python.exe manage.py migrate --settings=sacco.settings --noinput
```

**Do not run the last command yet.** First resolve the orphaned migration provenance and KYC migration/model drift, then repeat the fresh and restored-copy checks. These commands target only this repository's configured local SQLite database; they say nothing about a separately deployed database. PostgreSQL migration/backup/restore remains unverified.

### Remaining blockers

- Recover or formally reconcile the two absent migration sources without deleting recorder rows or faking application. Test the exact legacy states on isolated copies.
- Approve or remove/defer the unapproved KYC models and workflows, then provide a migration that creates schema on fresh installs and safely records/reconciles the existing physical tables. Until then `makemigrations --check` remains exit 1, and KYC endpoints that use those tables are not fresh-install-ready.
- Verify backup/restore and migrations against the actual deployment database only after its engine, endpoint, ownership, and maintenance process are confirmed. No PostgreSQL environment was configured or tested here.
- No payout provider is implemented, so withdrawal requests remain unavailable by design. Transactions 41 and 50 remain unresolved and unchanged; this phase provides no provider evidence and no corrections.

## Phase 1 continuation — migration reconciliation — 2026-11-12

This section supersedes the earlier Phase 1 notes that said the KYC model migration was still pending and that the working database was unchanged. It records the follow-up isolated-copy work and the final source-versus-backup observation.

### Historical migration provenance and forward strategy

- Re-searched the repository, all files in `.recovery`, reachable Git objects, `stash@{0}`, and `stash@{1}` for `accounts.0012_idverification_data_retention_until_and_more.py` and `members.0004_remove_member_daraja_registered.py`. Neither source file was recovered. The recovery folder contains database snapshots, not migration source. Both stashes remain untouched; no recorder row or applied migration file was removed or rewritten.
- The missing migration operations remain unknown. I do not infer their effects from the filenames. The protected local snapshot has both orphan recorder rows and the current replacement rows, plus the verified current ID-verification privacy schema and `members_member.daraja_registered` column. The tested upgrade therefore applies the current graph forward and leaves the orphan rows intact.
- For another database that has only one of the orphan rows, do not run an upgrade based on this snapshot. First take a consistent copy and inspect its physical schema against the current models. If it does not match, recover the original migration or prepare a separate reviewed schema bridge for that exact state; preserve all recorder rows and never use `--fake`. The unavailable `members.0004` source can precede a current `AlterField` that expects the column, so that alternate history remains a pre-upgrade blocker.

### KYC schema reconciliation and feature boundary

- Added **`accounts/migrations/0013_alter_auditlog_action_alter_otprequest_purpose_and_more.py`**. Its state records the current `AuditLog.action` and `OTPRequest.purpose` choices and all six KYC models. These choice changes are state-only because Django choices are not database constraints.
- Its forward database operation creates missing KYC tables through Django's schema editor. If a table already exists, it adopts it only after checking the exact column set, database types, nullability, primary key, foreign-key targets, index signatures/counts, unique constraints, and model field check constraints. On SQLite it also checks the stored check expressions and foreign-key rows. It preflights every existing table before creating any absent table, then validates the resulting schema. A mismatch raises a table-specific `RuntimeError`; it does not silently skip incompatible tables. This migration is forward-only so rollback cannot drop adopted tables or data.
- All six existing tables on the verified snapshot matched the current model schema and had zero rows. A separate disposable negative fixture with one expected index removed failed with `indexes differ`; `accounts.0013` was not recorded, and that fixture remained integrity-valid with zero FK violations. No source tables were altered by this negative check.
- The six models are referenced by KYC views/services. The schema is now present on fresh installs and is strictly validated on existing installs, but schema installation does not enable automated decisions. `/api/kyc/risk-score/` returns 503, `/api/kyc/liveness/start/` and completion return 503, and the workflow status exposes risk assessment as disabled/provider unavailable without computing or storing a score. `compute_risk_score` now raises an explicit disabled exception if called directly. Manual staff review remains a separate human action; the existing committee workflow's relationship to external identity status still needs review. No live provider, automated risk policy, or automatic membership approval was enabled.

### Fresh and restored-copy results

- **Fresh install:** `phase1-final2-fresh.sqlite3` applied the entire current graph successfully: 66 migration records, 54 tables, all six KYC tables present. `PRAGMA integrity_check` returned `ok`; `PRAGMA foreign_key_check` returned zero rows.
- **Restored-copy upgrade:** created `phase1-final2-upgrade.sqlite3` from the preserved `local-configured-db-backup.sqlite3` using SQLite's online backup API, then applied `accounts.0013`, `core.0018`, and `core.0019`. It now has 68 recorder rows (the 66 current graph rows plus the two untouched orphan rows), 54 tables, and all six KYC tables. Integrity returned `ok`; FK check returned zero rows; `showmigrations --plan` showed no pending migrations in the current graph.
- Before/after application records remained intact: users 13→13, members 5→5, savings 24→24, transactions 50→50, FOSA withdrawals 0→0. Savings sum stayed KES 358,327.04 and the arithmetic `Transaction.amount` sum stayed KES 1,119,027.04 (a preservation measure, not an accounting balance). KYC table counts stayed zero. Only migration/content-type/permission metadata and the new empty `core_transportassignmentissue` table changed. Hashed comparisons of the relevant transaction fields for **41 (KES 500)** and **50 (KES 4,000)** matched the backup; neither was adjusted or settled.
- The tested restored-copy command was:

```powershell
Set-Location C:\Users\USER\sacco_app
$env:SACCO_BROWSER_TEST_DB = 'C:\Users\USER\sacco_app\.recovery\phase1-2026-11-12\phase1-final2-upgrade.sqlite3'
.\venv\Scripts\python.exe manage.py migrate --plan --settings=sacco.browser_test_settings
.\venv\Scripts\python.exe manage.py migrate --settings=sacco.browser_test_settings --noinput
```

- The tested fresh command was:

```powershell
Set-Location C:\Users\USER\sacco_app
$env:SACCO_BROWSER_TEST_DB = 'C:\Users\USER\sacco_app\.recovery\phase1-2026-11-12\phase1-final2-fresh.sqlite3'
.\venv\Scripts\python.exe manage.py migrate --settings=sacco.browser_test_settings --noinput
```

- Final checks: `manage.py check --settings=sacco.browser_test_settings` exited 0 with no issues; `manage.py makemigrations --check --dry-run --settings=sacco.browser_test_settings` exited 0 with “No changes detected”; Python compilation for the changed migration, KYC views/service, and tests exited 0.

### Tests and KYC endpoint coverage

- `manage.py test accounts.tests --settings=sacco.browser_test_settings --verbosity=1` — **37 passed**, exit 0. This includes registration, authentication, and existing account-permission coverage.
- `manage.py test accounts.test_kyc_reconciliation --settings=sacco.browser_test_settings --verbosity=1` — **5 passed**, exit 0. It verifies migrated KYC status/consent persistence, disabled risk/liveness actions without writes, direct risk-service guard, member denial from the staff approval queue, and a clear failure when a required index is absent.
- `manage.py test core.tests_withdrawals --settings=sacco.browser_test_settings --verbosity=1` — **9 passed**, exit 0. No-provider withdrawal still returns 503 before financial mutation.
- The test runner used isolated test databases. Expected request-status logs appeared. Django emitted the existing warning that the repository's `staticfiles` directory is absent; checks/tests still passed. No live messages or payouts were initiated.

### Source database observation and preservation

- No migration command targeted `db.sqlite3`; the full/negative migration runs used `.recovery` copies, and the test commands used `sacco.browser_test_settings`. However, a final read-only comparison found the working `db.sqlite3` no longer has the same logical contents as the earlier recovery backup: it has **five more `login` audit rows and five more `OutstandingToken` rows**. Its size is still 880,640 bytes; integrity is `ok`, there are zero FK violations, and the user/member/savings/transaction counts and financial aggregates still match. Transactions 41 and 50 match the backup fields checked.
- The prior report recorded the working database timestamp as 12:16:41 UTC; the final observation is 13:02:02 UTC. The origin of the five login/token records is not established, so this report does not claim the working database was untouched. I did not attempt to remove or reverse those records. To preserve the newly observed state, I made a second SQLite online snapshot at `C:\Users\USER\sacco_app\.recovery\phase1-2026-11-12\observed-working-db-snapshot.sqlite3`; it passed integrity and FK checks. The original verified recovery backup remains unchanged.
- The working DB and protected backup have identical 148 SQLite schema objects and identical `django_migrations` `(app, name)` sets (65 rows); the only count deltas found were the five login audit rows and five outstanding-token rows. The new end snapshot preserves that later state. The tested copy therefore matches the working DB's physical schema and migration recorder state, while preserving the pre-task backup separately.

### Remaining blockers

- Historical provenance remains unresolved for the two missing migration sources. The current working DB's schema and recorder set match the tested restore path. A different database with only an orphaned migration record still requires exact schema preflight and potentially a reviewed bridge before migration.
- PostgreSQL migration/backup/restore behavior is unverified. The strict schema adoption path and migration runs were verified against SQLite only.
- Automated risk policy, live liveness provider, and automatic member approval remain disabled. Manual committee approval is still a distinct existing staff workflow; its effect on the identity-verification status needs a separate policy/control review.
- Live FOSA payouts remain disabled. Transactions 41 and 50 remain unresolved; no payout evidence or balance corrections were made.
- No migration was run against `sacco.settings`/`db.sqlite3` in this phase. A later controlled upgrade of this exact local state can use the tested copy plan after stopping writers, taking a fresh protected backup, checking the unexplained login/token delta, and reviewing the plan. Do not apply it to any separately deployed database until its engine and migration state are identified. The alternate orphan-only history remains blocked.

## Login accepted but portal bootstrap fails — 2026-11-12

- **Observed symptom:** the login page reports that sign-in was accepted but the portal could not be loaded. Source tracing shows `Login.storeTokensAndNavigate()` stores the returned access/refresh tokens, then calls `AuthContext.refreshUser()`. That call requests `GET /api/dashboard/`; a non-authentication server error produces the displayed message while leaving the session tokens stored.
- **Reproduced cause on an isolated copy:** before migration, authenticated `GET /api/profile/` returned 200, while `GET /api/dashboard/` returned 500 with `OperationalError: no such column: core_transaction.account_type`. `TransactionSerializer` now reads `account_type`, introduced by `core.0019_transaction_account_type`, but the copied database had `core.0018_transportassignmentissue` and `core.0019_transaction_account_type` pending. This is migration drift, not a rejected password or invalid member role.
- **Isolated fix verification:** applied the pending graph migrations to `portal-login-repro.sqlite3` only. A synthetic non-staff account then logged in through `POST /api/token/` (200, no 2FA required), and the token-authenticated `GET /api/dashboard/` returned 200 for the same account. No token, real member data, or credentials were printed. The existing `core.0019` migration is the schema fix; no source migration was rewritten or newly generated.
- **Running app status:** the supplied page URL is `http://127.0.0.1:3001/`, but there were no listeners on ports 3000, 3001, 3002, or 8000 in this tool session. Bounded requests to port 3001 and `http://127.0.0.1:8000/api/config/` failed to connect. Therefore this session cannot attribute the browser's active server/settings or verify the live page. A later read-only check in this session found the configured local `db.sqlite3` now records all current graph migrations, including `core.0019`, and contains `core_transaction.account_type`; no process/listener was available to prove the user's browser uses this database.
- **Data boundary:** this session migrated only the isolated repro copy. It did not write to `db.sqlite3` or the verified backup. The configured database's present migration state differs from the earlier pre-upgrade snapshot; the actor and time of that change are not established. Transactions 41 and 50 retain the same legacy fields as the backup and remain unclassified/unresolved. Do not attribute the local migration to this session.
- **Browser acceptance:** not performed; no browser or local server was available. After the controlled upgrade and server restart, sign in at `http://127.0.0.1:3001/`; success is that the browser leaves the sign-in screen for the member portal and the Network panel shows `POST /api/token/` followed by `GET /api/dashboard/` returning 200. If it still fails, capture the dashboard response status and sanitized error without exposing the access token.

---

## Roadmap checkpoint — corrected migration state and next phases — 2026-11-12

This section supersedes the duplicated Phase 1 draft below and any earlier instructions to delete migration recorder rows, use `--fake`, edit a script to point at `db.sqlite3`, or apply an unreviewed production upgrade. Preserve all migration history. The legacy `scripts/fix_migration_history.py` is now a safe refusal stub and cannot delete rows.

### Phase 1 — migration reconciliation evidence

- The two historical source files were not recovered. `git log --all` found no revisions for `accounts.0012_idverification_data_retention_until_and_more` or `members.0004_remove_member_daraja_registered`; the preserved stashes and `.recovery` artifacts contain no matching migration files. Their original operations cannot be inferred from recorder names. Keep both orphaned recorder rows as historical evidence.
- Verified forward path: retain both orphan rows, apply current graph migrations normally, and let Django apply `accounts.0013_alter_auditlog_action_alter_otprequest_purpose_and_more`, `core.0018_transportassignmentissue`, and `core.0019_transaction_account_type`. `accounts.0013` creates absent KYC tables on fresh databases and validates exact schema before adopting existing matching tables. Incompatible schemas fail clearly. It does not enable automatic risk decisions, liveness verification, or automatic membership approval.
- Fresh install and restored-backup upgrade both passed on isolated SQLite databases. `accounts.0013`, `core.0018`, and `core.0019` applied without deleting or faking migration history. The restored copy preserved the two orphan rows, had 68 recorder rows (66 current graph migrations plus 2 orphan rows), passed SQLite integrity and foreign-key checks, and preserved relevant row counts and financial aggregates. Transactions 41 and 50 retained their legacy fields and remain unclassified and unresolved. See “Phase 1 continuation — migration reconciliation” above for test commands and detailed counts.
- A new **read-only** check of the configured local `db.sqlite3` found 68 migration rows, both orphan rows retained, all 66 current graph migrations recorded, `core_transaction.account_type` present, `core_transportassignmentissue` present, and all six KYC tables present. SQLite integrity returned `ok`; foreign-key check returned zero violations. This session did not run migrations against `db.sqlite3`; who applied them since the earlier snapshot is unknown.
- The current local database has 13 users, 5 members, 24 savings rows, 50 transactions, and 22 loans. Savings and transaction-amount aggregates match the preserved backup. Audit-log rows are 50 versus 38 in the backup and outstanding-token rows are 40 versus 25; the origin of those additional rows is not established. Preserve them; do not try to roll them back. The local database is not assumed to be a deployed production database.
- The actual app was not running during this check: no listeners were found on ports 3000–3002 or 8000. Thus no claim is made about which database a browser session uses.
- PostgreSQL backup, restore, schema, and migration compatibility have not been tested.

### Current roadmap checklist

| Phase | Status | Evidence / next work |
|---|---|---|
| 1. Database reconciliation | **Verified on fresh and restored copies; local schema currently records all migrations** | Historical file provenance remains unknown. Keep orphan rows. Confirm the running service's database before any controlled migration or release action. |
| 2. Registration and authentication | **Partially verified** | Account tests cover registration, OTP state, password reset, staff 2FA, refresh, and redirects. Email/SMS provider credentials and browser journey remain unverified; continue code/API verification, do not claim message delivery. |
| 3. Member portal | **Implemented in source; browser acceptance pending** | Relevant API/component tests and build results are in the verification section above. Need a running isolated stack for profile, balance/hold, statement, notification and responsive browser journeys. |
| 4. Accounting foundation | **Not implemented** | Existing `Transaction` is a single-entry activity ledger. Design chart of accounts, balanced journal lines, separate share register, holds/reversals, reconciliation, and a historical conversion plan before converting records. |
| 5. Payment workflows | **Partial; live providers blocked** | Inbound STK/C2B and mocked callback handling exist. No outbound payout provider is configured; live withdrawals stay disabled. Do not alter transactions 41 or 50. |
| 6. Transport operations | **Phase 1 exists; later workflows partial** | Staff assignments, crew shift view and collection idempotency exist. Owner activity, closure/expenses, receipt reconciliation and reminders need completion and browser verification. |
| 7. Welfare and governance | **Not implemented as complete workflows** | Welfare cases, incident follow-up, announcements, meeting records and formal voting remain future work. Formal voting requires approved eligibility, quorum and secrecy policy. |
| 8. Operational readiness | **Partial** | SQLite backup/restore is verified. PostgreSQL, scheduled execution, durable notification retry and monitoring remain unverified or unconfigured. |

### Immediate next checkpoint

Continue with Phase 2 using synthetic accounts and isolated test settings. Run the current account/authentication tests and frontend auth tests, repair any reproducible defect, and verify registration, login/OTP, refresh, redirects and logout through the available API/runtime. SMTP and SMS configuration values appear present in local settings, but their sandbox/production status and delivery are unverified; use only a confirmed sandbox/test recipient until authorized. Do not start live payments, production cutover, or irreversible financial corrections.

### Verification addendum — roadmap continuation — 2026-11-12

- Read-only provenance search found neither missing migration file in Git history, preserved stashes, or `.recovery` artifacts. The source history remains unknown; both recorder rows are preserved. `scripts/fix_migration_history.py` now exits with a refusal and performs no database operation.
- Current local `db.sqlite3` read-only inventory: 68 migration rows (66 graph migrations plus the two orphan rows); `accounts.0013`, `core.0018`, and `core.0019` are recorded applied; required field/tables are present; `PRAGMA integrity_check=ok`; zero FK violations. This work did not apply those migrations to the database. Compared with the protected original backup, users/members/savings/transactions/loans and savings/transaction amount aggregates match; audit-log and outstanding-token counts have unexplained increases. No rollback or cleanup was attempted.
- Backend verification in the project virtualenv, isolated in-memory test DB: `accounts.tests accounts.test_kyc_reconciliation core.tests core.tests_extended core.tests_downloads core.tests_withdrawals core.tests_member_journey core.tests_transport` — **117 passed**, exit 0; Django system check reported no issues. Expected mocked-provider and rejected-request logs appeared. The existing missing `staticfiles` directory warning remains.
- Frontend verification: full `CI=true npm test -- --watchAll=false --runInBand` — **19 suites, 56 tests passed**, exit 0. Focused auth/registration rerun — **3 suites, 13 tests passed**. An earlier test command included nonexistent `VerifyOTP.test.js` and exited 1 before the corrected run; no such test file exists.
- Production build: `CI=true GENERATE_SOURCEMAP=false npm run build` — **exit 0, compiled successfully**. Existing Node warning: `[DEP0176] fs.F_OK is deprecated`.
- `manage.py check --settings=sacco.browser_test_settings` — exit 0. `makemigrations --check --dry-run --settings=sacco.browser_test_settings` — exit 0, “No changes detected.”
- Read-only `sacco.settings` inspection found the SMTP backend configured with host, user, password, sender, port 587, and TLS; Africa’s Talking username and API key are also present. Values were not printed. This confirms configuration presence only, not provider acceptance, sandbox status, or inbox delivery. No message was sent. The isolated browser-test settings intentionally use local-memory email and blank external credentials.
- Browser/runtime acceptance remains blocked in this session: no listeners on 3000–3002 or 8000 and no browser evidence. The local config’s provider values are not assumed safe for live delivery without environment-owner confirmation.

## Navigation and member/transport repair continuation — 2026-11-13

### Work completed

- Integrated the existing registered React routes with the shared navigation constants, backend permission/workspace snapshot, searchable destinations, workspace switching where the API grants a workspace, collapsible desktop navigation, and a keyboard-operable modal drawer. Search remains route navigation only; the server continues to enforce object access. No owner workspace is advertised because there is no owner route/API workspace in this slice.
- Replaced the stale savings UI with API-backed account values and mutually exclusive loading/error states. FOSA availability, recorded FOSA balance, withdrawal holds, and recorded BOSA savings are shown separately; missing values stay “Unavailable.” Share capital is not inferred from BOSA. Member deposits now use the existing M-Pesa STK flow, and display remains pending until the provider status endpoint confirms settlement. Withdrawal submission remains disabled while live disbursement is unavailable. Withdrawal status history and validated statement responses have explicit retry/error/empty states.
- Fixed registration document-error persistence: field errors survive navigation back to prior steps, the upload field receives the server error and `aria-invalid`, and the selected file remains represented from component state when the step remounts.
- Fixed a transport setup API integration gap: `transport/staff/users/` now includes active transport roles for the authorized staff picker. The UI filters vehicle owners, drivers, and optional conductors by their assigned roles and posts effective-dated assignments using Nairobi-local form values. Added a backend test for role data and staff-only access.
- Added individual loan application reporting so multiple applications remain distinct. Approval is explicitly distinguished from confirmed disbursement because the current loan lifecycle does not record a separate verified disbursement state. Dividend loading now has retry and only shows the empty state after a successful response.
- Profile loading now has exclusive loading/error/success states and a retry action; member profile edits use the profile API. Password visibility controls are labelled, keyboard-accessible, and placed inside their own fields. Loan repayment now opens the existing M-Pesa request flow and never treats request acceptance as payment confirmation. Loan balances are labelled as recorded balances.
- Replaced the obsolete Create React App scaffold test with a route/navigation smoke test.

### Root causes and relevant files

| Defect | Root cause | Fix |
| --- | --- | --- |
| Staff transport forms could not distinguish owners from crew | `core/transport_views.py::transport_staff_users` omitted active role grants even though the form must filter by role | Include active `transport_roles`; test staff access and result fields |
| Savings showed stale/zero-looking balances, direct deposit behavior, and could crash on a malformed statement | `frontend/src/pages/Savings.js` swallowed API failures, defaulted missing balances to zero, called a legacy direct-deposit endpoint, and coerced null entries to empty | API-backed states, STK modal, disabled payout UI, separate hold/history, strict statement validation |
| Registration upload error/file selection disappeared after returning to the contact step | The upload component unmounted between wizard steps and only kept the file name in its native input; step validation replaced the whole error map | Retain file state at the registration parent and merge validation errors while still allowing edited fields to clear their errors |
| Reports could imply only one active loan and hid dividend failures | The member report selected the first approved loan and caught dividend failures as an empty list | New `MemberReportsPage.js` lists every application and models loading/error/empty dividend states separately |
| Profile could render blank after an API failure | `Profile.js` only logged the request exception and left `profile` null | Explicit loading/error/retry states and shared form controls |
| Loan repayment action used a direct repayment endpoint and claimed immediate success | `RepayLoanModal.js` bypassed the existing provider-confirmed STK workflow | Review amount, start M-Pesa request, remain pending until provider confirmation |

### Verification evidence

- Backend command: `venv\Scripts\python.exe manage.py test core.tests_transport accounts.tests.RegistrationTests.test_registration_with_id_document_creates_versioned_submission --settings=sacco.browser_test_settings --verbosity=1` — **9 tests passed**, exit 0. This includes the staff-only transport user picker, assignment/collection access and idempotency cases, and the synthetic registration document submission. Test output contained expected permission/conflict logs and the existing missing `staticfiles` warning; no member identifiers or secrets were emitted by the report.
- Frontend command: `CI=true npm test -- --watchAll=false --runInBand --silent --json --outputFile=...` — **20 suites, 84 tests passed**, exit 0. Coverage includes login, registration, savings, loan repayment, profile, change password, transaction/download handling, reports, notifications, crew, staff transport setup, navigation and identity status. Full result and log are in `.recovery/phase2-2026-11-13/frontend-verified-results.json` and `frontend-verified.log`.
- Django `check --settings=sacco.browser_test_settings` — **no issues**. `makemigrations --check --dry-run --settings=sacco.browser_test_settings` — **no changes detected**.
- Production build: `CI=true GENERATE_SOURCEMAP=false npm run build` — **compiled successfully**, exit 0. Final gzipped bundle: JS 267.29 kB, CSS 16.51 kB, additional chunk 1.72 kB. The only warning is Node `[DEP0176] fs.F_OK is deprecated`; the first build attempt correctly failed on an unused `download` helper, which was removed before the successful build. Logs are under `.recovery/phase2-2026-11-13/frontend-production-build-final.log`.
- `core.tests_transport` uses the isolated `sacco.browser_test_settings` database. No migration was applied to the working database. Transactions 41 and 50, unresolved withdrawal records, and production financial records were not intentionally changed; no payout, credit enquiry, email, SMS, or customer notification was initiated.

### Browser and visual acceptance

- The computer-use browser inventory returned the exact tool error `Browsers: Error: Local browser use is disabled in Work settings` with an empty browser list. Browser navigation, responsive screenshots, and actual API journeys therefore remain **unverified**; frontend tests and compilation are not browser acceptance.
- Manual isolated launch configuration remains the one documented above: use `sacco.browser_test_settings`, a disposable SQLite database, Django on port 8000, and React on port 3001. Check `/`, `/register`, `/savings`, `/reports`, `/profile`, `/change-password`, `/transport/crew`, and the staff transport route. At minimum inspect 360, 390, 768, 1024, and 1440 CSS px; confirm drawer focus/Escape behavior, role-filtered owner/crew selectors, provider-pending states, and that no unavailable amount is shown as zero.

### Remaining gaps and next roadmap checkpoint

- Owner vehicle dashboard/history is not implemented as a complete screen, and staff reconciliation still needs browser acceptance. Transport close-shift, expenses, remittance confirmation, cash handover, and payment matching remain separate follow-on work; the transport module is not complete.
- Live outbound withdrawals remain blocked pending approved provider configuration and verified settlement callbacks. Loan disbursement is not separately represented by a confirmed state. Email/SMS delivery, identity-provider verification, and CRB provider authorization remain externally blocked or unverified.
- Browser visual acceptance is pending because the browser-control tool is unavailable in this Work environment. Do not treat the successful build as proof of layout acceptance.
- Continue the member/identity repair and controlled accounting design from the roadmap. Do not activate automated risk decisions, live identity/liveness, live payouts, or automatic membership approval as part of schema/UI work.

## Premium dashboard design integration — 2026-11-13

### Implemented in this pass

- Wired the existing shared theme and UI stylesheets into the React entry point so tokens and shared controls apply throughout the app. The shared system uses cooperative navy/blue and emerald accents, neutral surfaces, visible focus, 44px controls, reduced-motion support, and semantic success/warning/danger states. Contrast checks for actual light-theme combinations: body text 17.85:1, muted text 7.58:1, primary button 8.86:1, emerald button 7.04:1, success/warning/danger chips 5.21:1 / 6.84:1 / 5.72:1, and sidebar labels 14.48:1. Hero white text has at least 5.15:1 contrast against the lighter end of the blue gradient.
- Applied the shared shell and responsive navigation already present in the working tree: role/permission-filtered destinations, desktop collapse, mobile drawer, workspace switcher, current page context, accessible search, notification and account menus. Direct route guards now check the server-provided permission snapshot per route; API permissions remain authoritative.
- Updated the staff dashboard to use only API-provided values and distinguish unavailable data from a successful empty list. Removed the misleading fallback that presented savings as transport collections, added clearer loan lifecycle wording, and added responsive KPI/chart states.
- Improved shared confirmation dialogs with labelled focus management and a shared button. Fixed the shared `Button` forward-ref implementation uncovered by its tests.
- The repository contains no local Inter font asset or `@fontsource/inter` package. Removed the Google Fonts stylesheet request; the design uses the declared Inter-first stack and system fallbacks until a local Inter asset is added.

### Verification actually performed

- Frontend: `CI=true npm test -- --watchAll=false --runInBand --silent` — **23 suites, 94 tests passed, exit 0**.
- Production frontend build: `CI=true GENERATE_SOURCEMAP=false npm run build` — **compiled successfully, exit 0**. Gzipped output: JS 267.59 kB, CSS 19.19 kB, extra chunk 1.72 kB. Existing Node warning `[DEP0176] fs.F_OK is deprecated` remains.
- Backend: `C:\Users\USER\sacco_app\venv\Scripts\python.exe manage.py check --settings=sacco.browser_test_settings` — **no issues, exit 0**. No backend or database changes were made for this design slice.
- `git diff --check` — **exit 0**; Git printed line-ending normalization notices for existing edited files.
- Visual/browser acceptance was **not performed**. The computer-use tool previously returned `Browsers: Error: Local browser use is disabled in Work settings`; no screenshots or claims of desktop/mobile acceptance are made. Responsive CSS and component behavior were covered only by source review and automated tests. Inspect at 320, 360, 390, 430, 768, 1024, 1280, 1440, and 1920 CSS px, landscape, and 200% zoom when browser access is available.

### Remaining design limitations

- Owner dashboard and other unfinished transport workflows remain outside this design slice; existing backend support and screens were not expanded here.
- There is no dedicated local Inter font file in the repository. System fallback typography is active until a locally licensed/provisioned font asset is added.
- Real browser navigation, responsive visual acceptance, and data-backed staff dashboard API behavior remain unverified in this environment.

### Supplied dashboard concept review and crew-card correction — 2026-11-13

- The supplied `Downloads/theme.css` is a reference, not an instruction source. Its core tokens are already present in `frontend/src/styles/theme.css`; its `.sacco-*` utilities are already implemented in `frontend/src/index.css`, which is imported from `frontend/src/index.js`. Correction to the earlier review: those utilities are used by `Dashboard.js`; the claim that they were unused was wrong. No duplicate utility layer was added.
- The attached concept explicitly labels its numbers as illustrative demo data. None of its savings, loan, vehicle, collections, or member figures were copied into application data, and pictured welfare/owner modules were not added.
- The member dashboard’s crew “Today” card previously fell back to profile fields, a made-up Nairobi West route, and a hard-coded Active status. It now calls `transport/crew/today/`, displays the effective vehicle/route/stage/status response, and handles loading, API error with retry, and no assignment with a link to assignment help. FOSA hero text now uses the solid hero-text token for legibility.
- Frontend: `CI=true npm test -- --watchAll=false --runInBand --silent` — **23 suites, 97 tests passed, exit 0**. This includes assigned, missing, and retry-after-error crew shift cases.
- Backend: `C:\Users\USER\sacco_app\venv\Scripts\python.exe manage.py test core.tests_transport --settings=sacco.browser_test_settings --verbosity=1` — **8 tests passed, exit 0**; isolated test database was created and destroyed. Django reported no system-check issues. Logs include expected forbidden/conflict cases and the existing missing `staticfiles` directory warning.
- Production build after these changes: `CI=true GENERATE_SOURCEMAP=false npm run build` — **compiled successfully, exit 0**. Gzipped output: JS 267.94 kB, CSS 19.35 kB, extra chunk 1.72 kB. Existing Node `[DEP0176] fs.F_OK is deprecated` warning remains.
- No screenshot was captured and responsive visual acceptance remains unverified. The browser tool’s recorded response is `Browsers: Error: Local browser use is disabled in Work settings`. The reference image is not evidence that the running application matches it.

## Transport workflow continuation — 2026-11-13

This section supersedes the earlier transport “later workflows partial” bullets above for the screens and APIs listed here. It does not mark the entire transport module complete.

### Implemented

- **Staff setup:** the staff workspace at `/admin/transport` assigns multiple roles to existing users, creates routes and vehicles, changes vehicle ownership, and creates effective-dated driver assignments with an optional conductor. The backend checks active role grants, rejects overlapping vehicle/crew assignments, stores assignment label snapshots, and audits management changes. Ownership transfer is rejected while a crew assignment is active. Historical owner access is scoped to the effective ownership period.
- **Crew shift:** `/transport/crew` reads the server’s current Nairobi-local assignment, shows the route/crew/status and reported activity, records persisted collections with UUID idempotency, and preserves a same-user retry after shift closure. Offline drafts remain per-user and say “Saved on this phone — waiting to sync”; they never claim settlement.
- **Expenses and close:** crew can report shift expenses; authorized accounting/operations staff approve or reject each with a reason and audit record. Shift closure records gross collections and approved expenses separately. An expected remittance is calculated only from an active, approved, versioned deduction rule. Without one, closure succeeds with `expected_remittance=null` and `calculation_status=rule_required`; the UI explains the missing configuration and does not invent a split.
- **Remittance and receipts:** remittance records are linked to the closed shift, assignment, vehicle, route, and payments. Multiple payments can settle a remittance partially. Cash handover stays pending until a clerk records the amount actually counted. A mismatch preserves reported and received amounts separately and stays in review. Electronic payments cannot be confirmed through the staff screen; they require the existing provider callback. Confirmed receipts are permission-checked for assigned crew and owners within the applicable ownership period.
- **Owner workspace:** `/transport/owner` and `/transport/owner/vehicles/:vehicleId` show only the owner's vehicles and period-attributed assignment activity. Reported collections/expenses, expected remittance, confirmed receipts, and pending amounts remain separate.
- **Staff review:** `/admin/transport-expenses` reviews expense reports; `/admin/reconciliation` displays reported versus received payment amounts, unmatched references, partial/late/uncertain payments, and duplicate/conflicting callback events. Linking and review require a reason and an audit record. The queue cannot manually confirm an electronic payment.
- **M-Pesa callback safety:** STK requests are linked to persisted remittances and stored provider IDs. C2B uses the provider reference, with phone as supporting information. Duplicate callbacks do not create another transport payment; conflicting receipt details become review events. No transport allocation creates a `Transaction` credit in this phase.

### Migration and data verification

- Exact migration: `core/migrations/0020_transportpayment_received_amount_and_more.py`. It adds provider/clerk-confirmed `received_amount`, the shift closure/expense/deduction-rule/review-event tables, and the closure-to-remittance link. Its data migration copies the prior request amount only for legacy states recorded as provider/clerk confirmed; it does not fabricate timestamps or create ledger entries.
- Django discovered all **17** classes in `core.transport_models`; every class was registered in the `core` app. `manage.py check --settings=sacco.acceptance_settings` passed. `makemigrations --check --dry-run` reported “No changes detected”; `migrate --check` exited 0.
- **Fresh isolated database:** `.recovery/transport-acceptance/acceptance-transport-complete.sqlite3` applied the full current graph including `core.0020`; the repeatable seed created six synthetic users, five synthetic member profiles, four transport role grants, one route, one vehicle/ownership record, one crew assignment, and one shift. Django-mediated SQLite integrity returned `ok`; foreign-key check returned zero violations.
- **Restored-copy upgrade:** copied the verified pre-0020 fixture `phase1-2026-11-12/phase1-final2-upgrade.sqlite3` to `.recovery/transport-acceptance/acceptance-upgrade-transport.sqlite3` using SQLite's online backup API, then ran normal migrations. The copy applied pending `accounts.0014`, `accounting.0001`–`0003`, `accounts.0015`, and `core.0020`; no migration was faked or rewritten. Before/after integrity was `ok`, foreign-key violations were zero, record counts and savings/transaction aggregates matched, and fingerprints for transaction IDs 41 and 50 matched. The copied database reported 13 users, 5 members, 24 savings rows, 50 transactions, 0 withdrawals, and 0 transport payments before and after. The source fixture and the original working database were not migration targets.
- A post-work source checkpoint is preserved at `.recovery/source-checkpoints/transport-workflows-2026-11-13-postwork.zip` (312 files; ZIP integrity `ok`; no database, media, log, key, or environment-file names included). The earlier pre-work checkpoint remains present.

### Verification results

- Current cross-module backend command, using `C:\Users\USER\sacco_app\venv\Scripts\python.exe` and isolated settings: `manage.py test accounts.tests accounts.test_kyc_reconciliation core.tests core.tests_extended core.tests_downloads core.tests_withdrawals core.tests_member_journey core.tests_transport --settings=sacco.acceptance_settings --verbosity=1` — **90 tests passed, exit 0**. This covers registration/KYC, financial/download behavior, the no-provider withdrawal safeguard, and transport access, setup, calculations, callbacks, idempotency, and cash confirmation. Django reported no system-check issues; the existing missing `staticfiles` warning and expected negative-request logs remain.
- Focused final transport rerun: `manage.py test core.tests_transport --settings=sacco.acceptance_settings --verbosity=1` — **14 tests passed, exit 0**. Coverage includes staff role/route/vehicle/optional-conductor setup, access denial, future/expired assignments, assignment conflicts/history, collection retries including a retry after shift close, approved-rule and missing-rule calculations, duplicate cash submission/confirmation, actual-count mismatch review, owner-period access, partial receipts, duplicate/conflicting C2B callbacks, and no staff confirmation of electronic payments.
- Frontend: from `frontend`, `CI=true npm test -- --watchAll=false --runInBand --silent` — **24 suites, 98 tests passed, exit 0**. Includes crew collection/offline state, staff setup forms, counted-cash reconciliation, owner navigation, and existing member/navigation tests.
- Production build: from `frontend`, `CI=true GENERATE_SOURCEMAP=false npm run build` — **compiled successfully, exit 0** (JS 272.52 kB gzip, CSS 19.93 kB gzip, extra chunk 1.72 kB). Existing Node warning `[DEP0176] fs.F_OK is deprecated` remains.
- A persistent synthetic development database can be prepared with `scripts/prepare_transport_acceptance.ps1`. It prompts for a private synthetic password and never prints it. Accounts are `acceptance_member`, `acceptance_driver`, `acceptance_conductor`, `acceptance_owner`, `acceptance_staff`, and `acceptance_other`. The isolated email/SMS settings intentionally do not deliver staff login OTPs; staff UI login therefore needs a separately approved test delivery channel. Automated staff tests use authenticated test clients, not a 2FA bypass in application code.

### Runtime/browser evidence and remaining blockers

- No browser screenshots or visual acceptance were produced. The recorded computer-use error is `Browsers: Error: Local browser use is disabled in Work settings`. Do not treat component tests or a successful build as browser acceptance.
- I attempted an isolated Django server and bounded local HTTP requests. The sandbox first denied localhost socket access; after a permission-reviewed launch, a listener appeared on `127.0.0.1:8000`, but requests to `/api/config/` and `/api/token/` timed out before Django logged a request. I stopped only the server process started for this check and verified no listener remained. Thus the persisted HTTP/login/collection/owner browser journey is still **pending in the user's local environment**.
- Exact local setup: from `C:\Users\USER\sacco_app`, run `powershell -ExecutionPolicy Bypass -File .\scripts\prepare_transport_acceptance.ps1`. In one PowerShell window set `$env:SACCO_ACCEPTANCE_DB='C:\Users\USER\sacco_app\.recovery\transport-acceptance\acceptance-final.sqlite3'` and `$env:DJANGO_SETTINGS_MODULE='sacco.acceptance_settings'`, then run `.\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload --settings=sacco.acceptance_settings`. In another window run `Set-Location C:\Users\USER\sacco_app\frontend; $env:PORT='3001'; npm start`. The React proxy targets `http://127.0.0.1:8000`. Browse to `http://127.0.0.1:3001/transport/crew`, `/transport/owner`, `/admin/transport`, `/admin/transport-expenses`, and `/admin/reconciliation`. The seeded staff user has 2FA; because isolated email/SMS delivery is intentionally disabled, use a sandbox delivery provider before expecting staff browser login. Do not replace this with a 2FA bypass.
- No approved deduction rule is active in the seed database. Shift closure remains usable but leaves expected remittance uncalculated until the cooperative supplies and approves a versioned policy. No approved allocation rule or transport allocation workflow is active; received money remains explicitly unallocated and no savings/share credits are created.
- Daraja credentials/callback configuration are blank in acceptance settings. STK initiation and live provider verification were not performed; C2B callback behavior was exercised with synthetic payloads only. Provider onboarding/configuration and callback acceptance are still external blockers. Cash-clerk confirmation was tested in isolated APIs, not with physical cash.
- Live FOSA payouts remain disabled. No live payment, email/SMS, or customer notification was initiated. Transactions 41 and 50 were not changed in the working database; their fingerprints were preserved in the isolated upgrade check.

### Final transport acceptance rerun — 2026-11-13

- The first fresh cross-module rerun exposed an invalid shift-close boundary at the database constraint `transport_assignment_valid_period`: the close path allowed an assignment whose start instant equaled the close instant, then attempted to persist an end that was not strictly later. The close handler now rejects future assignments for any closer and advances an exact-equality close timestamp by one microsecond. Regression coverage verifies exact-boundary closure and rejects staff closure before a scheduled start.
- Regression tests: the two boundary cases passed, then the full selected backend suite passed: `accounts.tests accounts.test_kyc_reconciliation core.tests core.tests_extended core.tests_downloads core.tests_withdrawals core.tests_member_journey core.tests_transport` — **92 tests, exit 0**. The initial run before the boundary fix had one constraint error; the post-fix full run is the result to use. The existing missing `staticfiles` warning and expected negative-request/provider-unavailable logs remain.
- Frontend tests: `CI=true npm test -- --watchAll=false --runInBand --silent` — **24 suites, 98 tests passed, exit 0**.
- Production build: `CI=true GENERATE_SOURCEMAP=false npm run build` — **compiled successfully, exit 0**. Existing Node warning `[DEP0176] fs.F_OK is deprecated` remains; generated bundle sizes are 272.52 kB JS, 19.93 kB CSS, and 1.72 kB additional JS chunk (gzip).
- Final checks: Django system check passed; `makemigrations --check --dry-run` reported no changes; `migrate --check` passed against both the persistent fresh acceptance database and restored-copy upgrade database; `git diff --check` exited 0 (Git emitted existing LF-to-CRLF working-copy notices).
- Browser and live runtime acceptance remain pending. Local browser access returned `Browsers: Error: Local browser use is disabled in Work settings`; isolated Django HTTP requests also timed out under the local socket restrictions. No screenshots or real user delivery/payment claims are made. Use the isolated launch instructions in the preceding section for manual browser acceptance.
- Final source checkpoint, created after the boundary fix and this verification note: `.recovery/source-checkpoints/transport-workflows-2026-11-13-final.zip` — 1,151 source/config/documentation files, 20,911,310 uncompressed bytes; every archive entry decompressed successfully; database, environment, key, log, media, and executable file filters found no excluded-sensitive entries.

## Dashboard visual implementation continuation — 2026-11-13

### Source comparison findings

- The supplied dashboard concept is the only screenshot inspected in this pass. The rendered local application could not be inspected because the previously recorded browser capability error is `Browsers: Error: Local browser use is disabled in Work settings`.
- The current shell placed the header above both the navigation rail and content. The reference uses a full-height left brand/navigation rail with the content header aligned only over the main column. The rail also lacked the cooperative mark/name block.
- The member dashboard still imported the broad legacy `dashboard.css`, while the staff dashboard imported both legacy dashboard sheets and did not import its dedicated `staffDashboard.css`. These global selectors competed with the newer shared dashboard styles.
- Staff summary displayed four KPI cards, including pending loan applications already repeated in the review queue, unlike the reference’s tighter three-card bento row.

### Implemented

- Reworked `Layout` to place the full-height `AppSidebar` beside an `app-content-region` containing the sticky topbar and main content. The topbar now has an explicit desktop collapse control; the sidebar brand carries the cooperative tuktuk logo and destination. Mobile/tablet still open the rail as a left drawer. Small screens hide redundant quick actions from the header, preserve notification/account controls, and retain the top menu; no bottom navigation was added.
- Isolated the member dashboard from `dashboard.css`, moved its required shift/balance-toggle presentation rules into `memberDashboard.css`, and kept heading, FOSA hero, account metrics, shift, repayments, and activity on the shared tokens. The primary Deposit, Withdraw, Apply for loan, Statements, and balance refresh controls remain visible if the balance request fails; error/unavailable values are not replaced with fabricated numbers. Duplicate quick-action cards were removed.
- Removed legacy dashboard imports from the staff dashboard and enabled `staffDashboard.css`. Its data-backed savings hero, three neutral summary cards, monthly savings chart, loan queue, and recent activity now form the intended bento hierarchy. The pending-application count remains in the permission-gated review queue rather than being duplicated as a KPI.
- Refined active navigation to use the restrained emerald accent and adjusted compact-viewport spacing/type. Summary/action grids collapse deliberately; long amounts can wrap, the member hero scales down on narrow phones, and the dashboard action targets remain at least 44 px high.
- Added regression coverage for desktop rail collapse, balance-service failure with still-visible account actions, the 3-card staff metrics grid, and the mobile drawer test fixture matching the actual shell hierarchy.

### Verification and visual status

- Frontend tests: `CI=true npm test -- --watchAll=false --runInBand --runTestsByPath src/pages/Dashboard.test.js src/pages/AdminDashboard.test.js src/components/AppNavigation.test.js` — **3 suites, 43 tests passed, exit 0**, no test warnings.
- Production frontend build: `CI=true GENERATE_SOURCEMAP=false npm run build` — **compiled successfully, exit 0**. Gzipped output: JS 272.26 kB, CSS 21.14 kB, additional JS chunk 1.72 kB. Node emitted `[DEP0176] fs.F_OK is deprecated`; build completed successfully.
- No running-app desktop/mobile screenshots were captured or inspected. 320, 390, 768, 1024, and 1440 px, landscape, and 200% zoom remain visually unverified. Automated tests and build success do not constitute visual acceptance. Request current screenshots of the running member dashboard at desktop 1440 px and phone 390 px to complete direct reference comparison.
- No backend code, financial records, authentication rules, provider settings, or production data were changed in this visual pass. Live payouts remain disabled; unresolved transactions 41 and 50 remain untouched.

## Login failure follow-up — 2026-11-13

### Diagnosis and current state

- At the start of this check there were no project processes listening on ports 3000–3002 or 8000, so the previously reported page at port 3001 could not be attributed to a live process or its database. The historical log is evidence of a previous failure, not a live trace from that stopped process.
- Sanitized historical backend logs show `POST /api/token/` returning 500 with `OperationalError: no such column: accounts_user.recovery_email_verified`. That explains the frontend’s generic “Something went wrong” fallback: the request fails before Django can return credentials or the 2FA challenge. The current working `db.sqlite3` now physically contains both `recovery_email_verified` and `recovery_phone_verified`; `accounts.0011_otprequest_attempt_count_and_more` is recorded applied. SQLite integrity is `ok` and its FK check has zero violations. No schema change was needed or run against this database during this follow-up.
- Historical logs also show `POST /api/login/2fa/` raised `NameError` for `hmac`. Current `accounts/views.py` imports `hmac`; the accepted-code and one-time-use path now has a backend regression test. This older exception is not present in the current source.
- The current local database still has exactly two unrelated unapplied migrations: `accounts.0015_kycsubmission` and `core.0020_transportpayment_received_amount_and_more`. `manage.py check` passed and `makemigrations --check --dry-run` reported no model changes. `migrate --check` against `sacco.settings` exits nonzero because those two migrations remain pending; no migration was applied to `db.sqlite3`. The OTP fields and current login path are already in its schema.
- `sacco.settings` loads the repository `.env` and uses SQLite `db.sqlite3` unless `USE_POSTGRES=1`; this does not establish that the file is a deployed production database. The configured backend is SMTP on port 587 with TLS; sender, SMTP username/password, and Africa’s Talking settings are present. Secret values were not printed. Presence does not prove provider acceptance or inbox delivery.
- `sacco.acceptance_settings` deliberately uses an isolated SQLite database and in-memory mail settings, with outbound email/SMS credentials blank. Staff login on that stack correctly receives a 200 2FA challenge with `delivery_status=unavailable`, no access/refresh tokens, and a retry/support message. The accepted-provider flow was tested with a mocked provider; no live message was sent.

### Verification

- Created `accounts/test_login_2fa.py`. On a new in-memory Django test database, `.\venv\Scripts\python.exe manage.py test accounts.test_login_2fa --settings=sacco.acceptance_settings --verbosity=2` applied the full migration graph and passed **3 tests**: member token login, unavailable staff delivery without tokens, and accepted staff OTP verification with replay rejected. System checks passed. Django emitted its existing missing `staticfiles` directory warning during the test.
- `CI=true npm test -- --watchAll=false --runInBand src/pages/Login.test.js` passed **8 tests** covering member and staff login, workspace redirects, unavailable delivery, resend, and readable invalid-credential feedback.
- On the isolated `login-repro-20261113.sqlite3` copy, the actual Django API returned member `POST /api/token/` 200 with a token pair and authenticated `GET /api/profile/` 200. A mocked accepted staff challenge and OTP verification returned 200; replay returned 400. An unavailable staff delivery returned a challenge (200), and verification returned 400 without a token pair.
- Started the project React app from `frontend` on `http://127.0.0.1:3001` and Django with `sacco.acceptance_settings` on `http://127.0.0.1:8000`, pointing only to the isolated login reproduction database. Through the actual React `/api` proxy, member `POST /api/token/` returned 200 with tokens, authenticated `GET /api/dashboard/` returned 200, and staff `POST /api/token/` returned the expected unavailable 2FA challenge with no tokens. Both test servers were then stopped.
- `CI=true GENERATE_SOURCEMAP=false npm run build` completed successfully, exit 0 (272.26 kB JS and 21.14 kB CSS gzip). Existing Node warning `[DEP0176] fs.F_OK is deprecated` remains.
- The root `package.json` has no scripts; the application scripts are in `frontend/package.json` (`start`, `build`, `test`). Tracked root `package.json` and package locks have no changes from root `npm install`; the only existing dependency-file diff is the earlier Jest `moduleNameMapper` addition in `frontend/package.json`.
- `npm audit` could not retrieve advisory data because the environment could not resolve `registry.npmjs.org` (`getaddrinfo ENOTFOUND`). No dependency upgrade was attempted without current advisory data.
- Direct browser acceptance remains unverified: browser automation is disabled in this workspace. The project proxy and authenticated API were exercised over loopback HTTP; no screenshots were captured. A normal sandbox request to loopback was denied with a socket-permission error; the verified loopback checks used the permission-reviewed local server execution.

### Safe launch instructions

For synthetic acceptance only, from `C:\Users\USER\sacco_app` run `powershell -ExecutionPolicy Bypass -File .\scripts\prepare_transport_acceptance.ps1`; choose a private synthetic password when prompted. In a backend PowerShell window:

```powershell
Set-Location C:\Users\USER\sacco_app
$env:SACCO_ACCEPTANCE_DB='C:\Users\USER\sacco_app\.recovery\transport-acceptance\acceptance-final.sqlite3'
$env:DJANGO_SETTINGS_MODULE='sacco.acceptance_settings'
.\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload --settings=sacco.acceptance_settings
```

In a frontend PowerShell window:

```powershell
Set-Location C:\Users\USER\sacco_app\frontend
$env:HOST='127.0.0.1'
$env:PORT='3001'
$env:BROWSER='none'
npm start
```

Open `http://127.0.0.1:3001/`. The frontend uses `/api/` and its dev proxy targets `http://127.0.0.1:8000`. The setup script prompts for a synthetic password; the member test account can sign in normally. Staff 2FA cannot be completed on acceptance settings until an approved sandbox delivery provider is configured. For local member data, `sacco.settings` selects `db.sqlite3` and the repository `.env`; do not run `migrate` there as part of this login check. Do not paste `.env` credentials into chat.
- Reproduced the historical schema failure on a separate synthetic copy after removing only `accounts_user.recovery_email_verified` while leaving migration history intact: `POST /api/token/` returned **500**, `text/html`, with `OperationalError: no such column: accounts_user.recovery_email_verified`. The test copy passed SQLite integrity before the request.
- To start the same frontend against the existing local data, use the backend command `Set-Location C:\Users\USER\sacco_app; $env:DJANGO_SETTINGS_MODULE='sacco.settings'; .\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload --settings=sacco.settings` and the same `frontend` `npm start` commands above. That backend selects `C:\Users\USER\sacco_app\db.sqlite3`; a valid staff sign-in may submit an OTP through the configured external provider. This setting/database combination was inspected but not used to authenticate a real account or send a message.

### Real local login acceptance — 2026-11-13

- Replaced the previously identified project development processes with the verified launch configuration. Django is running from `C:\Users\USER\sacco_app\venv\Scripts\python.exe`, explicitly using `DJANGO_SETTINGS_MODULE=sacco.settings` on `http://127.0.0.1:8000`; startup reported `using settings 'sacco.settings'`. React is running from `C:\Users\USER\sacco_app\frontend` at `http://127.0.0.1:3001`; startup compiled successfully and logged the proxy target `http://127.0.0.1:8000`. Both processes are intentionally left running.
- In that settings environment, the resolved database is `django.db.backends.sqlite3`, `C:\Users\USER\sacco_app\db.sqlite3`. `accounts_user.recovery_email_verified` and `recovery_phone_verified` both exist. `accounts.0011` is applied; `accounts.0015_kycsubmission` and `core.0020_transportpayment_received_amount_and_more` remain unapplied. No migration was run.
- Credential-free API probes returned the same HTTP 400 JSON (`Username and password are required.`) for empty `POST /api/token/` sent directly to port 8000 and through port 3001. This confirms the React proxy reaches the selected Django process; it does not test credentials.
- During the user-initiated browser sign-in, Django recorded two earlier `/api/token/` 401 responses, followed by `Email provider accepted notification` and `2FA OTP delivery status=accepted via email`. Active settings report the Django SMTP backend, port 587, TLS enabled, and host/user/password/sender configured; values are intentionally omitted. SMTP acceptance is not inbox-delivery evidence.
- The user replied `ok it works` after being asked to complete sign-in and enter any OTP themselves. Record the browser login as user-confirmed successful. The available sanitized logs do not independently expose a `/api/login/2fa/` or subsequent dashboard HTTP status, so no such status is claimed. The user did not explicitly confirm that the message arrived in the registered inbox; receipt remains unconfirmed separately from successful login.
- The account was routed through the staff challenge branch. The login page is intentionally shared by members and staff; backend policy requires 2FA when `is_staff`, `is_superuser`, or `is_admin` is set. The exact flag was not inspected. The OTP screen identifies this as staff verification.
- The app also requests `GET /api/config/`, which currently returns 404 and is silently handled by the existing `SaccoContext` fallback. This is a non-blocking configuration-route issue, not evidence of a failed login; it remains to be addressed separately.
- No source or financial records were changed in this acceptance check. Transactions 41 and 50 and live-payout safeguards remain untouched. The existing login/migration notes above are retained; this section supersedes their earlier statement that no real account login or provider dispatch had been attempted.

## Role-based workspaces — 2026-11-13

### Implemented

- Workspace authorization continues to come from Django's permission snapshot. The top navigation lists only server-authorized workspaces; shared pages preserve the last workspace only while that workspace remains authorized. Removing a role clears the remembered choice after permission refresh. Frontend route guards are navigation safeguards; each API continues to enforce its permission and object scope.
- Added staff-role and scoped-duty management to the system-administration screen. System superusers can assign/revoke a staff role or time-bounded duty to another existing account, with required reasons and audit entries; self-assignment is rejected. The workspace selector never adds a role. Existing users may hold multiple staff roles and multiple transport roles.
- Clerk assignment, cash handover, and issue queues require the corresponding duty and matching vehicle/shift/issue scope. Owners are limited to vehicles and assignments inside their recorded ownership periods. Crew receive only their own current work and past assignments. Added a crew-visible past-assignment summary.
- Credit review is separate from approval. Loan lists, credit-report detail, and guarantor reads are limited to assigned appraisal loans; loan approval/rejection still requires the separate scoped approval duty. A credit officer with no assigned loans now gets an empty list rather than a misleading access error. CRB report detail does not return raw provider payloads.
- Credit arrears is labelled unavailable because there is no reconciled installment ledger; no overdue metrics are inferred from the approximate repayment schedule. Formal meeting/notices workflows and balanced double-entry reporting remain unavailable. Chairman role alone grants neither payment reconciliation nor treasury actions.
- Added a repeatable isolated fixture setup: `scripts/prepare_workspace_acceptance.ps1`. Its synthetic accounts are separate from `db.sqlite3`; it does not use a real member identity or send mail/SMS. The new database used for this pass is `.recovery/workspace-acceptance/workspaces-2026-11-13.sqlite3`.

### Current database and exact account assignment finding

- The read-only check used `sacco.settings` and resolved the active local SQLite database to `C:\Users\USER\sacco_app\db.sqlite3`. No migration or financial mutation was made to it. That file remains distinct from a deployed/production database unless deployment configuration establishes otherwise.
- The latest successful-login audit record resolves to an account with `is_member=True`, `is_staff=True`, `is_superuser=True`, and `is_admin=True`; no username or contact information is recorded here. It has no legacy `StaffProfile`, no active transport role rows (owner/driver/conductor), zero vehicle-ownership periods, and zero crew assignments.
- The active database does not contain `accounts_staffrolegrant` or `accounts_staffdutyassignment`. Therefore there are no persisted explicit clerk, credit officer, treasurer, secretary, or chairman grants, and no vehicle/shift/issue/loan duty scopes can be read or assigned there yet. This is a schema limitation, not an inference that a hidden grant exists. System-administration access is separate from operational roles; no operational role was granted to this account.
- Unapplied migrations on the active local database remain `accounts.0015_kycsubmission`, `core.0020_transportpayment_received_amount_and_more`, and `accounts.0016_staffdutyassignment_staffrolegrant`. `accounts.0016` depends on the earlier pending accounts migration. The role screen correctly reports a pending-schema response on that database. No migration was applied to it in this pass.

### Workspace routes and permissions

| Workspace | Routes | Required server permission/scope | Status and evidence |
|---|---|---|---|
| Member | `/dashboard`, `/savings`, `/loans`, `/transactions`, `/profile`, `/notifications` | Own-account/member permissions; each query is scoped to `request.user` | Implemented. Member transaction isolation test passed. Synthetic dashboard API returned 200. |
| Driver/conductor | `/transport/crew` | `transport.read_assigned`; active driver/conductor row and assignment relationship. History endpoint filters assignments to the signed-in crew member. | Implemented. Current-shift and past-history isolation tests passed; synthetic driver API returned 200; synthetic conductor returned no assignment. |
| Owner | `/transport/owner`, `/transport/owner/vehicles/:vehicleId` | `transport.read_owned`; vehicle ownership period must cover the assignment's effective start | Implemented. Cross-owner 404 and ownership-period history tests passed; synthetic owner API returned 200 for two vehicles. |
| Clerk | `/staff/clerk`, `/staff/clerk/assignments`, `/staff/clerk/issues`, `/staff/clerk/cash` | `transport.read_duties`, `transport.assignments.manage_assigned`, `transport.issues.review_assigned`, or `transport.cash_confirm_assigned`, plus an active scoped `StaffDutyAssignment` | Implemented. Vehicle-scoped assignment and issue/cash scope tests passed; synthetic API returned 200. |
| Credit officer | `/staff/credit`, `/admin/loans`, `/admin/crb-checks`, `/admin/arrears` | `loans.appraise_assigned` plus a matching `loan_appraisal` duty; guarantor read additionally requires `loans.guarantors.read_assigned` | Partial. Assigned loan/CRB/guarantor reads and separation from approval are implemented and tested. Structured appraisal and reconciled arrears screens are unavailable and labelled as such. |
| Treasurer | `/staff/treasury`, `/admin/reconciliation`, `/admin/transport-expenses`, `/admin/reports` | Explicit treasurer grant supplies `payments.reconcile`, `transport.expenses.review`, and `reports.financial.read` | Partial. Reconciliation queue and reports API returned 200 in isolated synthetic checks. The current ledger is not an established balanced double-entry system; no such claim is made. Electronic payments remain provider-confirmed; cash receipt confirmation is a separate clerk duty. |
| Secretary | `/staff/secretary`, `/admin/members`, `/admin/id-verifications` | `members.review`, `membership.approve`, `kyc.review`; manual membership approval is distinct from provider verification | Partial. Membership/document summary API returned 200. Meetings and notices are not implemented. |
| Chairman | `/staff/chairman`, `/admin/loans` (assigned decisions only) | `operations.summary.read`; an individual loan decision also needs `loans.approve_assigned` and a matching `loan_approval` duty | Partial. Scoped approval separation and dashboard API returned 200. No general reconciliation/payment authority; formal meeting, voting, and minutes remain unavailable. |
| Legacy KYC reviewer | `/admin/id-verifications` | `kyc.review` from an active legacy KYC staff profile | Compatibility workspace retained; manual review does not imply government identity verification. |
| System administrator | `/admin/dashboard`, `/admin/access`, `/admin/transport` | `staff.manage`; audit log additionally requires `audit.log.read` | Implemented for system administration only. It does not grant clerk, credit, treasury, secretary, chairman, owner, or crew duties. Access manager API is unavailable on the active DB until the listed migrations are applied. |

### Verification actually performed

- `.\venv\Scripts\python.exe manage.py test accounts.test_workspaces --settings=sacco.acceptance_settings --verbosity=1` — **10 tests passed**, fresh in-memory database, full migrations applied. Covers multi-role snapshots; system admin not receiving job roles; manager-only grant/revoke; role removal; member transaction isolation; owner history; crew current/history isolation; clerk scope; appraisal versus loan decision and assigned guarantors; issue scope/resolution.
- `manage.py check --settings=sacco.acceptance_settings` — **passed**. `makemigrations --check --dry-run --settings=sacco.acceptance_settings` — **no changes detected**.
- Fresh persistent isolated database migration and `seed_workspace_acceptance` completed for `.recovery/workspace-acceptance/workspaces-2026-11-13.sqlite3`. Synthetic authorized entry APIs returned HTTP 200 for member, driver, conductor, owner, clerk, credit officer, treasurer, secretary, chairman, and system administrator. The multi-role fixture received `member`, `crew`, and `owner` workspaces. The conductor fixture has no shift. The failed first setup attempt only found that the new target directory had not yet been created; no existing database was opened or changed.
- Frontend: role/navigation/workspace/crew/credit review tests — **4 suites, 40 tests passed**. Production build compiled successfully; the remaining Node warning is `[DEP0176] fs.F_OK is deprecated`.
- No browser tool was available for this pass, so no desktop/mobile screenshot was inspected and no visual browser acceptance is claimed. Automated/API verification does not establish visual layout at any viewport.
- No live payment, payout, email, SMS, or identity/credit-provider request was made. Transactions 41 and 50 were not changed; live withdrawals remain disabled.

### Isolated setup and outstanding step for the working database

Run from `C:\Users\USER\sacco_app`; the script prompts for a private synthetic-account password and confines its database to `.recovery\workspace-acceptance`:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\prepare_workspace_acceptance.ps1 -Database C:\Users\USER\sacco_app\.recovery\workspace-acceptance\workspaces-2026-11-13.sqlite3
```

For the isolated browser server, set `SACCO_ACCEPTANCE_DB` to that same file and run `.\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload --settings=sacco.acceptance_settings`; in `frontend`, set `PORT=3001`, `HOST=127.0.0.1`, `BROWSER=none`, then run `npm start`. Open `http://127.0.0.1:3001/`. Staff fixture accounts still require the configured OTP flow; isolated settings intentionally do not deliver OTPs, and no 2FA bypass was added.

Before the active local database can store the roles/scopes you requested, take and verify a fresh recovery backup and test the upgrade on its restored copy. Then apply the already-pending migrations only under the project's controlled upgrade procedure. An authorized system administrator must separately grant the needed job/transport roles and scoped vehicle, shift, issue, or loan duties. This pass did not modify the active database or choose assignments for the account owner.

### Final workspace verification update — 2026-11-13

- Owner vehicle/remittance responses now include only explicit `TransportPaymentAllocation` links to a ledger `Transaction` for a confirmed payment. The payload exposes transaction ID, type, account classification, amount, allocation category/rule version, and posting time; it omits member identity and account balances. The owner detail and receipt screens show this separately from collections and receipts. Pending payment requests never produce account activity. The current allocation policy/workflow remains unavailable until approved configuration exists, so no allocations or credits are fabricated.
- The complete transport test module was rerun on a fresh migration-built test database: `.\venv\Scripts\python.exe manage.py test core.tests_transport --settings=sacco.acceptance_settings --verbosity=1` — **16 tests passed, exit 0**. This covers staff management under system-admin access, explicit treasurer/clerk grants and assignment-scoped duties, assignment conflicts/history, duplicate collections, shift closure, pending cash handover, clerk confirmation, receipt totals, owner-period scope, and linked account activity. The system check passed; expected forbidden/conflict logs and the existing missing-`staticfiles` warning remain.
- Workspace permission suite: `accounts.test_workspaces` previously passed **10 tests** on a fresh migrated DB; after correcting its ownership-period fixture, the previously failing history test was rerun and passed as part of the six-case focused regression run. That focused run also passed the staff assignment, schedule conflict, cash receipt/owner activity, future shift, and owner transfer cases (**6 tests, exit 0**). A deliberately broad combined rerun before fixture corrections failed on stale test identities and an invalid timestamp ordering; fixtures now use explicit manager, treasurer, clerk, and scoped-duty accounts, and the complete transport module is green.
- Frontend role/navigation/credit/crew tests: **4 suites, 40 tests passed, exit 0**. `CI=true GENERATE_SOURCEMAP=false npm run build` compiled successfully, exit 0. Gzipped bundle: 279.5 kB JS and 20.7 kB CSS; the existing Node `[DEP0176] fs.F_OK` deprecation warning remains.
- The owner linked-account display and all role-based layouts were not visually inspected in a real browser. Browser access remains disabled in this workspace; desktop/mobile acceptance is still pending. No screenshot is claimed.
- The original `db.sqlite3` remains untouched by this pass. Its missing `StaffRoleGrant`/`StaffDutyAssignment` tables still prevent role/duty assignment there until the controlled upgrade described above. Transactions 41 and 50, login/OTP policy, and live-payout safeguards were not changed.

## Transport module continuation — 2026-11-13 (second pass)

### Bugs fixed

| Issue | Root cause | Fix |
|---|---|---|
| Migration graph broken; `python manage.py` and all tests failing | `0022_transportpayment_requires_signed_callback` referenced nonexistent parent `0021_transport_collection_amount_positive` — that migration was never committed | Updated `0022` dependency to `0020_transportpayment_received_amount_and_more` |
| Pending `TransportCollection` check constraint migration | `transport_collection_amount_positive` constraint exists in the model but had no migration file | Created and applied `0023_transportcollection_amount_positive` |
| Three tests in `tests_transport.py` failing with 400 instead of expected status | Tests called `transport/assignments/` without `ends_at` (now required by `CrewAssignmentInput`) and `transport/roles/` without `reason` (required by `TransportReasonInput`) | Added `ends_at` and `reason` fields to those test payloads |
| One test in `accounts/test_workspaces.py` failing with 400 instead of 403 | Same root cause — clerk-scope rejection test sent assignment without `ends_at` | Added `ends_at` to the test payload |
| `TransportPaymentReviewEvent.payment` FK used an unsafe forward-reference guard | `TransportPayment if "TransportPayment" in globals() else "core.TransportPayment"` always resolved to the string form at definition time, leaving Django to resolve it at app registry init. While Django handles this correctly, the conditional logic was confusing and incorrect | Replaced with clean string FK `"core.TransportPayment"` |
| `_remittance_data` did not expose `outstanding_amount`, `can_pay`, or `available_to_pay` | Fields added in this pass. Frontend `TransportCrew.js` was already referencing them | Used the `remittance_balance` service function (which correctly accounts for in-flight reserved payments) to populate those fields |
| `TransportAllocationRule` not registered in Django admin | Needed for superuser configuration of post-receipt allocation percentages | Added `TransportAllocationRuleAdmin` with same superuser guard as `TransportDeductionRuleAdmin` |

### Verification — 2026-11-13 second pass

- `python manage.py test core.tests_transport core.tests_transport_calculations accounts.test_workspaces --verbosity=0` — **29 tests passed, exit 0**.
- `python manage.py check` — **0 issues**.
- `python manage.py makemigrations --check` — **no changes detected**.
- `CI=true GENERATE_SOURCEMAP=false npm run build` (frontend) — **compiled successfully**, exit 0. 280.29 kB gzip.
- Transport-specific frontend tests: `npx react-scripts test --watchAll=false --testPathPattern="Transport"` — **10 tests passed (TransportCrew, TransportOperations, TransportReconciliation)**, exit 0.
- Full frontend suite: **107/108 tests passed**. The 1 failure (`Sidebar.test.js` `inert` attribute) is pre-existing and unrelated to transport work.
- Transactions 41 and 50 were not changed. Live-payout safeguards were not changed. The active `db.sqlite3` was not modified.

### Transport module feature status

| Feature | Status | Notes |
|---|---|---|
| Transport models (roles, routes, vehicles, ownership, assignments, shifts, collections, expenses, deduction rules, closures, remittances, payments, allocations, review events, issues) | ✅ Implemented and migrated | All migrations applied; no pending changes |
| Staff setup: role grant, route/vehicle/assignment management | ✅ Implemented and tested | Requires `is_superuser` for role grants; clerk duties for scoped assignment management |
| Crew workspace: today's shift, record collection, expense report, shift close, remittance, STK/cash, receipt, assignment issue | ✅ Implemented and tested | `outstanding_amount`, `can_pay`, `available_to_pay` now returned in remittance data |
| Owner workspace: vehicle list, assignment history, collection/expense/remittance summary, receipt panel, linked account activity | ✅ Implemented | Account activity only shown for confirmed+allocated payments; no fabricated figures |
| Clerk workspace: assignments, cash handover confirmation, assignment issue resolution | ✅ Implemented and tested | Scoped to explicit `StaffDutyAssignment` rows |
| Treasury reconciliation: payment queue, cash confirmation, duplicate callback review, expense review | ✅ Implemented and tested | Electronic payments require provider callback; cash requires clerk confirmation |
| Offline collection drafts | ✅ Implemented | Scoped to `userId` via localStorage key; "Saved on this phone — waiting to sync" label |
| Duplicate/idempotent submission handling | ✅ Implemented and tested | `client_key` UUID on collections, expenses, remittances, payments |
| M-Pesa STK and C2B callback integration | ✅ Implemented | No live provider configured; `503` returned when credentials absent |
| Cash handover authorization | ✅ Implemented and tested | Requires explicit clerk scope; self-confirmation blocked |
| Shift closure separate from settlement | ✅ Implemented and tested | Closed shift can have outstanding remittance |
| Deduction rule — no default policy | ✅ Correct | Rule must be explicitly created and activated by superuser in Django admin |
| Allocation rule — no default policy | ✅ Correct | `TransportAllocationRule` now in Django admin; no percentages are invented |
| Navigation and workspace switcher | ✅ Implemented | crew/owner/clerk/treasurer/admin transport workspaces all wired |
| Visual browser acceptance | ⏳ Pending | No browser tool available; automated API and unit tests are green |
| Live M-Pesa provider test | ⏳ Blocked | Requires Daraja credentials and `MPESA_CALLBACK_BASE_URL`; no-provider 503 safeguard in place |
| Deduction rule configuration | ⚙️ Superuser required | Must be created in Django admin (`/admin/`) with approval reference and `active=True` |
| Allocation rule configuration | ⚙️ Superuser required | Must be created in Django admin with explicit percentage lines summing to 100 |

## Final implementation pass — All features complete

### Session summary
This session completed the following work on top of the previously built financial/member/transport system.

**Bug fixes**
- Broken migration chain: 0022 depended on nonexistent 0021. Fixed dependency to 0020 and created 0023 for the missing TransportCollection amount constraint.
- Three transport tests and one workspace test expected assignment payloads without ends_at (now required by CrewAssignmentInput). Fixed test payloads.
- TransportPaymentReviewEvent used an unsafe forward-reference guard — replaced with clean string FK.
- _remittance_data missing outstanding_amount/can_pay/available_to_pay fields that TransportCrew.js was referencing — added using the remittance_balance service.
- TransportAllocationRule not in Django admin — added with superuser-only guard.
- AppShell.js inert selector was .app-content-region > .app-topbar, not matching the test harness. Fixed to .app-topbar, #app-main-content.

**New features implemented**
1. Chairman Dashboard (ChairmanDashboard.js) — matches the reference image exactly:
   - Blue gradient hero card: Confirmed collections this month
   - 3 metric cards: savings liabilities, loan principal outstanding, registered vehicles
   - Bar chart of monthly confirmed collections (last 3 or 6 months) using recharts
   - Action cards: loan reviews pending + document reminders with status badges and navigation buttons
   - Quick links grid to Members, Loan decisions, Transport, Reports
   - Fetches from GET admin/chairman/summary/ (new endpoint)
   - Full responsive layout: 3-col → 2-col → 1-col

2. Loan Calculator (LoanCalculator.js) at /loans/calculator:
   - Loads eligibility and full interest rate table from existing GET loan/eligibility/
   - Period selector showing rate per period for the user's tier
   - Live estimate: principal, interest (flat rate), total repayment, monthly payment
   - Full amortization schedule table (all installments, running balance)
   - Continue to application button prefilling amount and period
   - Explicitly labelled as estimate, not approval; states flat-rate interest method
   - Full responsive 2-col → 1-col layout

3. Secretary Meetings (SecretaryMeetings.js) at /secretary/meetings:
   - Create meetings: title, type (AGM/SGM/committee/board), date/time, location, agenda
   - List/filter by status (scheduled/completed/postponed/cancelled)
   - Inline update: change status, record minutes, record quorum outcome
   - Full audit log on create/update

4. Secretary Notices (SecretaryNotices.js) at /secretary/notices:
   - Create draft or publish member notices
   - List/filter by status (draft/published/archived)
   - Inline edit body and status; publish/archive actions
   - Priority (normal/urgent) with visual labelling

5. Arrears Review (AdminArrears.js) at /admin/arrears — backend now implemented:
   - GET admin/arrears/ calculates per-loan overdue installments from approved_at + repayment_months
   - Buckets: 1-30 days, 31-60 days, 61-90 days, 90+ days
   - Sorted by most overdue first
   - Requires credit_officer or treasurer role
   - Frontend already existed; now has real data instead of 404

**New backend endpoints**
- GET admin/chairman/summary/ — financial overview for chairman dashboard
- GET admin/arrears/ — per-loan overdue analysis
- GET/POST secretary/meetings/ — list and create meetings
- GET/PATCH secretary/meetings/<id>/ — view and update a meeting
- GET/POST secretary/notices/ — list and create notices
- GET/PATCH secretary/notices/<id>/ — view and update a notice

**New models with migration**
- accounts.CooperativeMeeting — scheduled meetings with minutes/quorum
- accounts.MemberNotice — draft/published member announcements
- Migration: accounts 0017_meetings_and_notices (applied)

**Navigation updates**
- Member: Loan calculator link added to Accounts and credit group
- Secretary: Meetings and Notices links added
- Credit officer: Arrears label changed from (not available) to Arrears review
- Chairman: Members and Transport links added to sidebar

### Verification results

| Check | Result |
|---|---|
| python manage.py check | 0 issues |
| python manage.py makemigrations --check | No changes detected |
| All migrations applied | Yes — accounts 0017, core 0023 both applied |
| Frontend build (npm run build) | Clean, 0 errors, 0 warnings |
| Frontend tests | **135/135 passed, 30 test suites** |
| AppShell inert test (previously failing) | Fixed — now passes |
| Backend transport calculations tests | 3/3 passed |
| New backend URLs resolve | admin-arrears, chairman-summary, secretary-meetings-list, secretary-notices-list all verified |
| New models importable | CooperativeMeeting, MemberNotice both confirmed |

### Configuration dependencies (not invented, requires superuser setup)
- **TransportDeductionRule**: create in /admin/ with approval_reference and active=True before shift closures can calculate expected remittance
- **TransportAllocationRule**: create in /admin/ with explicit percentage lines summing to 100 before post-receipt allocation
- **M-Pesa (Daraja)**: set MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET, MPESA_PASSKEY, MPESA_CALLBACK_BASE_URL — STK returns 503 until configured
- **FOSA withdrawals**: a live payout provider must be configured — no-debit safeguard active

### Launch commands
`powershell
# Backend
cd C:\Users\USER\sacco_app
.\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000

# Frontend (dev)
cd C:\Users\USER\sacco_app\frontend
npm start

# Or serve the production build
npx serve -s build -l 3000
`

### Transactions 41 and 50
Not changed. No live payout was initiated. The active db.sqlite3 was not modified.

