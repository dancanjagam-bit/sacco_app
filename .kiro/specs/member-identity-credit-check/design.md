# Design Document

## Member Identity Verification and Credit Check System

---

## Overview

This design extends the existing SACCO application with two integrated pipelines:

1. **Identity verification pipeline** — triggered at registration. The member uploads a National ID document; the backend runs OCR to extract name, ID number, and date of birth; extracted data is cross-checked against the submitted registration fields; and the Smile Identity KYC API is called to confirm against government records.

2. **Credit check pipeline** — triggered at loan application. The backend calls a CRB provider (TransUnion Kenya or Metropol) to check for blacklisting or defaulted debt, and extracts the count of active loan facilities at other institutions. Results gate loan approval and notify the relevant staff.

Both pipelines follow a **soft-flag** pattern: definitive failures block the operation, transient errors or soft findings set a `flagged`/`pending` status that routes the record to staff manual review. All state transitions are audit-logged and trigger in-app notifications.

The backend is **Django REST Framework**; the frontend is **React**. Code examples are in Python (backend) and JavaScript/JSX (frontend).

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Registration Flow                       │
│                                                             │
│  React Form → POST /api/register/ (multipart/form-data)    │
│       │                                                     │
│       ▼                                                     │
│  RegistrationSerializer                                     │
│  (validates file type/size + existing fields)               │
│       │                                                     │
│       ▼                                                     │
│  IDVerificationService.run(user, id_document, form_data)   │
│       ├── 1. FileValidator (MIME + size)                    │
│       ├── 2. OCRPipeline.extract(file)                      │
│       ├── 3. NameMatcher.compare(ocr_name, form_name)       │
│       └── 4. SmileIdentityClient.verify(id_num, name)       │
│                │                                            │
│                ▼                                            │
│       IDVerification (DB record)                            │
│       Notification + AuditLog                               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    Loan Application Flow                     │
│                                                             │
│  React Form → POST /api/loan/apply/                        │
│       │                                                     │
│       ▼                                                     │
│  LoanApplicationProcessor.apply(user, loan_data)           │
│       ├── 1. ID verification gate (status != unverified)    │
│       ├── 2. EligibilityEngine (existing)                   │
│       ├── 3. CRBService.check(user, loan)                   │
│       │       ├── CRBClient.query(national_id, full_name)   │
│       │       ├── ActiveLoanExtractor.parse(response)       │
│       │       └── CRBCheck (DB record)                      │
│       └── 4. Status assignment + Notification + AuditLog   │
└─────────────────────────────────────────────────────────────┘
```

---

## Components and Interfaces

### 1. `IDVerificationService` (`accounts/services/id_verification_service.py`)

Orchestrates the full identity check pipeline for a new member. Called from the registration view after `RegistrationSerializer` validates the non-file fields.

Responsibilities:
- Accept the `id_document` file and run `FileValidator`
- Call `OCRPipeline.extract()`
- Call `NameMatcher.compare()`
- Call the existing `call_smile_identity()` (or the new `SmileIdentityClient`)
- Write/update the `IDVerification` record
- Dispatch in-app `Notification` objects to the member and to staff
- Write `AuditLog` entries on every status change

### 2. `FileValidator` (`accounts/services/file_validator.py`)

Pure validation; does not touch the database.

```python
ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "application/pdf",
}
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB

def validate_id_document(file) -> None:
    """Raises ValidationError if file type or size is invalid."""
    import mimetypes, magic  # python-magic for reliable MIME detection
    mime = magic.from_buffer(file.read(2048), mime=True)
    file.seek(0)
    if mime not in ALLOWED_MIME_TYPES:
        raise ValidationError(
            f"Unsupported file type '{mime}'. "
            "Please upload a JPEG, PNG, or PDF."
        )
    if file.size > MAX_FILE_SIZE_BYTES:
        raise ValidationError(
            "ID document exceeds the 5 MB size limit. "
            "Please upload a smaller file."
        )
```

### 3. `OCRPipeline` (`accounts/services/ocr_pipeline.py`)

Extracts structured identity fields from an ID document. The initial implementation uses `pytesseract` + `Pillow` for images and `pdfplumber` for PDFs, with regex post-processing for Kenyan National ID card layout. The interface is provider-agnostic so a hosted OCR API (Google Vision, AWS Textract) can replace the local engine later.

```python
@dataclass
class OCRResult:
    ocr_full_name: str | None
    ocr_id_number: str | None
    ocr_dob: str | None       # ISO 8601 date string, e.g. "1990-05-14"
    raw_text: str
    confidence: float         # 0.0–1.0 estimate

def extract(file) -> OCRResult:
    """Extract identity fields from an ID document file object."""
```

Extraction pipeline:
1. Convert PDF first page to image (pdfplumber → PIL Image) or read JPEG/PNG directly.
2. Pre-process image: grayscale → contrast enhancement → adaptive thresholding (via Pillow/OpenCV).
3. Run Tesseract OCR with `--psm 6` (uniform block of text).
4. Apply regex patterns specific to Kenyan ID card layout to locate name, ID number, and date fields.
5. Return `OCRResult`; set fields to `None` if regex finds no match.

If any required field is `None`, `IDVerificationService` sets `IDVerification.status = "flagged"`.

### 4. `NameMatcher` (`accounts/services/name_matcher.py`)

Compares the OCR-extracted name against the submitted registration name. Uses token-set ratio from `thefuzz` (SequenceMatcher-based) to tolerate middle-name inclusion/exclusion, abbreviation, and minor OCR errors.

```python
MATCH_THRESHOLD = 80  # configurable via SACCOSettings or env var

def compare(ocr_name: str, submitted_first: str, submitted_last: str) -> tuple[bool, float, str]:
    """
    Returns (matches, score, reason).
    score is 0–100; matches is True when score >= MATCH_THRESHOLD.
    """
    from thefuzz import fuzz
    submitted_full = f"{submitted_first} {submitted_last}".strip().lower()
    ocr_normalised = " ".join(ocr_name.lower().split())
    score = fuzz.token_set_ratio(ocr_normalised, submitted_full)
    if score >= MATCH_THRESHOLD:
        return True, score, ""
    return False, score, (
        f"Name mismatch: OCR extracted '{ocr_name}', "
        f"submitted '{submitted_first} {submitted_last}' (score {score}/100, threshold {MATCH_THRESHOLD})."
    )
```

### 5. `CRBService` (`core/services/crb_service.py`)

Queries a CRB provider and writes a `CRBCheck` record.

```python
def check(user, loan: Loan) -> CRBCheck:
    """Run a CRB check for a loan application. Returns the CRBCheck record."""
```

Internally delegates to:
- `TransUnionClient` or `MetropolClient` (chosen by env var `CRB_PROVIDER`)
- `ActiveLoanExtractor.parse(raw_response)` to derive `active_external_loans`

Fallback chain:
1. No credentials → `check_status = "not_configured"`
2. HTTP 5xx / timeout → `check_status = "pending_manual"`
3. Blacklisted/defaulted flag in response → `check_status = "flagged"`
4. `active_external_loans > 0` → `check_status = "flagged"`
5. Clean record → `check_status = "passed"`

### 6. `CRBClient` (`core/services/crb_client.py`)

Provider-agnostic interface. Concrete implementations for TransUnion Kenya and Metropol are swapped via the `CRB_PROVIDER` environment variable.

```python
class CRBClientBase:
    def query(self, national_id: str, full_name: str) -> dict:
        """Return raw bureau response as a dict."""
        raise NotImplementedError

class TransUnionKenyaClient(CRBClientBase):
    BASE_URL = "https://api.transunion.co.ke/v1"
    # Auth: OAuth 2.0 client_credentials; credentials from env

class MetropolClient(CRBClientBase):
    BASE_URL = "https://api.metropol.co.ke/reference/v2"
    # Auth: API key in header; credential from env

def get_crb_client() -> CRBClientBase:
    provider = os.getenv("CRB_PROVIDER", "").lower()
    if provider == "transunion":
        return TransUnionKenyaClient()
    if provider == "metropol":
        return MetropolClient()
    return None  # not configured
```

### 7. `ActiveLoanExtractor` (`core/services/crb_service.py`)

Pure parsing function — given a raw CRB response dict, returns the count of active external loan facilities and a list of creditor names.

```python
def parse_active_loans(raw_response: dict) -> tuple[int | None, list[str]]:
    """
    Returns (count, creditor_names).
    Returns (None, []) if the response lacks a structured loans field.
    """
```

### 8. `LoanApplicationProcessor` extensions (`core/views.py`)

The existing `apply_loan` view is extended to:
1. Gate on `IDVerification.status != "unverified"` (or the member having no `IDVerification` at all).
2. Call `CRBService.check()` before writing `Loan.status`.
3. Assign `Loan.status = "flagged"` when `CRBCheck.check_status` is `flagged`.
4. Fire notifications and audit log entries.

---

## Data Models

### `IDVerification` (existing — extended)

The existing model in `accounts/models.py` already has `status`, `provider_response`, `failure_reason`, `verified_by`, and `verified_at`. Two fields are added:

```python
class IDVerification(models.Model):
    # ... existing fields unchanged ...

    # New fields
    id_document    = models.FileField(
        upload_to="id_documents/%Y/%m/",
        null=True, blank=True,
        help_text="Uploaded National ID document (JPEG, PNG, or PDF)"
    )
    ocr_result     = models.JSONField(
        default=dict, blank=True,
        help_text="Structured OCR output: ocr_full_name, ocr_id_number, ocr_dob, confidence"
    )
```

The `status` field already has `pending`, `verified`, `failed`, `flagged` — no change needed.

### `CRBCheck` (new — `core/models.py`)

```python
class CRBCheck(models.Model):
    CHECK_STATUS_CHOICES = [
        ("passed",          "Passed — Clean Record"),
        ("flagged",         "Flagged — Issues Found"),
        ("failed",          "Failed — Hard Block"),
        ("pending_manual",  "Pending Manual Review"),
        ("not_configured",  "Bureau Not Configured"),
    ]

    loan           = models.OneToOneField(
        "Loan", on_delete=models.CASCADE, related_name="crb_check"
    )
    bureau_name    = models.CharField(max_length=50, blank=True, default="")
    check_status   = models.CharField(
        max_length=20, choices=CHECK_STATUS_CHOICES, default="pending_manual"
    )
    raw_response   = models.JSONField(default=dict, blank=True)
    checked_at     = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True, default="")
    checked_by_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="crb_reviews"
    )
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"CRBCheck loan#{self.loan_id} — {self.check_status} ({self.bureau_name or 'no bureau'})"
```

### `Loan` model extension

Add `flagged` to `STATUS_CHOICES`:

```python
STATUS_CHOICES = [
    ("pending",  "Pending"),
    ("flagged",  "Flagged — Under Review"),   # NEW
    ("approved", "Approved"),
    ("rejected", "Rejected"),
    ("repaid",   "Repaid"),
]
```

### `Member` model extension

Add `is_id_verified` property (or rely on `IDVerification.status`) to gate loan applications. Rather than adding a redundant field, the processor queries `IDVerification` at loan application time.

---

### Interfaces

#### Registration endpoint change

`POST /api/register/` changes from `application/json` to `multipart/form-data` to accept the file upload alongside the existing text fields.

`RegistrationSerializer` gains:
```python
id_document = serializers.FileField(required=True)

def validate_id_document(self, file):
    from accounts.services.file_validator import validate_id_document
    validate_id_document(file)  # raises ValidationError on bad type/size
    return file
```

#### New admin endpoints (ID verification)

| Method | URL | Description |
|---|---|---|
| `GET` | `/api/admin/id-verifications/` | List all IDVerification records (paginated) |
| `GET` | `/api/admin/id-verifications/<id>/` | Detail view with OCR result |
| `PATCH` | `/api/admin/id-verifications/<id>/review/` | Staff manually overrides status |

#### New admin endpoints (CRB)

| Method | URL | Description |
|---|---|---|
| `GET` | `/api/admin/crb-checks/` | List all CRBCheck records (paginated) |
| `GET` | `/api/admin/crb-checks/<id>/` | Detail view with raw bureau response |
| `PATCH` | `/api/admin/crb-checks/<id>/review/` | Staff manually overrides check_status |
| `POST` | `/api/admin/loan/<id>/flag-override/` | Override flagged loan to approved/rejected |

#### Member-facing endpoints

| Method | URL | Description |
|---|---|---|
| `GET` | `/api/my-verification/` | Member views their own IDVerification status |

---

## Error Handling

| Scenario | HTTP status | Behaviour |
|---|---|---|
| Invalid file type at upload | 400 | `{"id_document": ["Unsupported file type…"]}` |
| File too large | 400 | `{"id_document": ["ID document exceeds the 5 MB size limit…"]}` |
| OCR extraction fails | 201 (account created) | `IDVerification.status = "flagged"`, staff notified |
| Name mismatch | 201 (account created) | `IDVerification.status = "flagged"`, member notified |
| SmileIdentity hard rejection | 400 | Registration blocked, `IDVerification.status = "failed"` |
| SmileIdentity transient error | 201 (account created) | `IDVerification.status = "pending"`, staff notified |
| CRB not configured | 201 (loan created) | `CRBCheck.check_status = "not_configured"`, `Loan.status = "pending"` |
| CRB transient error | 201 (loan created) | `CRBCheck.check_status = "pending_manual"`, `Loan.status = "pending"` |
| CRB flags applicant | 201 (loan created) | `CRBCheck.check_status = "flagged"`, `Loan.status = "flagged"`, staff notified |
| Loan disbursal on flagged loan | 403 | `{"detail": "Loan is flagged and cannot be disbursed until reviewed."}` |
| Loan application while ID unverified | 403 | `{"detail": "Your identity has not been verified. Please await staff review."}` |

---

## Storage

ID documents are stored under `MEDIA_ROOT/id_documents/YYYY/MM/<uuid>.<ext>`. Upload paths use UUIDs (not the member's ID or username) to avoid enumeration. The `FileField` is served only to authenticated staff; members cannot directly download their stored document via the API.

Settings addition (`sacco/settings.py`):
```python
# ID document upload
ID_DOCUMENT_UPLOAD_PATH = "id_documents"
NAME_MATCH_THRESHOLD = int(os.getenv("NAME_MATCH_THRESHOLD", "80"))
CRB_PROVIDER = os.getenv("CRB_PROVIDER", "")  # "transunion" | "metropol" | ""
TRANSUNION_API_KEY    = os.getenv("TRANSUNION_API_KEY", "")
TRANSUNION_API_SECRET = os.getenv("TRANSUNION_API_SECRET", "")
METROPOL_API_KEY      = os.getenv("METROPOL_API_KEY", "")
```

---

## Notification Strategy

All in-app notifications use the existing `Notification.send()` method.

| Event | Recipient | Type | Title |
|---|---|---|---|
| ID verification → `verified` | Member | `success` | "Identity Verified" |
| ID verification → `failed` | Member | `error` | "Identity Verification Failed" |
| ID verification → `flagged` | Member | `warning` | "Identity Under Review" |
| ID verification → `flagged`/`pending` | All active StaffReviewers | `warning` | "New ID Verification Requires Review" |
| Loan → `flagged` | Member | `warning` | "Loan Application Under Review" |
| Loan → `flagged` | All loan officers + superadmins | `warning` | "Flagged Loan Application Requires Review" |
| Flagged loan → `approved` | Member | `success` | "Loan Application Approved" |
| Flagged loan → `rejected` | Member | `error` | "Loan Application Rejected" |

---

## Audit Log Strategy

Extends the existing `AuditLog` model with two new `action` values:

```python
("id_verification_status_change", "ID Verification Status Change"),
("crb_check_created",             "CRB Check Created"),
```

All existing `AuditLog.ACTION_CHOICES` remain unchanged. Entries are written by:
- `IDVerificationService` on every status change
- `CRBService` when a `CRBCheck` record is created
- Staff review views when a reviewer manually overrides a status

Fields logged per event:
- `IDVerification` status change: `{prev_status, new_status, provider, national_id_hash (SHA-256), actor}`
- `CRBCheck` creation: `{bureau_name, check_status, loan_id, active_external_loans}`
- Staff override: `{reviewer_username, prev_status, new_status, reason}`

Raw document image bytes and full OCR text are **never** written to `AuditLog.details`.

---

## Frontend Components

### `IDDocumentUpload` (`frontend/src/components/IDDocumentUpload.js`)

A controlled file input that:
- Accepts `image/jpeg,image/png,application/pdf`
- Shows file size and a thumbnail preview for images
- Displays validation errors returned by the API

Used inside `Register.js`.

### `VerificationStatusBadge` (`frontend/src/components/VerificationStatusBadge.js`)

Reusable badge showing `pending` / `verified` / `flagged` / `failed` with appropriate colour.

Used in `MemberProfile.js` and `AdminMembers.js`.

### `AdminIDVerifications.js` (`frontend/src/pages/AdminIDVerifications.js`)

Staff page listing all pending/flagged ID verifications with:
- Filter by status
- Detail modal showing extracted OCR fields and Smile Identity response
- Approve / Reject buttons that call `PATCH /api/admin/id-verifications/<id>/review/`

### `AdminCRBChecks.js` (`frontend/src/pages/AdminCRBChecks.js`)

Staff page listing CRB check records tied to loan applications with:
- `check_status` badge
- Active external loans count
- Override button for manual review resolution

---

## Dependency Additions

The following packages need to be added to `requirements.txt`:

| Package | Version | Purpose |
|---|---|---|
| `pytesseract` | `0.3.13` | OCR engine wrapper |
| `Pillow` | `11.2.1` | Image processing for OCR pre-processing |
| `pdfplumber` | `0.11.4` | PDF text / image extraction |
| `thefuzz` | `0.22.1` | Fuzzy name matching |
| `python-magic` | `0.4.27` | Reliable MIME type detection |

`pytesseract` requires the Tesseract binary to be installed on the host OS (`apt install tesseract-ocr` on Debian/Ubuntu). For production, a hosted OCR API is recommended.

---

## Testing Strategy

**Unit tests** cover specific examples, error-path branches, and integration points between components:
- `FileValidator` accepts each of the three allowed MIME types and rejects others; rejects files above 5 MB and accepts files at or below the limit.
- `IDVerificationService` routes to the correct `IDVerification.status` for each outcome: OCR failure → `flagged`; name mismatch → `flagged`; SmileIdentity hard rejection → `failed`; SmileIdentity transient error → `pending`; SmileIdentity success → `verified`.
- `CRBService` assigns the correct `check_status` and `Loan.status` for each bureau response scenario (not configured, transient error, blacklisted, active loans, clean).
- Staff review endpoints correctly gate disbursement while `Loan.status` is `flagged` and lift the gate after approval.

**Property-based tests** (using Hypothesis) verify universal invariants across a wide range of generated inputs:
- File format and size validation boundaries (Properties 1, 2)
- `OCRPipeline` output structure completeness (Property 3)
- Persistence round-trips for OCR data and Smile Identity API responses (Properties 4, 6)
- Case/whitespace invariance of `NameMatcher` (Property 5)
- Notification fan-out to all qualifying staff (Properties 7, 11)
- `CRBCheck` record field completeness (Property 8)
- Active loan count extraction correctness (Properties 9, 10)
- `AuditLog` creation on all status transitions (Properties 12, 13)

Each property test runs a minimum of 100 randomly generated examples. Pure functions (`FileValidator`, `NameMatcher`, `ActiveLoanExtractor`) are tested without database access; service-level properties mock external API calls and use `pytest-django`'s `db` fixture for persistence round-trips.

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Valid file formats are accepted; invalid formats are rejected

*For any* uploaded file, the `FileValidator` SHALL accept it if and only if its detected MIME type is `image/jpeg`, `image/png`, or `application/pdf`.

**Validates: Requirements 1.2, 1.3**

---

### Property 2: File size boundary is enforced correctly

*For any* uploaded file of a valid MIME type, the `FileValidator` SHALL accept the file if its size is ≤ 5,242,880 bytes (5 MB) and reject it if its size exceeds that threshold.

**Validates: Requirements 1.4**

---

### Property 3: OCR output structure is always complete or gracefully absent

*For any* call to `OCRPipeline.extract()` that returns a result without raising an exception, the returned `OCRResult` object SHALL contain the keys `ocr_full_name`, `ocr_id_number`, `ocr_dob`, `raw_text`, and `confidence` — each field is either a non-empty string/float or explicitly `None`.

**Validates: Requirements 2.3**

---

### Property 4: OCR data is persisted faithfully in IDVerification

*For any* `OCRResult` returned by the pipeline, after `IDVerificationService` saves the `IDVerification` record, re-reading `IDVerification.ocr_result` from the database SHALL contain the same `ocr_full_name`, `ocr_id_number`, and `ocr_dob` values as the original `OCRResult`.

**Validates: Requirements 2.4**

---

### Property 5: Name comparison is case- and whitespace-invariant

*For any* OCR-extracted name string and submitted registration name, applying any combination of case transformation (upper, lower, mixed) or additional surrounding/internal whitespace to either name SHALL NOT change the boolean match outcome returned by `NameMatcher.compare()`.

**Validates: Requirements 3.2**

---

### Property 6: Smile Identity API response is persisted faithfully

*For any* response dict returned by `call_smile_identity()`, after `IDVerificationService` saves the `IDVerification` record, re-reading `IDVerification.provider_response` from the database SHALL contain the same top-level keys and values as the original response dict.

**Validates: Requirements 3.8**

---

### Property 7: Member and staff are notified on every IDVerification status transition

*For any* transition of `IDVerification.status` to `verified`, `failed`, or `flagged`, the `IDVerificationService` SHALL create at least one `Notification` record for the owning member. *For any* transition to `flagged` or `pending`, at least one `Notification` SHALL also be created for every active `StaffProfile` with a reviewer-eligible role.

**Validates: Requirements 4.4, 4.5**

---

### Property 8: CRBCheck record always contains all required fields after creation

*For any* invocation of `CRBService.check()`, the resulting `CRBCheck` record persisted in the database SHALL have non-null values for `bureau_name` (may be empty string when not configured), `check_status`, `checked_at`, and a `raw_response` dict (may be empty `{}`).

**Validates: Requirements 5.3**

---

### Property 9: Active external loans count is extracted correctly from bureau responses

*For any* bureau response dict that contains a structured list of active loan facilities, `ActiveLoanExtractor.parse_active_loans()` SHALL return a count equal to the number of active facility entries in that list, and `CRBCheck.raw_response["active_external_loans"]` SHALL equal that count.

**Validates: Requirements 6.1**

---

### Property 10: Any positive active loan count triggers a flagged status

*For any* bureau response where `active_external_loans` is a positive integer N > 0, `CRBService.check()` SHALL set `CRBCheck.check_status` to `flagged` and `CRBCheck.failure_reason` SHALL contain the string representation of N.

**Validates: Requirements 6.2**

---

### Property 11: Flagged loans notify all qualifying staff

*For any* set of active `StaffProfile` records where role is `loan_officer` or `superadmin`, when `Loan.status` is set to `flagged`, every member of that set SHALL receive a `Notification` record created in the same database transaction.

**Validates: Requirements 7.1**

---

### Property 12: AuditLog entry is created for every IDVerification status change

*For any* change to `IDVerification.status`, the `IDVerificationService` SHALL create an `AuditLog` record whose `details` field contains both the previous status value and the new status value.

**Validates: Requirements 8.1**

---

### Property 13: AuditLog entry is created for every CRBCheck record

*For any* `CRBCheck` record created by `CRBService.check()`, there SHALL exist at least one `AuditLog` record whose `details` field contains `bureau_name`, `check_status`, and `loan_id` values matching those of the `CRBCheck`.

**Validates: Requirements 8.2**
