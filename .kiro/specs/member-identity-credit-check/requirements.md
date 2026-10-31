# Requirements Document

## Introduction

This document specifies requirements for a member identity verification and credit check system within the SACCO application. The system enhances the existing registration and loan application flows by adding: (1) real-name verification through National ID document upload and OCR extraction cross-checked against the Smile Identity KYC API, and (2) Credit Reference Bureau (CRB) checks and multi-bank active loan detection at the time of loan application. When checks surface issues, the system flags the record for staff manual review rather than outright rejecting it, and notifies the affected member.

## Glossary

- **IDVerificationService**: The backend service responsible for coordinating ID document upload, OCR extraction, and Smile Identity API cross-checking during registration.
- **OCRPipeline**: The backend component that processes an uploaded ID document image and extracts text fields (full name, ID number, date of birth).
- **SmileIdentityAPI**: The third-party KYC REST API at usesmileid.com used to cross-verify extracted ID data against government records.
- **CRBService**: The backend service that queries a Credit Reference Bureau (TransUnion Kenya or Metropol) to determine whether a loan applicant has outstanding external debt or is blacklisted.
- **CRBCheck**: A persisted record of one CRB inquiry for a specific loan application, storing the raw bureau response and the derived decision.
- **LoanApplicationProcessor**: The backend component that orchestrates the loan application pipeline, including eligibility evaluation, CRB check invocation, and status assignment.
- **IDDocument**: The image file (JPEG, PNG, or PDF) of a member's government-issued National ID card uploaded during registration.
- **FlaggedRecord**: A loan application or ID verification record whose status has been set to `flagged` as a result of an automated check finding a potential issue, pending staff manual review.
- **StaffReviewer**: A SACCO staff member with the `loan_officer`, `accountant`, or `superadmin` role who reviews FlaggedRecords and resolves them.
- **Member**: A registered SACCO user with `is_member = True`.
- **Loan**: The `core.Loan` model instance representing a loan application by a Member.
- **RegistrationSerializer**: The existing DRF serializer in `accounts/serializers.py` that validates and processes new member registrations.

---

## Requirements

### Requirement 1: ID Document Upload at Registration

**User Story:** As a prospective member, I want to upload my National ID document during registration, so that the SACCO can verify my identity against an authoritative source.

#### Acceptance Criteria

1. WHEN a new member submits the registration form, THE RegistrationSerializer SHALL require an `id_document` field containing an uploaded image or PDF file of the National ID.
2. THE IDVerificationService SHALL accept ID documents in JPEG, PNG, and PDF formats only.
3. IF the uploaded file format is not JPEG, PNG, or PDF, THEN THE IDVerificationService SHALL reject the upload and return an error message identifying the unsupported format.
4. IF the uploaded file size exceeds 5 MB, THEN THE IDVerificationService SHALL reject the upload and return an error message stating the maximum allowed size.
5. THE IDVerificationService SHALL store the uploaded IDDocument securely in the configured media storage, accessible only to authenticated staff and the owning Member.

---

### Requirement 2: OCR Extraction from ID Document

**User Story:** As a SACCO administrator, I want the system to automatically extract identity data from an uploaded ID document, so that manual data entry errors are eliminated and verification is faster.

#### Acceptance Criteria

1. WHEN an IDDocument is successfully stored, THE OCRPipeline SHALL extract the full name, ID number, and date of birth from the document image.
2. IF the OCRPipeline cannot extract one or more required fields (full name, ID number, or date of birth) from the IDDocument, THEN THE IDVerificationService SHALL set the `IDVerification.status` to `flagged` and notify the Member that manual review is required.
3. THE OCRPipeline SHALL return extracted fields as structured data: `ocr_full_name` (string), `ocr_id_number` (string), and `ocr_dob` (date string in ISO 8601 format).
4. THE IDVerificationService SHALL persist the OCR-extracted fields in the `IDVerification.provider_response` JSON field alongside the raw OCR output.

---

### Requirement 3: Name and ID Cross-Check at Registration

**User Story:** As a SACCO administrator, I want the name a member provides during registration to match the name on their National ID, so that identity fraud is detected before membership is approved.

#### Acceptance Criteria

1. WHEN OCR extraction succeeds, THE IDVerificationService SHALL compare `ocr_full_name` against the `first_name` and `last_name` submitted in the registration form.
2. THE IDVerificationService SHALL perform name comparison using case-insensitive, whitespace-normalised matching.
3. IF the name comparison fails (similarity score below the configured threshold), THEN THE IDVerificationService SHALL set `IDVerification.status` to `flagged` and record the mismatch reason in `IDVerification.failure_reason`.
4. WHEN name comparison succeeds, THE IDVerificationService SHALL invoke the SmileIdentityAPI to cross-verify the `ocr_id_number`, `first_name`, and `last_name` against government records.
5. IF the SmileIdentityAPI returns a definitive rejection (result code not in `1012`/`1013`), THEN THE IDVerificationService SHALL set `IDVerification.status` to `failed` and record the API rejection reason in `IDVerification.failure_reason`.
6. IF the SmileIdentityAPI is not configured or returns a transient error, THEN THE IDVerificationService SHALL set `IDVerification.status` to `pending` and allow registration to proceed for manual staff review.
7. WHEN the SmileIdentityAPI confirms the identity, THE IDVerificationService SHALL set `IDVerification.status` to `verified` and record `IDVerification.verified_at` with the current timestamp.
8. THE IDVerificationService SHALL persist all SmileIdentityAPI response data in `IDVerification.provider_response`.

---

### Requirement 4: Registration Gating on Verification Outcome

**User Story:** As a SACCO administrator, I want failed identity verifications to be blocked from completing registration, so that fraudulent accounts are not created.

#### Acceptance Criteria

1. IF `IDVerification.status` is `failed` after all checks complete, THEN THE RegistrationSerializer SHALL prevent account creation and return the failure reason to the submitter.
2. WHILE `IDVerification.status` is `pending` or `flagged`, THE IDVerificationService SHALL allow the Member account to be created but SHALL set the account to an `unverified` state that restricts loan application access.
3. WHEN `IDVerification.status` transitions to `verified` by a StaffReviewer or the SmileIdentityAPI, THE IDVerificationService SHALL lift the `unverified` restriction on the Member account.
4. THE IDVerificationService SHALL send an in-app Notification to the Member when `IDVerification.status` changes to `verified`, `failed`, or `flagged`.
5. WHEN `IDVerification.status` is set to `flagged` or `pending`, THE IDVerificationService SHALL send an in-app Notification to all active StaffReviewers indicating that a new ID verification requires manual review.

---

### Requirement 5: CRB Check on Loan Application

**User Story:** As a loan officer, I want the system to automatically query the Credit Reference Bureau when a member applies for a loan, so that I can make informed lending decisions without performing manual bureau checks.

#### Acceptance Criteria

1. WHEN a Member submits a loan application, THE LoanApplicationProcessor SHALL invoke the CRBService before setting the initial `Loan.status`.
2. THE CRBService SHALL query TransUnion Kenya or Metropol using the Member's `national_id` and `full_name` as the lookup parameters.
3. THE CRBService SHALL persist the bureau response as a `CRBCheck` record linked to the `Loan`, storing: `bureau_name`, `check_status` (`passed`, `flagged`, `failed`, `pending_manual`, `not_configured`), `raw_response` (JSON), `checked_at` (datetime), and `failure_reason` (text).
4. IF the CRB bureau API is not configured (credentials absent), THEN THE CRBService SHALL create a `CRBCheck` record with `check_status` set to `not_configured` and set `Loan.status` to `pending` for manual staff review.
5. IF the CRB bureau API returns a transient error, THEN THE CRBService SHALL create a `CRBCheck` record with `check_status` set to `pending_manual` and set `Loan.status` to `pending`.
6. IF the CRB bureau reports the applicant is blacklisted or has outstanding defaulted debt, THEN THE CRBService SHALL set `CRBCheck.check_status` to `flagged` and set `Loan.status` to `flagged`.
7. IF the CRB bureau confirms the applicant has a clean credit record, THEN THE CRBService SHALL set `CRBCheck.check_status` to `passed` and allow the `LoanApplicationProcessor` to proceed with standard eligibility evaluation.

---

### Requirement 6: Multi-Bank Active Loan Detection

**User Story:** As a loan officer, I want to know whether a loan applicant has active loans at other financial institutions before processing their application, so that over-indebtedness risk is managed.

#### Acceptance Criteria

1. WHEN the CRBService queries the bureau, THE CRBService SHALL extract and record the count of active external loan facilities in `CRBCheck.raw_response` under the key `active_external_loans`.
2. IF `active_external_loans` is greater than zero, THEN THE CRBService SHALL set `CRBCheck.check_status` to `flagged` and include the count and creditor names (where available from the bureau response) in `CRBCheck.failure_reason`.
3. WHERE the bureau response does not include a structured active-loans field, THE CRBService SHALL record `active_external_loans` as `null` and set `CRBCheck.check_status` to `pending_manual`.

---

### Requirement 7: Flagged Loan Application — Staff Review Workflow

**User Story:** As a loan officer, I want to be notified when a loan application is flagged due to CRB or multi-bank issues, so that I can review the case and make a final decision.

#### Acceptance Criteria

1. WHEN `Loan.status` is set to `flagged`, THE LoanApplicationProcessor SHALL send an in-app Notification to all active StaffReviewers with the `loan_officer` or `superadmin` role, including the Member's name, loan amount, and the flag reason.
2. WHEN `Loan.status` is set to `flagged`, THE LoanApplicationProcessor SHALL send an in-app Notification to the Member stating that their loan application is under review.
3. WHEN a StaffReviewer sets `Loan.status` from `flagged` to `approved` or `rejected`, THE LoanApplicationProcessor SHALL send an in-app Notification to the Member with the final decision and any recorded remarks.
4. THE LoanApplicationProcessor SHALL record a `loan_apply` AuditLog entry that includes the `CRBCheck.check_status` and the flag reason whenever a loan application results in a `flagged` status.
5. WHILE `Loan.status` is `flagged`, THE LoanApplicationProcessor SHALL prevent the loan from being disbursed until a StaffReviewer explicitly approves it.

---

### Requirement 8: Audit and Transparency

**User Story:** As a SACCO auditor, I want all identity verification and credit check events to be recorded in the audit log, so that the verification trail is available for compliance review.

#### Acceptance Criteria

1. WHEN `IDVerification.status` changes for any reason, THE IDVerificationService SHALL create an AuditLog entry with action `member_update`, recording the previous status, new status, and the actor (system or StaffReviewer).
2. WHEN a `CRBCheck` record is created, THE CRBService SHALL create an AuditLog entry with action `loan_apply`, recording the `bureau_name`, `check_status`, and `Loan.id`.
3. WHEN a StaffReviewer manually overrides an `IDVerification` or `CRBCheck` outcome, THE IDVerificationService or CRBService SHALL create an AuditLog entry recording the reviewer's identity, the previous status, and the new status.
4. THE IDVerificationService SHALL NOT record raw government ID document images or full OCR text in the AuditLog; only structured metadata fields (status, provider, check result) SHALL be logged.
