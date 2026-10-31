# Requirements Document

## Introduction

This feature adds two automated compliance pipelines to the SACCO application.

The **registration pipeline** requires every member to upload a government-issued ID document and a selfie photo during registration. The system extracts identity data from the ID via OCR, cross-checks the name against the registration form, verifies the identity through Smile Identity's KYC API, and compares the selfie face against the ID document photo using Smile Identity's biometric verification. The combined result is stored on the `IDVerification` record and gates registration access.

The **loan application pipeline** runs a Credit Reference Bureau (CRB) check on every new loan application. The system detects active external loans and flags the application for officer review when credit risk is identified.

All status transitions produce `Notification` records and `AuditLog` entries. Admin endpoints expose review queues for both pipelines, and the React frontend gains upload components, status badges, and dedicated admin pages.

## Glossary

- **IDVerification**: The Django model in `accounts/models.py` that stores the result of identity verification for a member, including status, provider response, and uploaded documents.
- **Member**: A registered SACCO user with `is_member = True`.
- **Staff**: A SACCO user with `is_admin = True` or an associated `StaffProfile` record.
- **Smile Identity**: The third-party KYC and biometric verification provider integrated in `accounts/id_verification.py`.
- **SmartSelfie**: Smile Identity's biometric face match and liveness verification product.
- **OCR Pipeline**: The service that extracts text fields (name, ID number, date of birth) from an uploaded ID document image or PDF.
- **Name Matcher**: The service that fuzzy-matches the name extracted by OCR against the name entered on the registration form.
- **CRB**: Credit Reference Bureau — a third-party provider (TransUnion Kenya or Metropol) that returns a credit score and list of active loans for a national ID.
- **CRBCheck**: The Django model in `core/models.py` that stores the result of a CRB query for a specific loan application.
- **Loan**: The Django model in `core/models.py` representing a member loan application.
- **AuditLog**: The Django model in `accounts/models.py` that records actor, action, target, and details for compliance traceability.
- **Notification**: The Django model in `accounts/models.py` that delivers in-app messages to users.
- **Face Match Score**: A numeric value (0–100) returned by the Smile Identity SmartSelfie API indicating the confidence that two face images belong to the same person.
- **Liveness Check**: A SmartSelfie feature that detects whether the selfie was taken from a live person rather than a photo or screen.
- **MEDIA_ROOT / MEDIA_URL**: Django settings that define the filesystem path and URL prefix for user-uploaded files.

## Requirements

### Requirement 1: ID Document Upload at Registration

**User Story:** As a member, I want to upload a government-issued ID document during registration, so that the SACCO can verify my identity before granting full account access.

#### Acceptance Criteria

1. THE Registration Endpoint SHALL accept an `id_document` file field alongside standard registration fields via `multipart/form-data`.
2. WHEN an `id_document` file is submitted, THE Registration Endpoint SHALL validate that the file MIME type is one of `image/jpeg`, `image/png`, `image/gif`, or `application/pdf`.
3. WHEN an `id_document` file exceeds the size limit defined by the `ID_DOC_MAX_MB` setting (default 5 MB), THE Registration Endpoint SHALL reject the file and return a 400 error with a descriptive message.
4. IF the submitted `id_document` file has an unsupported MIME type, THEN THE Registration Endpoint SHALL reject the file and return a 400 error identifying the unsupported type.
5. WHEN a valid `id_document` file is submitted, THE IDVerification record SHALL store the file at the `id_document` FileField using the `id_documents/` upload path.
6. WHERE `id_document` upload is not provided, THE Registration Endpoint SHALL proceed with registration and set `IDVerification.status` to `"pending"` for manual staff review.

---

### Requirement 2: OCR Extraction from ID Document

**User Story:** As the system, I want to extract identity fields from the uploaded ID document automatically, so that the name on the document can be compared against the registration form without manual data entry.

#### Acceptance Criteria

1. WHEN a valid `id_document` file is saved, THE OCR Pipeline SHALL extract raw text from the document using `pytesseract` for image files and `pdfplumber` for PDF files.
2. WHEN raw text is extracted, THE OCR Pipeline SHALL parse the text to identify the following fields: `id_number` (7–8 numeric digits for Kenyan National ID), `full_name`, and `dob` (date of birth).
3. THE OCR Pipeline SHALL store the result as `{"raw_text": str, "fields": {"id_number": str|null, "full_name": str|null, "dob": str|null}}` in `IDVerification.ocr_result`.
4. IF the OCR extraction raises an exception, THEN THE OCR Pipeline SHALL store an empty `fields` dict and log the error, and the registration flow SHALL continue using the `"pending"` status path.

---

### Requirement 3: Name and ID Cross-Check at Registration

**User Story:** As the SACCO, I want the name on the uploaded ID document to be compared against the name entered on the registration form, so that mismatches can be flagged for staff review.

#### Acceptance Criteria

1. WHEN `IDVerification.ocr_result` contains a non-empty `full_name` field, THE Name Matcher SHALL compare it against the `first_name` and `last_name` fields submitted on the registration form using fuzzy token-set-ratio matching.
2. WHEN the fuzzy match score is below the threshold defined by the `NAME_MATCH_THRESHOLD` setting (default 75), THE Name Matcher SHALL return a mismatch result and THE ID Verification Service SHALL set `IDVerification.status` to `"flagged"`.
3. WHEN the fuzzy match score meets or exceeds the `NAME_MATCH_THRESHOLD`, THE Name Matcher SHALL return a match result and the verification flow SHALL continue to the Smile Identity API check.
4. IF the OCR `full_name` field is empty or null, THEN THE ID Verification Service SHALL skip the name comparison step and continue to the Smile Identity API check.

---

### Requirement 4: Registration Gating on Verification Outcome

**User Story:** As the SACCO, I want registration to be allowed or blocked based on the combined ID verification result, so that members with definitively invalid IDs cannot complete registration.

#### Acceptance Criteria

1. WHEN Smile Identity returns a definitive failure (`success = False`), THE ID Verification Service SHALL set `IDVerification.status` to `"failed"` and THE Registration Endpoint SHALL return a 400 response with the rejection reason.
2. WHEN Smile Identity returns a definitive success (`success = True`) and all prior checks pass, THE ID Verification Service SHALL set `IDVerification.status` to `"verified"` and THE Registration Endpoint SHALL complete registration.
3. WHEN Smile Identity is not configured or returns a transient error (`success = None`), THE ID Verification Service SHALL set `IDVerification.status` to `"pending"` and THE Registration Endpoint SHALL complete registration.
4. WHEN the name cross-check returns a mismatch, THE ID Verification Service SHALL set `IDVerification.status` to `"flagged"` and THE Registration Endpoint SHALL complete registration (the member is not blocked but is queued for staff review).
5. THE Registration Endpoint SHALL include an `id_status` field in the response payload reflecting the final `IDVerification.status` value.

---

### Requirement 5: CRB Check on Loan Application

**User Story:** As the SACCO, I want a CRB check to run automatically on every new loan application, so that members with adverse credit history are identified before the loan is processed.

#### Acceptance Criteria

1. WHEN a new `Loan` record is created, THE CRB Service SHALL invoke the configured CRB provider (`CRB_PROVIDER` env var, choices: `transunion` | `metropol` | `stub`) with the member's `national_id`.
2. THE CRB Service SHALL create a `CRBCheck` record linked to the loan, storing provider name, status, score, active loans count, and raw response.
3. WHEN the CRB provider is not configured or returns a transient network error, THE CRB Service SHALL set `CRBCheck.status` to `"error"` and leave `Loan.status` unchanged.
4. THE Loan Application Endpoint SHALL include a `crb_status` field in the response payload reflecting the `CRBCheck.status` value.

---

### Requirement 6: Multi-Bank Active Loan Detection

**User Story:** As the SACCO, I want loan applications to be automatically flagged when a member has active loans at other financial institutions, so that over-indebtedness risk is surfaced for officer review.

#### Acceptance Criteria

1. WHEN the CRB response contains one or more active external loans, THE CRB Service SHALL set `Loan.status` to `"flagged"` and `CRBCheck.status` to `"flagged"`.
2. WHEN the CRB score is below the threshold defined by the `CRB_FLAG_SCORE_THRESHOLD` setting (default 500), THE CRB Service SHALL set `Loan.status` to `"flagged"` and `CRBCheck.status` to `"flagged"`.
3. WHEN a loan is flagged by the CRB Service, THE CRB Service SHALL send a `Notification` to the member and to staff.
4. WHEN a loan is flagged by the CRB Service, THE Loan Application Endpoint SHALL include a human-readable `flag_reason` in the response payload.

---

### Requirement 7: Flagged Loan Application — Staff Review Workflow

**User Story:** As a loan officer, I want to review and override flagged loan applications, so that members with legitimate circumstances are not permanently blocked by automated checks.

#### Acceptance Criteria

1. THE Admin CRB Endpoint SHALL provide `GET /api/core/admin/crb-checks/` listing all `CRBCheck` records, filterable by status and loan.
2. THE Admin CRB Endpoint SHALL provide `GET /api/core/admin/crb-checks/<id>/` returning full detail including `raw_response`.
3. WHEN staff submits `POST /api/core/admin/crb-checks/<id>/override/` with override notes, THE Admin CRB Endpoint SHALL set `Loan.status` to `"approved"`, populate `CRBCheck.override_by`, `CRBCheck.override_at`, and `CRBCheck.override_notes`, send a `Notification` to the member, and create an `AuditLog` entry with action `"crb_override"`.
4. THE Admin CRB Endpoint SHALL require `IsAdmin` permission for all operations; a 403 response SHALL be returned for non-admin callers.
5. THE Admin ID Verification Endpoint SHALL provide `GET /api/accounts/admin/id-verifications/` listing all `IDVerification` records with status filter.
6. WHEN staff submits `POST /api/accounts/admin/id-verifications/<id>/review/` with a new status and notes, THE Admin ID Verification Endpoint SHALL update `IDVerification.status`, send a `Notification` to the member, and create an `AuditLog` entry with action `"id_verify_review"`.

---

### Requirement 8: Audit and Transparency

**User Story:** As the SACCO compliance officer, I want every identity and credit verification action to be recorded in the audit log, so that all regulatory decisions have a traceable history.

#### Acceptance Criteria

1. WHEN an ID verification is initiated at registration, THE ID Verification Service SHALL create an `AuditLog` entry with action `"id_verify_submit"`.
2. WHEN a CRB check completes (any outcome), THE CRB Service SHALL create an `AuditLog` entry with action `"crb_check_run"`.
3. WHEN a loan is flagged by the CRB Service, THE CRB Service SHALL create an `AuditLog` entry with action `"loan_flagged"`.
4. THE `AuditLog` entries for verification events SHALL include `details` containing the `IDVerification.id` or `CRBCheck.id`, the resulting status, and the provider name.
5. THE `AuditLog.ACTION_CHOICES` SHALL include `"id_verify_submit"`, `"id_verify_review"`, `"crb_check_run"`, `"crb_override"`, and `"loan_flagged"`.

---

### Requirement 9: Face Verification at Registration

**User Story:** As the SACCO, I want the member to submit a selfie at registration that is compared against the face on the uploaded ID document, so that the person registering is confirmed to be the same person named on the ID.

#### Acceptance Criteria

1. THE Registration Endpoint SHALL accept a `selfie` file field alongside the `id_document` and standard registration fields via `multipart/form-data`.
2. WHEN a `selfie` file is submitted, THE Registration Endpoint SHALL validate that the file MIME type is one of `image/jpeg`, `image/png`, or `image/gif`.
3. WHEN a valid `selfie` file is submitted, THE ID Verification Service SHALL store the selfie at the `selfie` FileField on `IDVerification` using a secure upload path (e.g. `selfies/`).
4. WHEN both a `selfie` and an `id_document` are present on the `IDVerification` record, THE ID Verification Service SHALL call the Smile Identity SmartSelfie biometric API to compare the selfie face against the ID document photo.
5. WHEN the Smile Identity SmartSelfie API returns a face match score below the configured `FACE_MATCH_THRESHOLD` setting (default 70), THE ID Verification Service SHALL set `IDVerification.status` to `"flagged"` for staff review.
6. WHEN the Smile Identity SmartSelfie API returns a face match score at or above `FACE_MATCH_THRESHOLD` and all prior checks pass, THE ID Verification Service SHALL allow the verification flow to proceed to the final status determination.
7. WHEN the Smile Identity SmartSelfie API reports a liveness check failure, THE ID Verification Service SHALL set `IDVerification.status` to `"flagged"` regardless of the face match score.
8. WHEN the Smile Identity SmartSelfie API is not configured or returns a transient error, THE ID Verification Service SHALL set `IDVerification.status` to `"pending"` (same graceful fallback as the name-check API path) and SHALL NOT block registration.
9. THE ID Verification Service SHALL store the full Smile Identity SmartSelfie API response, including the face match score, in `IDVerification.provider_response`.
10. WHEN a face verification result is produced (any outcome), THE ID Verification Service SHALL create an `AuditLog` entry with action `"face_verify"` and details containing the `IDVerification.id`, the outcome (matched / flagged / pending), and the face match score if available.
11. THE `selfie` file stored on `IDVerification` SHALL be accessible only to the owning member and to staff with `IsAdmin` permission; unauthenticated or non-owner, non-admin requests SHALL receive a 403 response.
12. THE `id_document` file stored on `IDVerification` SHALL be accessible only to the owning member and to staff with `IsAdmin` permission; unauthenticated or non-owner, non-admin requests SHALL receive a 403 response.
13. WHERE a `selfie` is not provided at registration, THE ID Verification Service SHALL skip the face verification step and set `IDVerification.status` to `"pending"` for staff review.
14. THE Admin ID Verification Endpoint detail view SHALL return the `selfie` file URL alongside the `id_document` URL so that staff can compare both images during the review workflow.
15. THE `AuditLog.ACTION_CHOICES` SHALL include `"face_verify"` in addition to the entries defined in Requirement 8.
