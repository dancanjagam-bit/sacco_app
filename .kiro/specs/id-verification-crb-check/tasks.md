# Implementation Plan: Member Identity Verification & CRB Check

## Overview

This feature adds two automated pipelines to the SACCO app:

1. **Registration pipeline** — members upload a government ID document and a selfie photo during registration. The backend runs OCR to extract name, ID number, and date of birth; cross-checks the name against the registration form; calls the Smile Identity KYC API; and calls the Smile Identity SmartSelfie biometric API to confirm the selfie face matches the ID document photo. All results are stored on the extended `IDVerification` model and gate registration access.
2. **Loan application pipeline** — on every new loan application the system calls a CRB provider (TransUnion Kenya or Metropol, swapped via `CRB_PROVIDER` env var), detects active external loans, and flags the application for officer review if credit risk is found.

All status changes produce `Notification` records and `AuditLog` entries. New admin endpoints expose review queues for both pipelines. The React frontend gains upload and webcam capture components, status badges, and two new admin pages.

---

## Tasks

- [x] 1. Extend data models and run migrations
  - [x] 1.1 Add `id_document` FileField and `ocr_result` JSONField to `IDVerification` in `accounts/models.py`
    - `id_document = models.FileField(upload_to="id_documents/", null=True, blank=True)`
    - `ocr_result = models.JSONField(default=dict, blank=True)` — stores raw extracted text and parsed fields
    - _Requirements: 7 (Extend IDVerification model)_

  - [x] 1.2 Add `selfie` FileField and `face_match_score` FloatField to `IDVerification` in `accounts/models.py`
    - `selfie = models.FileField(upload_to="selfies/", null=True, blank=True)`
    - `face_match_score = models.FloatField(null=True, blank=True)`
    - _Requirements: 9 (Face verification model fields)_

  - [x] 1.3 Add `"flagged"` to `Loan.STATUS_CHOICES` in `core/models.py`
    - Insert `("flagged", "Flagged for CRB Review")` into the STATUS_CHOICES list
    - _Requirements: 9 (Add flagged to Loan.STATUS_CHOICES)_

  - [x] 1.4 Create `CRBCheck` model in `core/models.py`
    - Fields: `loan` (FK → Loan), `member` (FK → User), `provider` (CharField, choices: transunion/metropol/stub), `status` (choices: pending/clear/flagged/error), `score` (IntegerField, null/blank), `active_loans_count` (IntegerField, default 0), `raw_response` (JSONField), `checked_at` (DateTimeField, auto_now_add), `override_by` (FK → User, null/blank), `override_at` (DateTimeField, null/blank), `override_notes` (TextField, blank)
    - _Requirements: 8 (New CRBCheck model)_

  - [x] 1.5 Add new `AuditLog.ACTION_CHOICES` entries in `accounts/models.py`
    - Add: `("id_verify_submit", "ID Verification Submitted")`, `("id_verify_review", "ID Verification Reviewed")`, `("crb_check_run", "CRB Check Run")`, `("crb_override", "CRB Flagged Loan Override")`, `("loan_flagged", "Loan Flagged by CRB")`, `("face_verify", "Face Verification Run")`
    - _Requirements: 9 (face_verify AuditLog action), 15 (AuditLog entries for all status changes)_

  - [x] 1.6 Generate and apply Django migrations
    - Run `python manage.py makemigrations accounts core` to generate migration files
    - Migration files must be committed (they are not auto-generated at runtime)
    - _Requirements: 16 (Django migrations)_

- [x] 2. Build backend services — file validation and OCR pipeline
  - [x] 2.1 Create `accounts/services/__init__.py` (empty) and `accounts/services/file_validator.py`
    - Implement `validate_id_document(file) -> None` — raises `ValidationError` on bad MIME or size
    - Implement `validate_selfie(file) -> None` — accepts JPEG/PNG/GIF only (no PDF); raises `ValidationError` on bad MIME or size
    - Allowed MIME types for ID doc: `image/jpeg`, `image/png`, `image/gif`, `application/pdf`
    - Allowed MIME types for selfie: `image/jpeg`, `image/png`, `image/gif`
    - Max size: 5 MB (configurable via `ID_DOC_MAX_MB` setting, default 5)
    - Use `python-magic` (or `imghdr` + content-type header as fallback) for MIME detection
    - _Requirements: 1 (file_validator.py), 9 (selfie MIME validation)_

  - [ ]* 2.2 Write property tests for `file_validator` (Hypothesis)
    - **Property 1: Any file larger than max size is always rejected**
    - **Property 2: Any file with a disallowed MIME is always rejected regardless of size**
    - **Validates: Requirements 1**

  - [x] 2.3 Create `accounts/services/ocr_pipeline.py`
    - Implement `extract_text_from_image(file_path: str) -> str` using `pytesseract`
    - Implement `extract_text_from_pdf(file_path: str) -> str` using `pdfplumber`
    - Implement `run_ocr(file_path: str) -> dict` — dispatcher that detects file type and returns `{"raw_text": str, "fields": {"id_number": str|None, "full_name": str|None, "dob": str|None}}`
    - Use regex heuristics to parse Kenyan National ID number (7–8 digits), name, and DOB from raw text
    - _Requirements: 2 (ocr_pipeline.py)_

  - [ ]* 2.4 Write unit tests for `ocr_pipeline` field extraction
    - Test regex parsers against sample OCR output strings for ID number, name, DOB
    - Test dispatcher routing for `.jpg`, `.png`, `.pdf` file extensions
    - _Requirements: 2_

  - [x] 2.5 Create `accounts/services/name_matcher.py`
    - Implement `match_names(ocr_name: str, form_name: str) -> tuple[bool, float]`
    - Use `thefuzz.fuzz.token_set_ratio` for matching; configurable threshold via `NAME_MATCH_THRESHOLD` setting (default 75)
    - Return `(True, score)` when score ≥ threshold; `(False, score)` otherwise
    - Handle empty/None gracefully (return `(False, 0.0)`)
    - _Requirements: 3 (name_matcher.py)_

  - [ ]* 2.6 Write property tests for `name_matcher` (Hypothesis)
    - **Property 3: A name always matches itself (score = 100)**
    - **Property 4: Matching is commutative — match(a, b) == match(b, a)**
    - **Validates: Requirements 3**

- [x] 3. Build backend services — face verification and ID verification orchestrator
  - [x] 3.1 Create `accounts/services/face_verification_service.py`
    - Define `FaceVerificationResult` dataclass: `face_match_score: float | None`, `liveness_passed: bool`, `outcome: str` (`"matched"` | `"flagged"` | `"pending"`), `raw_response: dict`
    - Implement `verify(selfie_file, id_document_file) -> FaceVerificationResult`
    - Read `SMILE_IDENTITY_API_KEY` and `SMILE_IDENTITY_PARTNER_ID` from settings; if either absent → return `outcome="pending"`
    - POST base64-encoded selfie and id_document to Smile Identity SmartSelfie API (`sandbox` or `production` endpoint based on `SMILE_IDENTITY_ENV`)
    - Parse `Actions.Liveness_Check` and `Actions.Confidence_Value` from response
    - `liveness_passed = False` → `outcome = "flagged"`; `face_match_score < FACE_MATCH_THRESHOLD` → `outcome = "flagged"`; both pass → `outcome = "matched"`
    - On any network or parse exception → log error, return `outcome = "pending"`
    - _Requirements: 9 (FaceVerificationService)_

  - [ ]* 3.2 Write unit tests for `face_verification_service` — all 5 outcome paths
    - Test liveness failure → `outcome="flagged"`
    - Test score below threshold → `outcome="flagged"`
    - Test credentials not configured → `outcome="pending"`
    - Test transient network/parse error → `outcome="pending"`
    - Test all checks pass → `outcome="matched"`
    - _Requirements: 9_

  - [x] 3.3 Create `accounts/services/id_verification_service.py`
    - Implement `run_id_verification(user, national_id, first_name, last_name, id_document_file, selfie_file=None) -> dict`
    - Orchestration steps:
      - Step 1: `file_validator.validate_id_document` → 400 on invalid
      - Step 2: `file_validator.validate_selfie` → 400 on invalid (skip if no selfie)
      - Step 3: save files to `IDVerification.id_document` / `IDVerification.selfie`
      - Step 4: `ocr_pipeline.run_ocr` → store result in `IDVerification.ocr_result`
      - Step 5: `name_matcher.match_names(ocr_name, form_name)` → flag mismatch
      - Step 6: `call_smile_identity` from existing `accounts/id_verification.py`
      - Step 7: if selfie present, call `FaceVerificationService.verify(selfie_file, id_document_file)`; store `face_match_score`, merge SmartSelfie raw response into `IDVerification.provider_response`, create `AuditLog` entry with `action="face_verify"`, and set status per outcome (`flagged` / `pending` / continue to `verified`); if no selfie → set status `"pending"`
    - Returns `{"approved": bool, "status": str, "message": str, "ocr_result": dict}`
    - _Requirements: 4 (id_verification_service.py orchestrator), 9 (face verification integration)_

  - [ ]* 3.4 Write unit tests for `id_verification_service` with mocked dependencies
    - Test "file invalid → reject" path
    - Test "name mismatch → flagged" path
    - Test "Smile Identity verified, face matched → verified" path
    - Test "Smile Identity not configured → pending" path
    - Test "selfie absent → face check skipped, status pending" path
    - Test "face liveness fail → flagged" path
    - _Requirements: 4, 9_

- [x] 4. Build backend services — CRB pipeline
  - [x] 4.1 Create `core/services/__init__.py` (empty) and `core/services/crb_client.py`
    - Implement `TransUnionKenyaClient` class with `check(national_id: str) -> dict`
    - Implement `MetropolClient` class with `check(national_id: str) -> dict`
    - Both clients return `{"provider": str, "score": int|None, "active_loans": list[dict], "raw": dict, "error": str|None}`
    - Use `CRB_API_KEY`, `CRB_API_URL` settings (from env); return stub response when not configured
    - Swap clients via `CRB_PROVIDER` env var (`"transunion"` | `"metropol"` | `"stub"`)
    - _Requirements: 5 (crb_client.py)_

  - [ ]* 4.2 Write unit tests for `crb_client` with mocked HTTP
    - Test that `stub` provider returns deterministic response
    - Test that HTTP error is caught and returned as `{"error": "..."}`
    - _Requirements: 5_

  - [x] 4.3 Create `core/services/crb_service.py`
    - Implement `ActiveLoanExtractor.extract(raw_response: dict) -> list[dict]` — parses provider response to list active loans
    - Implement `CRBService.run_check(loan) -> CRBCheck` — selects client via env, calls `check()`, extracts active loans, creates and saves a `CRBCheck` record, sets `loan.status = "flagged"` if active loans found or score below threshold (`CRB_FLAG_SCORE_THRESHOLD`, default 500), sends `Notification` to member and staff, logs `AuditLog`
    - _Requirements: 6 (crb_service.py)_

  - [ ]* 4.4 Write unit tests for `CRBService.run_check`
    - Test "clear CRB → loan stays pending" path
    - Test "active external loans found → loan flagged" path
    - Test "score below threshold → loan flagged" path
    - _Requirements: 6_

- [x] 5. Extend registration serializer and integrate new ID verification service
  - [x] 5.1 Extend `RegistrationSerializer` in `accounts/serializers.py`
    - Add `id_document = serializers.FileField(required=False, allow_null=True)` — accepts JPEG/PNG/GIF/PDF; override `to_internal_value` if needed
    - Add `selfie = serializers.FileField(required=False, allow_null=True)` — JPEG/PNG/GIF only
    - Add `validate_id_document()` method calling `file_validator.validate_id_document()`
    - Add `validate_selfie()` method calling `file_validator.validate_selfie()` (raises `ValidationError` if PDF)
    - Update the registration view in `accounts/views.py` to call `id_verification_service.run_id_verification(...)` passing both `request.FILES.get("id_document")` and `request.FILES.get("selfie")`
    - Ensure the endpoint accepts `multipart/form-data`
    - _Requirements: 9 (selfie field in RegistrationSerializer), 10 (Extend RegistrationSerializer)_

  - [ ]* 5.2 Write integration test for the registration endpoint with file uploads
    - POST multipart form with a small PNG as `id_document` and a small JPEG as `selfie` alongside valid registration data
    - Assert `IDVerification.id_document`, `IDVerification.selfie`, and `ocr_result` key are populated on the created record
    - Assert a PDF `selfie` upload returns HTTP 400
    - _Requirements: 9, 10_

- [ ] 6. Integrate CRB check into loan application flow
  - [-] 6.1 Update the loan application view in `core/views.py`
    - After creating a new `Loan`, call `CRBService().run_check(loan)` inside the `transaction.atomic()` block (or immediately after, if CRB call should not roll back the loan record)
    - Return `crb_status` in the response payload so the frontend can inform the member
    - If `loan.status == "flagged"`, include a human-readable `flag_reason` in the response
    - _Requirements: 11 (Extend loan application view)_

  - [ ]* 6.2 Write unit test for flagged loan application response
    - Mock `CRBService.run_check` to set `loan.status = "flagged"`
    - Assert response contains `crb_status: "flagged"` and `flag_reason`
    - _Requirements: 11_

- [x] 7. New admin endpoints
  - [x] 7.1 Add ID verification admin endpoints in `accounts/views.py`
    - `GET /api/accounts/admin/id-verifications/` — list all `IDVerification` records with status filter
    - `GET /api/accounts/admin/id-verifications/<id>/` — retrieve single record including `ocr_result`, `id_document` URL, and `selfie` URL
    - `POST /api/accounts/admin/id-verifications/<id>/review/` — accept `{"status": "verified"|"failed"|"flagged", "notes": str}`, update record, send `Notification` to member, log `AuditLog` with action `"id_verify_review"`
    - All endpoints require `IsAdmin` permission
    - Register new URL patterns in `accounts/urls.py`
    - _Requirements: 12 (Admin endpoints — ID verification review)_

  - [x] 7.2 Add protected media view in `accounts/views.py`
    - Create `ProtectedMediaView(APIView)` with `permission_classes = [IsAuthenticated]`
    - `GET /api/media/protected/<path:path>/` — resolves `IDVerification` from the file path; returns 403 if requester is not the record owner or an admin; returns `FileResponse` for authorized requests
    - Register URL pattern in `accounts/urls.py`
    - _Requirements: 9 (protected media access for selfie and id_document)_

  - [x] 7.3 Add CRB check admin endpoints in `core/views.py`
    - `GET /api/core/admin/crb-checks/` — list all `CRBCheck` records with status/loan filters
    - `GET /api/core/admin/crb-checks/<id>/` — retrieve single record with `raw_response`
    - `POST /api/core/admin/crb-checks/<id>/override/` — accept `{"notes": str}`, set `loan.status = "approved"`, populate `CRBCheck.override_by/at/notes`, send `Notification`, log `AuditLog` with action `"crb_override"`
    - All endpoints require `IsAdmin` permission
    - Register new URL patterns in `core/urls.py`
    - _Requirements: 12 (Admin endpoints — CRB check review and flagged loan override)_

  - [ ]* 7.4 Write unit tests for admin review endpoints
    - Test 403 when called by a non-admin member
    - Test successful status transition with Notification and AuditLog side effects
    - Test `ProtectedMediaView` returns 403 for non-owner/non-admin and 200 for owner and admin
    - _Requirements: 9, 12_

- [~] 8. Checkpoint — backend integration
  - Ensure all backend tests pass (`python manage.py test accounts core`), ask the user if questions arise.

- [x] 9. React frontend — shared components
  - [x] 9.1 Create `frontend/src/components/IDDocumentUpload.js`
    - Renders a file input accepting `image/jpeg,image/png,image/gif,application/pdf`
    - Shows a preview thumbnail for images or a PDF icon for PDFs
    - Displays client-side size validation error (> 5 MB) before upload
    - On selection, calls the provided `onChange(file)` callback
    - Accessible: label linked to input, `aria-describedby` for error messages
    - _Requirements: 13 (IDDocumentUpload component)_

  - [x] 9.2 Create `frontend/src/components/SelfieCapture.js`
    - Webcam mode using `react-webcam` library; captures JPEG screenshot and converts the base64 data URL to a `File` object via `onChange(file)` callback
    - Upload fallback mode: `<input type="file" accept="image/jpeg,image/png,image/gif" />`
    - Automatically switches to upload mode if camera permission is denied
    - Accessible: `aria-label` on capture button and file input
    - _Requirements: 9 (SelfieCapture component)_

  - [x] 9.3 Create `frontend/src/components/VerificationStatusBadge.js`
    - Accepts `status` prop (`"pending"` | `"verified"` | `"failed"` | `"flagged"`)
    - Renders a colour-coded pill: pending=grey, verified=green, failed=red, flagged=amber
    - _Requirements: 13 (VerificationStatusBadge component)_

- [ ] 10. React frontend — member registration update
  - [-] 10.1 Update `frontend/src/pages/Register.js` to include ID document upload and selfie capture
    - Import `IDDocumentUpload` and add it to the registration form
    - Import `SelfieCapture` and place it alongside `IDDocumentUpload` in the form
    - Change form submission to use `multipart/form-data` (via `FormData`) instead of JSON; include both `id_document` and `selfie` files when present
    - Show `VerificationStatusBadge` with the `id_status` returned from the API after registration
    - _Requirements: 9 (selfie capture in registration), 13_

- [ ] 11. React frontend — admin pages
  - [ ] 11.1 Create `frontend/src/pages/AdminIDVerifications.js`
    - Fetch from `GET /api/accounts/admin/id-verifications/` with status filter tabs (All / Pending / Flagged / Verified / Failed)
    - Render a table: member name, member number, national ID, submitted date, status badge, actions
    - Detail panel: OCR result fields, ID document image/PDF preview, **selfie image preview** (served via `ProtectedMediaView`), face match score numeric badge (green ≥ 70, amber 50–69, red < 50 or null), Smile Identity response
    - Review action: inline form to set status + notes and call `POST .../review/`
    - _Requirements: 9 (selfie preview and face_match_score badge), 13 (AdminIDVerifications page)_

  - [~] 11.2 Create `frontend/src/pages/AdminCRBChecks.js`
    - Fetch from `GET /api/core/admin/crb-checks/` with status filter tabs (All / Clear / Flagged / Error)
    - Render a table: member name, loan amount, CRB provider, score, active loans count, checked date, status badge
    - Detail panel: raw CRB response, active loans list
    - Override action: inline notes form that calls `POST .../override/` to approve a flagged loan
    - _Requirements: 13 (AdminCRBChecks page)_

  - [~] 11.3 Add routes and sidebar links for new admin pages
    - In `frontend/src/App.js`, add `<AdminRoute path="/admin/id-verifications" component={AdminIDVerifications} />` and `<AdminRoute path="/admin/crb-checks" component={AdminCRBChecks} />`
    - In `frontend/src/components/Sidebar.js`, add navigation entries "ID Verifications" and "CRB Checks" under a "Compliance" group, visible only to admins
    - _Requirements: 13_

- [~] 12. Checkpoint — frontend integration
  - Ensure the frontend builds without errors (`npm run build` in `frontend/`), ask the user if questions arise.

- [x] 13. Add new env vars to `.env.example`
  - [x] 13.1 Append CRB, OCR, and face verification env var documentation to `.env.example`
    - Add `CRB_PROVIDER=stub` (choices: transunion, metropol, stub)
    - Add `CRB_API_KEY=your-crb-api-key`
    - Add `CRB_API_URL=https://api.crb-provider.co.ke`
    - Add `CRB_FLAG_SCORE_THRESHOLD=500`
    - Add `SMILE_IDENTITY_API_KEY=your-smile-identity-key`
    - Add `SMILE_IDENTITY_PARTNER_ID=your-partner-id`
    - Add `ID_DOC_MAX_MB=5`
    - Add `NAME_MATCH_THRESHOLD=75`
    - Add `FACE_MATCH_THRESHOLD=70`
    - Add `SMILE_IDENTITY_ENV=sandbox`
    - _Requirements: 9 (face verification env vars), 18 (.env.example additions)_

- [x] 14. Install `react-webcam` npm dependency
  - [x] 14.1 Add `react-webcam` to `frontend/package.json` and install
    - Run `npm install react-webcam@^7.2.0` in `frontend/`
    - Confirm `react-webcam` appears in `package.json` dependencies and `package-lock.json`
    - _Requirements: 9 (SelfieCapture webcam library)_

- [~] 15. Final checkpoint — full test suite
  - Ensure all backend tests pass and the frontend build succeeds, ask the user if questions arise.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP delivery
- The `accounts/services/` and `core/services/` directories must be created as Python packages (with `__init__.py`)
- The existing `accounts/id_verification.py` is preserved; `id_verification_service.py` calls `call_smile_identity()` from it rather than duplicating the logic
- CRB and SmartSelfie calls are network I/O — always wrap in `try/except` and fall back gracefully when the provider is unreachable; `FaceVerificationService.verify()` must never raise
- Selfie files (`selfies/`) and ID document files (`id_documents/`) must NOT be served via the default `MEDIA_URL` in production; access is routed through `ProtectedMediaView` only
- File uploads require `MEDIA_ROOT` / `MEDIA_URL` to be configured in `settings.py` — verify this before wiring the FileFields
- Property tests (Hypothesis) require `hypothesis` in `requirements.txt`; add it if missing
- `python-magic` requires `libmagic` system library; on Windows use `python-magic-bin`
- `react-webcam` captures a JPEG data URL; convert to a `File` object (e.g. `new File([blob], "selfie.jpg", { type: "image/jpeg" })`) before appending to `FormData`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4", "1.5"] },
    { "id": 1, "tasks": ["1.6"] },
    { "id": 2, "tasks": ["2.1", "2.3", "2.5", "4.1", "14.1"] },
    { "id": 3, "tasks": ["2.2", "2.4", "2.6", "4.2", "3.1"] },
    { "id": 4, "tasks": ["3.2", "3.3", "4.3", "9.1", "9.2", "9.3", "13.1"] },
    { "id": 5, "tasks": ["3.4", "4.4", "5.1", "7.1", "7.2", "7.3"] },
    { "id": 6, "tasks": ["5.2", "6.1", "7.4", "10.1", "11.1", "11.2"] },
    { "id": 7, "tasks": ["6.2", "11.3"] }
  ]
}
```
