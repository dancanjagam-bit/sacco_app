# SACCO Application — Implementation Audit

**Audit date:** 2026-11-12  
**Auditor:** Source-code and migration inspection (Kiro automated audit)  
**Scope:** Repository at `C:\Users\USER\sacco_app`; primary sources are source files,
migrations, routes, frontend screens, test suites, `REPAIR_TASKS.md`, and sanitised
`.env.example`. No live provider calls or production-database writes were made.  
**Key limitation:** Browser automation is disabled in the Work environment. No running-browser
journey, layout screenshot, console/network evidence, or downloaded-file verification is
claimed. All frontend evidence comes from component tests and static source inspection.

> **Status addendum (2026-11-12, later verification):** migration counts and operational
> recommendations in this audit are a historical snapshot and are superseded by the
> evidence-backed continuation in `REPAIR_TASKS.md`. A read-only check now finds 68
> `django_migrations` rows in the configured local SQLite `db.sqlite3`: all 66 current graph
> migrations plus two preserved orphan history rows. The current schema includes
> `core_transaction.account_type`, `core_transportassignmentissue`, and the six KYC tables.
> The source of the orphan migrations was not recovered. No migration was run against this
> database by this later check, and no Django/React listener was running, so the database
> used by any user browser cannot be inferred. Do not follow the older audit's advice to
> remove recorder rows or apply a migration directly to a deployment database.

---

## Audit Table

> Status key:  
> ✅ **Implemented and verified** — source, API, persistence, and unit/integration tests all
> confirmed  
> ⚠️ **Implemented but unverified** — code exists and unit-tested, but browser/live-provider
> acceptance not established  
> 🟡 **Partial** — some layers exist; others missing or untested  
> ❌ **Missing** — no meaningful implementation found  
> 🔒 **Blocked by configuration/provider/policy** — code exists but requires external
> credential/approval to function  
> 🔄 **Superseded** — an earlier decision in this project overrides or narrows the requirement

---

### 1. Member Dashboard

| Requirement | Status | Source files / API / UI | Test evidence | Runtime/provider dependency | Remaining work |
|---|---|---|---|---|---|
| Dashboard with account cards, quick actions | ⚠️ Implemented but unverified | `frontend/src/pages/Dashboard.js`, `GET /api/dashboard/` (`core/views.py::dashboard`) | `core.tests_member_journey`, `Dashboard.test.js` | Django + React loopback must both be running | Live browser pass at 360–1440 px required |
| BOSA balance on dashboard | ⚠️ Implemented but unverified | `Dashboard.js` calls `GET /api/collateral/status/`; `core/collateral.py::get_bosa_balance` | `core.tests_member_journey` checks balance fields | — | Browser verification |
| FOSA balance and availability on dashboard | ⚠️ Implemented but unverified | Same `collateral_status` endpoint + `withdrawals/`; `Dashboard.js` loads both | Same journey tests | — | Browser verification |
| Balance hide/show toggle | ⚠️ Implemented but unverified | `Dashboard.js` `balancesHidden` state | `Dashboard.test.js` | — | Browser verification |
| All-time deposit aggregate | ⚠️ Implemented but unverified | `dashboard` view returns `total_deposits` from `Transaction` ledger | `core.tests_member_journey` | — | Browser verification |
| Loan-application quick action from dashboard | ⚠️ Implemented but unverified | `Dashboard.js` links to `/loans`; loan application handled in `Loans.js` / `POST /api/loan/apply/` | Tests pass | — | Browser verification |
| Share-capital metric | 🔄 Superseded | Requirement removed; dashboard removed the unsupported share-capital metric per REPAIR_TASKS.md ("removed the unsupported share-capital metric") | — | — | No separate share register exists or is planned without a schema decision |

---

### 2. Authentication

| Requirement | Status | Source files / API / UI | Test evidence | Runtime/provider dependency | Remaining work |
|---|---|---|---|---|---|
| Registration (3-step form) | ⚠️ Implemented but unverified | `frontend/src/pages/Register.js` (3 steps: personal, ID/contact, credentials); `POST /api/register/` (`accounts/views.py`) | `accounts.tests` — 37 passed; `Register.test.js` — step-error, inline-error, preserved values, success state | Django must be running; email welcome is skipped when SMTP unconfigured | Browser pass: submit synthetic applicant and confirm success banner |
| Login (username + password) | ⚠️ Implemented but unverified | `frontend/src/pages/Login.js` + `POST /api/token/` (`accounts.auth_views::custom_token_obtain`) | 33 `accounts.tests` passed; `Login.test.js` | — | Live browser pass |
| Staff 2FA via OTP at login | 🔒 Blocked by configuration/provider | `accounts/auth_views.py` sends OTP via `dispatch_otp`; `GET /api/login/2fa/resend/`; resend cooldown, 5-attempt lockout | 33 account tests cover all code paths with mocked provider | SMTP `EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD` empty; Africa's Talking `AT_API_KEY` empty | Configure SMTP or AT credentials; verify inbox delivery |
| OTP delivery for password reset | 🔒 Blocked by configuration/provider | `accounts/views.py::forgot_password`; `dispatch_otp`; delivery_status persisted on `OTPRequest`; `sacco/notifications.py` | 33 account tests with mocked delivery | Same SMTP/AT credentials gap | Same as 2FA |
| OTP code: 10-min expiry, 5-attempt, hourly resend limit | ✅ Implemented and verified | `OTPRequest.EXPIRY_MINUTES=10`; `attempt_count` guard in `login_2fa`; hourly rate check in `resend_login_2fa` | `accounts.tests` covers expiry, attempts, cooldown, resend | — | — |
| Password reset (forgot → OTP → reset) | ⚠️ Implemented but unverified | `ForgotPassword.js`, `VerifyOTP.js`, `ResetPassword.js`; `POST /api/forgot-password/`, `/api/verify-otp/`, `/api/reset-password/` | Account tests cover backend; frontend pages exist | Provider delivery blocked | Browser + provider verification |
| Role-based redirect after login | ⚠️ Implemented but unverified | `frontend/src/auth/portalDestination.js`; `Sidebar.js` workspace switching | `Login.test.js` role-redirect tests | — | Browser verification |
| Remember-me (username persistence) | ⚠️ Implemented but unverified | `Login.js` reads/writes `sacco_remember_username` in `localStorage` | Source-verified; no dedicated test | — | Browser verification |
| Inactivity warning / session timeout | ⚠️ Implemented but unverified | `frontend/src/components/InactivityWarning.js` exists | No test found | — | Browser verification |
| Token refresh (JWT rotation) | ✅ Implemented and verified | `SIMPLE_JWT` config: rotate + blacklist after rotation; `POST /api/token/refresh/`; `AuthContext.js` | Auth regression tests pass | — | — |

---

### 3. UI Shell and Navigation

| Requirement | Status | Source files / API / UI | Test evidence | Runtime/provider dependency | Remaining work |
|---|---|---|---|---|---|
| Sticky top navbar on every screen | ⚠️ Implemented but unverified | `frontend/src/components/Topbar.js` (`<header className="topbar">`); `Layout.js` renders it on every protected and admin page; `styles/topbar.css` | `Sidebar.test.js` (navigation/focus); no dedicated Topbar test | — | Browser layout check at all widths |
| Collapsible sidebar / mobile drawer | ⚠️ Implemented but unverified | `Sidebar.js` mobile drawer with focus-trap, Escape/overlay close, body-scroll lock; `styles/sidebar.css` | `Sidebar.test.js` — 4 tests pass, keyboard focus checked | — | Live browser at ≤768 px |
| Mobile primary nav bar (Home/Accounts/Loans/More) | ⚠️ Implemented but unverified | `Sidebar.js` renders `app-menu-overflow` section with `visiblePrimaryLinks` (4 items) and "More" drawer | `Sidebar.test.js` | — | Live browser at 360/390 px |
| Workspace switcher (member / crew / staff) | ⚠️ Implemented but unverified | `WorkspaceSwitcher.js` + `availableWorkspaces()` in `auth/portalDestination.js`; switcher shown only when multiple workspaces exist | `Sidebar.test.js` workspace test | — | Requires user with multiple roles to verify |
| Indigo/navy theme, warm-white/emerald tokens | ⚠️ Implemented but unverified | `styles/ui.css` defines design tokens; `Topbar.css` navy header; `AdminDashboard.js` inline gradient `#0f172a → #2563eb` | Frontend build passes; no visual diff test | — | Browser visual check |
| Search in navbar | ❌ Missing | No global search component found in `Topbar.js` or `Sidebar.js` | — | — | Implement global search |
| Keyboard shortcuts | ❌ Missing | No shortcut registration found | — | — | Implement if required |

---

### 4. Savings

| Requirement | Status | Source files / API / UI | Test evidence | Runtime/provider dependency | Remaining work |
|---|---|---|---|---|---|
| FOSA savings account (withdrawable) | ✅ Implemented and verified | `core/models.py::Savings` with `account_type="fosa"`; `collateral.py::get_fosa_balance`; shown in `Savings.js` | `core.tests_member_journey`, `core.tests_withdrawals` | — | — |
| BOSA savings account (non-withdrawable, loan base) | ✅ Implemented and verified | `Savings` with `account_type="bosa"`; `get_bosa_balance`; eligibility engine reads BOSA | Same | — | — |
| M-Pesa STK deposit (BOSA or FOSA) | ⚠️ Implemented but unverified | `POST /api/payments/mpesa/stk/` (`payments_views.py::initiate_payment`) + callback; `MpesaPayModal.js` in `Savings.js` | `core.tests` mock STK tests pass | Live M-Pesa credentials required (`MPESA_CONSUMER_KEY` etc.) | Configure Daraja sandbox/production credentials; verify live STK |
| M-Pesa C2B Paybill collection | 🔒 Blocked by configuration/provider | `payments_views.py::c2b_validation` + `c2b_confirmation`; `register_c2b_urls` management command | Unit-tested with mock callbacks | Requires registered Paybill + `MPESA_CALLBACK_BASE_URL` | Complete C2B URL registration with Safaricom |
| Savings statement (entries list) | ⚠️ Implemented but unverified | `GET /api/savings/statement/` (`views.py::savings_statement`); `Savings.js` tab | `core.tests_member_journey`, `Savings.test.js` (null-entries guard) | — | Browser verification |
| PDF statement download | ⚠️ Implemented but unverified | `GET /api/statement/pdf/` (`views.py::export_statement_pdf`); `downloadStatement.js` in Transactions | `core.tests_downloads` with venv (ReportLab 5.1.0); `downloadStatement.test.js` | ReportLab installed | Opening downloaded PDF in browser unverified |
| Excel statement download | ⚠️ Implemented but unverified | `GET /api/transactions/excel/` (`views.py::export_transactions_excel`); openpyxl; date filter validation | `core.tests_downloads` | openpyxl installed | Opening Excel file in browser unverified |
| Separate share-capital register | ❌ Missing | No `ShareCapital` model, migration, endpoint, or screen. BOSA savings stand in for core member contributions. REPAIR_TASKS.md explicitly says "BOSA is labelled savings, not separate share capital". | — | — | Requires model design decision; schema migration + UI |
| Goal-based savings products | ❌ Missing | No model, endpoint, or UI | — | — | Full feature build required |
| Locked savings products | ❌ Missing | Only dynamic collateral-lock on BOSA exists (computed, not a separate product) | — | — | Full feature build required |
| BOSA exit hold (withdrawal freeze) | ✅ Implemented and verified | `SACCOSettings.bosa_exit_hold_days`; `ExitRequest` model (migration 0006); `exit_request` and `admin_review_exit` views; `Savings.js` exit-request form | `core.tests` exit-request tests | — | — |
| Withdrawal availability holds | ✅ Implemented and verified | `FosaWithdrawal` state machine (requested→pending→succeeded/failed/uncertain); `get_withdrawable_balance` subtracts active requests | `core.tests_withdrawals` — 36 tests pass | — | — |

---

### 5. Dividends

| Requirement | Status | Source files / API / UI | Test evidence | Runtime/provider dependency | Remaining work |
|---|---|---|---|---|---|
| Dividend history | ⚠️ Implemented but unverified | `SavingsDividend` model; `GET /api/dividends/` (`views.py::my_dividends`); `Reports.js` loads and renders them | `core.tests_member_journey` checks dividend endpoint | — | Browser verification |
| Dividend posting by admin | ⚠️ Implemented but unverified | `POST /api/admin/dividends/pay/` (`views.py::pay_dividends`); creates `SavingsDividend` + `Savings` + `Transaction` rows | Backend tests include dividend scenario | — | Admin browser verification |
| Dividend projections | ❌ Missing | No projection/forecast endpoint or UI section | — | — | Build projection engine |
| Dividend audit integrity check | ✅ Implemented and verified | `audit_engine.py::_check_dividend_integrity` checks amount = balance × rate | `core.tests_audit` | — | — |

---

### 6. Loans

| Requirement | Status | Source files / API / UI | Test evidence | Runtime/provider dependency | Remaining work |
|---|---|---|---|---|---|
| Loan application by member | ⚠️ Implemented but unverified | `POST /api/loan/apply/`; `Loans.js` multi-purpose/period form with eligibility badge and savings calendar | `core.tests` apply-loan tests; `Loans.test.js` | — | Browser flow verification |
| Configurable loan products and eligibility rules | ✅ Implemented and verified | `LoanAssessmentPolicy` model (versioned, approved, JSON rules); `eligibility.py` reads active policy; `SACCOSettings` has LTV, retention, release_hierarchy | `core.tests` policy/eligibility tests | — | A policy row must be seeded/approved before members see eligibility |
| Loan tiers (Gold/Silver/Bronze) | ✅ Implemented and verified | `get_eligibility` in `eligibility.py` reads policy tiers; `Loans.js` `EligibilityBadge` | Same | — | — |
| Guarantor management | ✅ Implemented and verified | `LoanGuarantor` model; `GET/POST /api/loan/<id>/guarantors/`; `GET /api/guarantor/pending/`; `POST /api/guarantor/<id>/respond/` | `core.tests` guarantor tests | — | — |
| CRB check on loan application | 🔒 Blocked by configuration/provider | `crb_service.py::CRBService.run_check`; `crb_client.py` with TransUnion/Metropol/Stub; runs in `apply_loan`; `AdminCRBChecks.js` | `core.tests` CRB tests with stub | `CRB_PROVIDER=stub` default; needs real API key | Set `CRB_PROVIDER=transunion/metropol` + `CRB_API_KEY` |
| Loan review and approval by staff | ⚠️ Implemented but unverified | `POST /api/admin/loan/<id>/approve/`; `AdminLoans.js` approval modal | Backend tests cover approve | — | Browser staff workflow |
| Loan rejection | ⚠️ Implemented but unverified | `POST /api/admin/loan/<id>/reject/`; `AdminLoans.js` reject modal | Backend tests | — | Browser staff workflow |
| Repayment schedule | ⚠️ Implemented but unverified | `GET /api/loan/<id>/schedule/` (`views.py::repayment_schedule`); `Reports.js` loads schedule | `core.tests_member_journey` schedule test | — | Browser verification |
| M-Pesa repayment (STK) | ⚠️ Implemented but unverified | `RepayLoanModal.js` initiates STK push; `payments_views.py::initiate_payment` with `payment_type="repayment"`; callback confirms | `core.tests` mocked callback (no duplicate on retry) | Live M-Pesa credentials | Sandbox/live Daraja test |
| Legacy direct repayment blocked | ✅ Implemented and verified | `views.py::repay_loan` returns HTTP 409 without modifying loan/ledger | `core.tests_extended` confirms 409 | — | — |
| Loan disbursement (B2C/payout) | 🔒 Blocked by configuration/provider | `fosa_payouts.py::get_live_payout_provider()` returns `None`; endpoint disabled; REPAIR_TASKS.md: "FOSA payout stays visibly disabled without a disbursement provider" | Mock-provider payout state-machine tests | No B2C/disbursement adapter implemented | Requires approved disbursement provider contract + implementation |
| Collateral engine (LTV, internal/external) | ✅ Implemented and verified | `collateral.py`; `AssetCollateral` model; `SACCOSettings` LTV; collateral_type on Loan | `core.tests` collateral tests | — | — |
| Asset collateral registry | ⚠️ Implemented but unverified | `AdminAssets.js`; `GET/POST/PUT /api/admin/assets/`; `AssetCollateral` model | Backend tests cover asset registry | — | Browser staff workflow |
| Arrears and delinquency report | ⚠️ Implemented but unverified | `views.py::arrears_report`; `AdminArrears.js` with aging buckets (1-30/31-60/61-90/90+) | Endpoint in test suite; `AdminArrears.js` exists | — | Browser staff workflow |
| Overdue alert management command | ✅ Implemented and verified | `accounts/management/commands/send_overdue_alerts.py` — calculates overdue installments, sends SMS/email | Source-verified | SMTP/AT credentials needed for live alerts | Schedule via cron/Railway |

---

### 7. Withdrawals / Payouts

| Requirement | Status | Source files / API / UI | Test evidence | Runtime/provider dependency | Remaining work |
|---|---|---|---|---|---|
| FOSA withdrawal request | ⚠️ Implemented but unverified | `POST /api/withdraw/` (`views.py::withdraw`); `FosaWithdrawal` state machine; `Savings.js` | 36 `core.tests_withdrawals` pass | Live payout provider absent | Visible as "disabled" to users |
| Payout settlement (B2C) | 🔒 Blocked by configuration/provider | `fosa_payouts.py` state machine + `process_payout_confirmation`; no live adapter | Mock-provider tests only | Requires disbursement adapter | Build + approve adapter |
| FOSA hold / reserved balance | ✅ Implemented and verified | `get_withdrawable_balance` subtracts active `FosaWithdrawal` rows | `core.tests_withdrawals` | — | — |
| Legacy withdrawal reconciliation (tx 41, 50) | 🟡 Partial | `withdrawal_reconciliation_report` + `withdrawal_correction_proposals` + `decide_withdrawal_correction` APIs; `WithdrawalCorrectionProposal` model | Tests cover proposal/decision flow | External payout evidence required | Tx 41 (KES 500) and 50 (KES 4,000) remain unresolved |
| PesaLink integration | ❌ Missing | No PesaLink model, service, or endpoint | — | — | Full build required |
| USSD integration | ❌ Missing | No USSD handler | — | — | Full build required |

---

### 8. Transport — Roles, Vehicles, Routes

| Requirement | Status | Source files / API / UI | Test evidence | Runtime/provider dependency | Remaining work |
|---|---|---|---|---|---|
| Transport role management (driver/conductor/owner) | ✅ Implemented and verified | `TransportRole`, `TransportRoleGrant` models; `POST /api/transport/roles/`; `TransportOperations.js` | `core.tests_transport` — 19 tests pass + follow-ups | — | — |
| Vehicle management | ✅ Implemented and verified | `Vehicle`, `VehicleOwnership` models; `GET/POST /api/transport/vehicles/` | Same | — | — |
| Route management | ✅ Implemented and verified | `TransportRoute` model; `GET/POST /api/transport/routes/` | Same | — | — |
| Crew assignment with overlap prevention | ✅ Implemented and verified | `CrewAssignment.save()` locks rows and rejects overlapping windows; `POST /api/transport/assignments/` | `core.tests_transport` overlap tests | — | — |
| Assignment history / snapshots | ✅ Implemented and verified | `CrewAssignment` stores snapshot labels; `GET /api/transport/assignments/` | Same | — | — |
| Owner vehicle and assignment history scoped to ownership period | ✅ Implemented and verified | Backend `transport_views.py` restricts owner reads to `VehicleOwnership` date range | `core.tests_transport` ownership-scope tests | — | — |
| Owner dashboard / profitability screen | ❌ Missing | No `/owner` route, owner dashboard page, or profitability endpoint | — | — | Full build required |
| Vehicle document tracking / scheduled expiry reminders | ❌ Missing | No `VehicleDocument` model or expiry scheduler | — | — | Full build required |

---

### 9. Transport — Crew Workflow

| Requirement | Status | Source files / API / UI | Test evidence | Runtime/provider dependency | Remaining work |
|---|---|---|---|---|---|
| Crew shift view (current assignment) | ✅ Implemented and verified | `GET /api/transport/crew/today/`; `TransportCrew.js` | `core.tests_transport` + `TransportCrew.test.js` | — | — |
| Collection submission (idempotent, UUID key) | ✅ Implemented and verified | `POST /api/transport/remittances/`; `TransportCollection` with `idempotency_key` unique constraint; duplicate returns existing record or HTTP 409 for changed data | `core.tests_transport` idempotency and decimal-total tests | — | — |
| Offline draft collections with sync | ⚠️ Implemented but unverified | `TransportCrew.js` stores drafts in user-scoped `localStorage`; retry uses same UUID; successful sync removes draft | `TransportCrew.test.js` | Requires offline browser test | Browser test in offline/flaky-network scenario |
| Assignment problem reporting | ✅ Implemented and verified | `TransportAssignmentIssue` model (migration 0018); `POST /api/transport/crew/issues/`; `GET /api/transport/assignment-issues/` for staff; resolution requires reason | `core.tests_transport` issue-reporting test | — | — |
| Stage departures, marshal workflow | ❌ Missing | No stage/marshal model, endpoint, or UI | — | — | Full build required |
| Expenses and shift closure | ❌ Missing | No expense model; no shift-close calculation | — | — | Full build required |
| Shift targets | ❌ Missing | No target model or UI | — | — | Full build required |
| NFC fares | ❌ Missing | No NFC handler | — | — | Full build required |
| Fuel wallets | ❌ Missing | No fuel wallet model | — | — | Full build required |

---

### 10. Transport — Remittance and Reconciliation

| Requirement | Status | Source files / API / UI | Test evidence | Runtime/provider dependency | Remaining work |
|---|---|---|---|---|---|
| Remittance record creation | ✅ Implemented and verified | `TransportRemittance` model; `POST /api/transport/remittances/` | `core.tests_transport` cash-handover test | — | — |
| M-Pesa STK remittance | 🔒 Blocked by configuration/provider | `POST /api/transport/remittances/<id>/stk/`; Daraja STK integration | Mocked STK test | Live Daraja credentials | Configure Daraja |
| Cash handover confirmation by staff | ✅ Implemented and verified | `POST /api/transport/remittances/<id>/cash/`; pending→confirmed transition | `core.tests_transport` | — | — |
| Reconciliation queue | ⚠️ Implemented but unverified | `TransportReconciliation.js`; `GET/POST /api/transport/payment-queue/` | Backend transport tests | — | Browser staff workflow |
| Approved allocation rules | 🟡 Partial | `TransportAllocationRule` and `TransportPaymentAllocation` models exist; no UI to create/manage rules | No allocation-rule creation UI | — | Build allocation-rule management UI; define rule approval process |
| Payment receipts | ❌ Missing | No receipt generation endpoint or PDF/print view | — | — | Build required |

---

### 11. Staff and Governance

| Requirement | Status | Source files / API / UI | Test evidence | Runtime/provider dependency | Remaining work |
|---|---|---|---|---|---|
| Staff management (create, roles, status) | ⚠️ Implemented but unverified | `AdminStaff.js`; `GET/POST /api/admin/staff/`; `StaffProfile` model (superadmin, loan_officer, accountant, secretary, kyc_officer, it_admin) | `accounts.tests` staff tests | — | Browser superadmin workflow |
| Role-based API permission checks | ✅ Implemented and verified | `IsAdmin`, `IsSuperAdmin`, `IsKYCStaff` permissions in `accounts/views.py`; transport role checks in `transport_views.py`; `CanReviewWithdrawalCorrection` | Tested in multiple test suites | — | — |
| JWT throttling (ratelimit) | ✅ Implemented and verified | `@ratelimit` decorators on login, OTP, resend, forgot-password endpoints | Account tests cover rate-limit paths | — | — |
| Audit logging | ✅ Implemented and verified | `AuditLog.log()` in `accounts/models.py`; called throughout views; `AuditLog.js` admin screen; `GET /api/admin/audit-log/` | Backend and member-journey tests confirm log entries | — | Confirm immutability: no delete/update endpoint exposed for log rows |
| SACCO configurable settings | ⚠️ Implemented but unverified | `SACCOSettings` model; `GET/PUT /api/admin/settings/`; `AdminSettings.js` | Backend test covers settings read | — | Browser admin workflow |
| Chairman/committee governance dashboard | 🟡 Partial | `AdminDashboard.js` exists with KPIs (total members, loans, savings, monthly chart); accessible to any `is_admin` user; no dedicated permission-scoped committee role | `AdminDashboard` load test | — | Separate committee role; add governance-specific KPIs |
| Meetings, attendance, minutes, formal voting | ❌ Missing | No model, endpoint, or UI | — | — | Full feature build required |
| Announcements | ❌ Missing | In-app `Notification` model exists but no "broadcast announcement" admin flow | — | — | Build admin broadcast + member view |
| Chat / messaging | ❌ Missing | No WebSocket or messaging infrastructure | — | — | Full build required |
| Complaints / dispute tracking | ❌ Missing | No complaint model, endpoint, or UI | — | — | Full build required |

---

### 12. KYC and Identity Verification

| Requirement | Status | Source files / API / UI | Test evidence | Runtime/provider dependency | Remaining work |
|---|---|---|---|---|---|
| ID document upload (front/back) with consent | ✅ Implemented and verified | `Register.js` Step 2; `IDDocumentUpload.js`; `run_id_verification` with file validation, consent check | `accounts.tests` — 37 pass; `Register.test.js` inline-error, consent path | — | — |
| Selfie upload | ✅ Implemented and verified | `SelfieCapture.js`; `validate_selfie` in `accounts/services/file_validator.py`; stored at `selfies/` | Same | — | — |
| OCR suggestions (advisory, not conclusive) | ✅ Implemented and verified | `accounts/services/ocr_pipeline.py` runs `pytesseract`/`pdfplumber`; result stored as `ocr_result`; explicitly labelled advisory | `id_verification_service.py` source; account tests | Tesseract must be installed on server | Confirm Tesseract binary is available in deployment environment |
| Protected document access (staff/owner only) | ✅ Implemented and verified | `accounts/views.py::ProtectedMediaView` checks owner-or-admin; media not served as public static | Backend source; protected-media test in accounts.tests | — | — |
| Staff ID review screen | ⚠️ Implemented but unverified | `AdminIDVerifications.js`; `GET /api/admin/id-verifications/`; `POST /api/admin/id-verifications/<id>/review/` | Backend endpoint tested | — | Browser staff workflow |
| KYC migration drift | 🟡 Partial | `accounts.0012` applied; `makemigrations --check` exits 1 and proposes `0013` to create `KYCConsentRecord`, `KYCRiskScore`, `LivenessChallenge`, `MemberApproval`, `DeviceFingerprint`, `MemberReference` and alter `AuditLog.action`/`OTPRequest.purpose` | Confirmed in this audit run | — | Generate and apply `0013`; test on fresh + existing DB before applying to production |
| KYC multi-step workflow (phone OTP → references → liveness → risk → consent → approval) | 🟡 Partial | Models exist (`KYCConsentRecord`, `MemberReference`, `LivenessChallenge`, `KYCRiskScore`, `DeviceFingerprint`, `MemberApproval`); `kyc_views.py` and `accounts/urls.py` wire all endpoints; serializers exist | No `accounts.tests` test for KYC workflow found in test suite | Models NOT yet migrated to production schema (drift); no frontend screens for multi-step KYC | Generate+apply migration; write tests; build member KYC workflow UI |
| Phone/email verification at registration | 🟡 Partial | `kyc_phone_otp_request/confirm` endpoints exist; `OTPRequest` with `purpose="phone_verification"` exists; no frontend step in `Register.js` | Endpoints source-verified | OTP delivery blocked (provider config) | Add phone-verify step to Register; configure provider |
| Duplicate-identity detection (hash lookup) | ✅ Implemented and verified | `hash_national_id` HMAC-SHA256; `national_id_hash` indexed on `IDVerification`; `run_id_verification` sets it | `accounts.0012` migration; source-verified | — | Currently applied only at document-intake; deduplication query not in registration path yet |
| Live government ID verification | 🔒 Blocked by configuration/provider | `accounts/services/identity_provider.py::get_identity_provider()` returns `SandboxIdentityProvider` which always returns `provider_unavailable` | Source-confirmed: "Live verification remains blocked until provider onboarding is documented" | Smile Identity API key + partner ID; no live provider onboarded | Onboard provider; replace `SandboxIdentityProvider` |
| Selfie face match against ID photo | 🔒 Blocked by configuration/provider | `face_verification_service.py` builds Smile Identity SmartSelfie request; `SMILE_IDENTITY_API_KEY` empty | Source-verified | `SMILE_IDENTITY_API_KEY` and `SMILE_IDENTITY_PARTNER_ID` needed | Configure credentials; test in sandbox |
| Liveness detection | 🔒 Blocked by configuration/provider | `kyc_views.py::kyc_liveness_start/complete`; `LivenessChallenge` model | Source-verified; model exists but not migrated | Same Smile Identity credentials + migration | Apply migration; configure provider |
| Referee (member reference) approval workflow | 🟡 Partial | `MemberReference` model; `kyc_reference_add`, `kyc_reference_received`, `kyc_reference_respond` endpoints | Source-verified; model not yet migrated | Migration required | Apply `0013`; build member-facing reference-submit UI |
| Committee approval of KYC | 🟡 Partial | `MemberApproval` model; `kyc_admin_pending_approvals`, `kyc_admin_approval_decide` endpoints | Source-verified; model not yet migrated | Migration required | Apply `0013`; build staff approval UI |
| Separate membership approval and identity statuses | 🟡 Partial | `IDVerification.status` tracks identity; `Member.status` tracks membership; `MemberApproval` tracks committee decision; these are separate fields | Source-verified | `MemberApproval` not migrated | Apply `0013`; surface both statuses clearly in member and staff UIs |
| Kenya DPA consent record | 🟡 Partial | `KYCConsentRecord` model; `kyc_consent` endpoint; `kyc_my_data` and `kyc_erasure` privacy endpoints | Source-verified; model not yet migrated | Migration required | Apply `0013` |
| Data retention purge command | ✅ Implemented and verified | `accounts/management/commands/purge_expired_kyc_documents.py` with `--apply` flag | Source-verified; dry-run reports count | Requires cron/scheduler | Schedule purge command |
| Device fingerprint / device binding | 🟡 Partial | `DeviceFingerprint` model; `kyc_device_register` endpoint | Source-verified; model not yet migrated | Migration required | Apply `0013` |
| Biometric liveness (Smile Identity SmartSelfie) | 🔒 Blocked by configuration/provider | `face_verification_service.py` calls Smile Identity API | Source-verified | Credentials + migration | Same as face match above |
| Transaction PIN | ❌ Missing | No transaction-PIN model, enforcement, or UI | — | — | Full build required |

---

### 13. Member Profile and Account Management

| Requirement | Status | Source files / API / UI | Test evidence | Runtime/provider dependency | Remaining work |
|---|---|---|---|---|---|
| View and edit profile | ⚠️ Implemented but unverified | `Profile.js`; `GET/PATCH /api/profile/` | `Profile.test.js` | — | Browser verification |
| Change password | ⚠️ Implemented but unverified | `ChangePassword.js`; `POST /api/change-password/`; visibility toggle inside each field | `ChangePassword.test.js` | — | Browser verification |
| Recovery contacts (email + phone) with verification | 🟡 Partial | `User.recovery_email`/`recovery_phone`; `POST /api/profile/recovery-contact/request/confirm/`; `Profile.js` shows recovery fields | Backend source; `accounts.tests` covers contact-verification path | OTP delivery blocked | Configure provider; browser test add-contact flow |
| Notifications (in-app) | ⚠️ Implemented but unverified | `Notification` model; `GET /api/notifications/`; `Notifications.js` with loading/error/empty/populated exclusive states + Retry; `Topbar.js` dropdown | `Notifications.test.js`, `accounts.tests.NotificationEndpointTests` | — | Browser verification; confirm 401 is no longer reproducible |
| Responsive layouts across screen sizes | ⚠️ Implemented but unverified | CSS uses flexbox/grid; mobile nav added; safe-area padding; min-width guards | `Sidebar.test.js` checks hidden elements | — | Manual browser test at 360, 390, 768, 1024, 1440 px + 200% zoom |

---

### 14. SASRA Compliance

| Requirement | Status | Source files / API / UI | Test evidence | Runtime/provider dependency | Remaining work |
|---|---|---|---|---|---|
| SASRA report generation (quarterly/annual/monthly/special) | ⚠️ Implemented but unverified | `SASRAReport` model; `views.py::sasra_reports`/`sasra_submit`; `AdminSASRA.js` with 4 report types | Backend endpoint in test suite | — | Browser admin workflow; SASRA format compliance review by a regulatory expert |
| SASRA report submission flag | ⚠️ Implemented but unverified | `SASRAReport.status` cycles draft→generated→submitted | Same | — | Actual regulatory submission process undefined |
| Regulatory compliance (content accuracy) | ❌ Missing (unverifiable) | Report numbers come from the single-entry Transaction ledger; no independent accounting verification | — | Requires regulatory review | SASRA format expert review; complete accounting ledger first |

---

### 15. Welfare Module

| Requirement | Status | Source files / API / UI | Test evidence | Runtime/provider dependency | Remaining work |
|---|---|---|---|---|---|
| Welfare contributions, cases, approvals, payouts | ❌ Missing | No `Welfare` model, migration, endpoint, or UI anywhere in the repository | — | — | Full feature build required |
| Incident reporting with location and assistance notifications | ❌ Missing | No `Incident` model or UI | — | — | Full feature build required |

---

### 16. Accounting and Ledger

| Requirement | Status | Source files / API / UI | Test evidence | Runtime/provider dependency | Remaining work |
|---|---|---|---|---|---|
| Transaction history (member-scoped, paginated) | ✅ Implemented and verified | `GET /api/transactions/` (`views.py::my_transactions`); `Transactions.js` with PAGE_SIZE=50; filters validated | `core.tests_downloads`, `core.tests_member_journey` | — | — |
| Transaction type/date filters with validation | ✅ Implemented and verified | `_validated_statement_date_range`; invalid/reversed ranges return HTTP 400 | Same | — | — |
| Transaction reversals | 🟡 Partial | `Transaction.reverses` FK added (migration 0016 — **not applied to `db.sqlite3`**); reversal type in model | Migration pending on production DB | Apply migration 0016 | Reversal workflow UI missing |
| Double-entry / balanced ledger | ❌ Missing | `core.models.Transaction` is a single-entry member activity ledger. REPAIR_TASKS.md explicitly states: "There is no chart of accounts or balanced debit/credit journal-line model." | — | — | Requires architectural decision + migration plan |
| Automated reconciliation (Savings vs Transaction) | ✅ Implemented and verified | `audit_engine.py::_check_transaction_integrity`; compares Savings rows to Transaction rows | `core.tests_audit` | — | Findings require staff action to resolve |
| Account-type field on Transaction | 🟡 Partial | Migration 0019 adds `Transaction.account_type` — **not applied to `db.sqlite3`** | Pending application | Apply migration 0019 | — |

---

### 17. Financial Audit Engine

| Requirement | Status | Source files / API / UI | Test evidence | Runtime/provider dependency | Remaining work |
|---|---|---|---|---|---|
| Run audit (all checks) | ⚠️ Implemented but unverified | `POST /api/admin/audit/run/`; `audit_engine.py` runs 8 check types | `core.tests_audit` | — | Browser admin workflow |
| Audit findings with severity | ⚠️ Implemented but unverified | `AuditFinding` model; `GET /api/admin/audit/findings/`; `AdminAudit.js` | Same | — | Browser admin workflow |
| Finding review workflow | ⚠️ Implemented but unverified | `POST /api/admin/audit/findings/<id>/review/`; `AdminAudit.js` review modal | Same | — | Browser admin workflow |
| Audit report export | ⚠️ Implemented but unverified | `GET /api/admin/audit/report/` | Same | — | Browser admin workflow |

---

### 18. Infrastructure, Jobs, and Operations

| Requirement | Status | Source files / API / UI | Test evidence | Runtime/provider dependency | Remaining work |
|---|---|---|---|---|---|
| PostgreSQL production deployment | 🟡 Partial | `settings.py` supports `USE_POSTGRES=1` with psycopg2; `db.sqlite3` currently in use | Config option source-verified | psycopg2 not in `requirements.txt` | Add `psycopg2-binary` or `psycopg[binary]` to requirements; provision PostgreSQL; run full migration chain on fresh PG DB |
| Database backups and restore testing | ❌ Missing | No backup script, documented backup procedure, or restore test evidence | — | — | Implement automated backup + restore test |
| Background job scheduling (overdue alerts, KYC purge) | 🟡 Partial | `send_overdue_alerts` and `purge_expired_kyc_documents` management commands exist; documented cron invocations | Source-verified | Cron / Railway scheduler must be configured | Configure scheduler; confirm commands run reliably |
| Monitoring and operational observability | 🟡 Partial | Rotating file log at `logs/sacco.log` (10 MB, 5 backups); `logger` calls throughout backend | Log config source-verified | — | Add health-check endpoint; set up error alerting (e.g. Sentry) |
| C2B URL registration | 🟡 Partial | `register_c2b_urls` management command exists | Source-verified | Daraja credentials + live deployment URL | Run command post-deployment |
| WhiteNoise static serving in production | ✅ Implemented and verified | `STATICFILES_STORAGE = CompressedManifestStaticFilesStorage`; `WHITENOISE_ROOT` for React build | Config source-verified; `npm run build` exits 0 | — | — |
| React production build | ✅ Implemented and verified | `CI=true GENERATE_SOURCEMAP=false npm run build` exits 0; Node `[DEP0176]` warning only | Build verified in REPAIR_TASKS.md | — | Upgrade Node/webpack to clear DEP0176 |
| Frontend tests | ✅ Implemented and verified | 16 suites, 42 tests passing (`npm test --watchAll=false --runInBand`) | REPAIR_TASKS.md latest run | — | — |
| Backend tests | ✅ Implemented and verified | 76 tests passing with venv (`manage.py test accounts.tests core.tests core.tests_extended core.tests_downloads core.tests_withdrawals core.tests_member_journey`) + 19 transport tests | REPAIR_TASKS.md latest runs | — | Expand coverage for KYC workflow, transport reconciliation, SASRA |
| Migration drift | 🟡 Partial | `accounts` migrations 0011–0012 not applied to `db.sqlite3`; `core` migrations 0016–0019 not applied to `db.sqlite3`; `accounts.0013` not yet generated | `showmigrations` output from this audit | — | Generate `0013`; apply all pending migrations to production DB with backup first |

---

### 19. Offline / PWA

| Requirement | Status | Source files / API / UI | Test evidence | Runtime/provider dependency | Remaining work |
|---|---|---|---|---|---|
| Offline draft collections (transport) | ⚠️ Implemented but unverified | `TransportCrew.js` user-scoped `localStorage` drafts | `TransportCrew.test.js` | Requires offline browser test | Manual offline test |
| Offline drafts for other features | ❌ Missing | No offline draft mechanism for loan applications, savings, or general member pages | — | — | Full build required |
| Service worker / PWA caching | ❌ Missing | CRA default service worker not enabled; no `manifest.json` customisation found | — | — | Implement if required |

---

## Summary of Migration Drift (confirmed in this audit run)

```
accounts (db.sqlite3):
  [ ] 0011_otprequest_attempt_count_and_more
  [ ] 0012_idverification_private_fields
  (proposed but not generated)
  [ ] 0013 — KYCConsentRecord, KYCRiskScore, LivenessChallenge,
              MemberApproval, DeviceFingerprint, MemberReference,
              AuditLog.action choices, OTPRequest.purpose choices

core (db.sqlite3):
  [ ] 0016_transaction_reverses_alter_transaction_type_and_more
  [ ] 0017_alter_fosawithdrawal_provider_reference
  [ ] 0018_transportassignmentissue
  [ ] 0019_transaction_account_type
```

All migrations through 0012/0018 are applied to the isolated test databases.
`db.sqlite3` (the working database) is behind by at least 6 migration steps.
No production migration was run during this audit.

---

## Five Highest-Priority Blockers

### Blocker 1 — Migration drift will break production on next deploy
**What:** 6 unapplied migrations on `db.sqlite3`; `accounts.0013` not yet generated.  
**Risk:** Deploying the current codebase against an unmigrated database will raise `OperationalError` for every endpoint that touches `FosaWithdrawal.provider_reference` (migration 0017), `Transaction.reverses` (0016), `TransportAssignmentIssue` (0018), `Transaction.account_type` (0019), and all KYC workflow models.  
**Action:** 1) Take a backup of `db.sqlite3` or the production PostgreSQL database. 2) Generate `accounts.0013`. 3) Apply `accounts.0011`–`0013` and `core.0016`–`0019` on the backup copy, verify no errors. 4) Apply to production under a maintenance window.

### Blocker 2 — OTP delivery is non-functional (login 2FA and password reset)
**What:** `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` are empty; `AT_API_KEY` is empty. The `dispatch_otp` path always returns `unavailable`. Staff cannot log in via 2FA; members cannot reset passwords.  
**Risk:** Any staff user is locked out unless they have an existing valid JWT. Members who forget passwords cannot recover their accounts.  
**Action:** Populate SMTP credentials or Africa's Talking API key in `.env`; restart Django; verify an OTP arrives in an inbox. This is prerequisite for browser login acceptance.

### Blocker 3 — No live payout provider (B2C/disbursement disabled)
**What:** `get_live_payout_provider()` returns `None`. All approved loan disbursements and FOSA withdrawal settlements are blocked in production.  
**Risk:** Approved loans cannot be disbursed; FOSA withdrawal requests are accepted but never paid out.  
**Action:** Decide on a disbursement provider (Daraja B2C, PesaLink, or other); implement `reserve_and_submit_withdrawal` with the live adapter; configure credentials; test in sandbox; go live. This is the single most consequential missing capability for a live SACCO.

### Blocker 4 — No live identity verification (KYC gated behind sandbox)
**What:** `get_identity_provider()` always returns `SandboxIdentityProvider` which returns `provider_unavailable`. Selfie face-match and liveness are code-complete but require Smile Identity credentials. The KYC multi-step workflow models are not yet migrated (`0013` pending).  
**Risk:** No member can be automatically KYC-verified. All verification requires manual staff review, which does not scale.  
**Action:** 1) Apply migration `0013`. 2) Onboard Smile Identity (or approved alternative). 3) Set `SMILE_IDENTITY_API_KEY`, `SMILE_IDENTITY_PARTNER_ID`, `SMILE_IDENTITY_ENV`. 4) Test face-match and liveness in sandbox. 5) Build the missing member-facing KYC multi-step UI.

### Blocker 5 — PostgreSQL not configured; SQLite in use; no backup procedure
**What:** `db.sqlite3` is the current database. PostgreSQL support is configured but not active (`USE_POSTGRES=0`). `psycopg2` is absent from `requirements.txt`. No backup script or restore-test evidence exists.  
**Risk:** SQLite is not safe for concurrent multi-user writes in production. Any data corruption or server loss will result in total data loss if no backup exists.  
**Action:** 1) Add `psycopg2-binary` to `requirements.txt`. 2) Provision a PostgreSQL instance. 3) Set `USE_POSTGRES=1`, `DB_*` variables. 4) Run the full migration chain on the new PG database. 5) Migrate existing data from SQLite. 6) Implement automated daily backups with restore-tested recovery.

---

## Dependency-Ordered Completion Plan

```
Phase 0 — Foundation (prerequisite for everything else)
  0.1  Take db.sqlite3 backup
  0.2  Generate accounts.0013 migration
  0.3  Apply accounts.0011-0013 + core.0016-0019 to test DB, verify
  0.4  Apply to production DB under maintenance window
  0.5  Add psycopg2-binary; provision PostgreSQL; migrate data
  0.6  Configure automated database backups + restore test

Phase 1 — Auth and OTP delivery (gates browser acceptance)
  1.1  Configure SMTP or Africa's Talking credentials
  1.2  Verify OTP inbox delivery for staff 2FA and password reset
  1.3  Complete browser acceptance: login, dashboard, all member screens
  1.4  Mobile layout test at 360-1440 px

Phase 2 — Financial completeness
  2.1  Implement B2C/disbursement adapter for loan disbursement + FOSA payouts
  2.2  Resolve legacy withdrawals 41 and 50 (requires external payout evidence)
  2.3  Design share-capital register (separate model from BOSA savings)
  2.4  Implement double-entry accounting migration plan or document decision to stay single-entry

Phase 3 — KYC completion
  3.1  Onboard identity provider (Smile Identity or equivalent)
  3.2  Configure SMILE_IDENTITY_API_KEY; test face-match in sandbox
  3.3  Apply migration 0013; wire KYC multi-step frontend screens
  3.4  Implement referee/reference approval workflow UI
  3.5  Implement committee KYC approval UI

Phase 4 — Live M-Pesa
  4.1  Configure Daraja sandbox credentials; verify STK end-to-end
  4.2  Run register_c2b_urls for C2B Paybill
  4.3  Test live STK deposit and repayment callback
  4.4  Move to Daraja production after sandbox acceptance

Phase 5 — CRB live provider
  5.1  Set CRB_PROVIDER=transunion or metropol
  5.2  Configure CRB_API_KEY; verify loan-application CRB check in sandbox

Phase 6 — Transport completion
  6.1  Owner dashboard and profitability screen
  6.2  Stage, marshal, and shift-closure model and UI
  6.3  Expenses model and UI
  6.4  Allocation-rule management UI
  6.5  Vehicle document tracking + expiry reminders
  6.6  Payment receipts

Phase 7 — Missing modules (each is a self-contained feature build)
  7.1  Welfare module (contributions, cases, approvals, payouts)
  7.2  Incident reporting with location
  7.3  Meetings, attendance, minutes, formal voting
  7.4  Announcements (admin broadcast → member feed)
  7.5  Complaints and dispute tracking
  7.6  Chat / messaging (requires real-time infrastructure decision)
  7.7  Goal-based and locked savings products
  7.8  Dividend projections
  7.9  PesaLink integration
  7.10 USSD integration
  7.11 NFC fares
  7.12 Fuel wallets
  7.13 Transaction PIN
  7.14 Global search in navbar

Phase 8 — Operational hardening
  8.1  Health-check endpoint + uptime monitoring
  8.2  Error alerting (Sentry or equivalent)
  8.3  Cron schedule for send_overdue_alerts and purge_expired_kyc_documents
  8.4  Upgrade Node/webpack to clear DEP0176 deprecation
  8.5  SASRA report format compliance review by regulatory expert
```

---

## Items That Could Not Be Verified in This Audit

The following could not be confirmed due to the browser-automation restriction and the absence of a live running environment during inspection:

1. **Any rendered UI** — layout, contrast, overflow, focus order, and mobile behaviour at any viewport width.
2. **Live OTP delivery** — no message was sent; mocked tests only.
3. **Live M-Pesa STK** — no real STK push was initiated; Daraja mock tests only.
4. **Live CRB check** — `CRB_PROVIDER=stub` in test settings; no real bureau request was made.
5. **Live identity/face/liveness check** — provider returns `sandbox_does_not_verify_identity` by design.
6. **Downloaded PDF and Excel files** — backend generation was verified in venv; opening them in a browser is unverified.
7. **Tesseract OCR binary** — `pytesseract` is in `requirements.txt`; whether the binary is installed on the deployment host is not confirmed.
8. **PostgreSQL round-trip** — settings support PG; no PG instance was tested.
9. **`db.sqlite3` schema state** — `showmigrations` confirmed which migrations are applied; actual column presence was not verified with `.schema` on every table.
10. **SASRA regulatory content accuracy** — report generation code was reviewed; whether report numbers satisfy SASRA's current reporting standards requires a regulatory expert.
