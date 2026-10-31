# Design Document

## Member Identity & CRB Check System (with Face Verification)

---

## Overview

This design covers two automated compliance pipelines for the SACCO application:

1. **Registration pipeline** — members upload a government ID document and a selfie photo during registration. The backend runs OCR to extract name, ID number, and date of birth from the ID; cross-checks the name against the registration form; calls the Smile Identity KYC API; and calls the Smile Identity SmartSelfie biometric API to confirm the selfie face matches the ID document photo. All results are stored on the extended `IDVerification` model and gate registration access.

2. **Loan application pipeline** — on every new loan application the system calls a CRB provider (TransUnion Kenya or Metropol, swapped via `CRB_PROVIDER` env var), detects active external loans, and flags the application for officer review when credit risk is found.

Both pipelines follow a **soft-flag** pattern: definitive failures block the operation, while transient errors or soft findings set a `flagged`/`pending` status that routes the record to staff manual review. All state transitions produce `Notification` records and `AuditLog` entries.

Backend: **Django REST Framework**. Frontend: **React**. Code examples are in Python (backend) and JavaScript/JSX (frontend).

---

## Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│                        Registration Flow                           │
│                                                                   │
│  React Form → POST /api/register/ (multipart/form-data)          │
│       │                                                           │
│       ▼                                                           │
│  RegistrationSerializer                                           │
│  (validates id_document type/size + selfie type/size)            │
│       │                                                           │
│       ▼                                                           │
│  IDVerificationService.run(user, id_document, selfie, form_data) │
│       ├── 1. FileValidator (id_document MIME + size)              │
│       ├── 2. OCRPipeline.extract(id_document)                     │
│       ├── 3. NameMatcher.compare(ocr_name, form_name)             │
│       ├── 4. SmileIdentityClient.verify(id_num, name)             │
│       └── 5. FaceVerificationService.verify(selfie, id_document)  │
│                │                                                  │
│                ▼                                                  │
│       IDVerification (DB record)                                  │
│       Notification + AuditLog                                     │
└───────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│                     Loan Application Flow                          │
│                                                                   │
│  React Form → POST /api/loan/apply/                              │
│       │                                                           │
│       ▼                                                           │
│  LoanApplicationProcessor.apply(user, loan_data)                 │
│       ├── 1. ID verification gate (status must not be pending)    │
│       ├── 2. EligibilityEngine (existing)                         │
│       ├── 3. CRBService.check(user, loan)                         │
│       │       ├── CRBClient.query(national_id, full_name)         │
│       │       ├── ActiveLoanExtractor.parse(response)             │
│       │       └── CRBCheck (DB record)                            │
│       └── 4. Status assignment + Notification + AuditLog         │
└───────────────────────────────────────────────────────────────────┘
```

---

## Components and Interfaces

### 1. `IDVerificationService` (`accounts/services/id_verification_service.py`)

Orchestrates the full identity check pipeline for a new member. Called from the registration view after `RegistrationSerializer` validates the non-file fields.

Responsibilities:
- Accept the `id_document` and `selfie` files; run `FileValidator` on each
- Call `OCRPipeline.extract()` on the ID document
- Call `NameMatcher.compare()` against the form name
- Call the existing `call_smile_identity()` from `accounts/id_verification.py`
- Call `FaceVerificationService.verify()` when both files are present
- Write/update the `IDVerification` record
- Dispatch in-app `Notification` objects to the member and to staff
- Write `AuditLog` entries on every status-affecting outcome

Orchestration flow and status resolution (each step can short-circuit):

```
Step 1: FileValidator(id_document)           → 400 on invalid type/size
Step 2: FileValidator(selfie)                → 400 on invalid type (jpeg/png/gif only, no PDF)
Step 3: OCRPipeline.extract(id_document)     → stores ocr_result; missing fields → "flagged"
Step 4: NameMatcher.compare(ocr_name, form_name)
        score < NAME_MATCH_THRESHOLD         → status = "flagged"; continue to face check
Step 5: call_smile_identity(national_id, …)
        success = False                      → status = "failed"; return 400
        success = None                       → status = "pending"
        success = True                       → continue to face check
Step 6: FaceVerificationService.verify(selfie, id_document)
        liveness_passed = False              → status = "flagged"
        face_match_score < THRESHOLD         → status = "flagged"
        API not configured / error           → status = "pending"
        all pass                             → status = "verified"
```

Note: Steps 4 and 6 set `flagged` but do not block registration — the member is queued for staff review.

### 2. `FileValidator` (`accounts/services/file_validator.py`)

Pure validation; does not touch the database.

```python
ID_DOC_ALLOWED_MIME = {"image/jpeg", "image/png", "image/gif", "application/pdf"}
SELFIE_ALLOWED_MIME = {"image/jpeg", "image/png", "image/gif"}
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB (configurable via ID_DOC_MAX_MB)

def validate_id_document(file) -> None:
    """Raises ValidationError if file type or size is invalid."""
    import magic
    mime = magic.from_buffer(file.read(2048), mime=True)
    file.seek(0)
    if mime not in ID_DOC_ALLOWED_MIME:
        raise ValidationError(
            f"Unsupported file type '{mime}'. "
            "Please upload a JPEG, PNG, GIF, or PDF."
        )
    if file.size > MAX_FILE_SIZE_BYTES:
        raise ValidationError(
            "ID document exceeds the 5 MB size limit."
        )

def validate_selfie(file) -> None:
    """Raises ValidationError if selfie file type is invalid (PDF not allowed)."""
    import magic
    mime = magic.from_buffer(file.read(2048), mime=True)
    file.seek(0)
    if mime not in SELFIE_ALLOWED_MIME:
        raise ValidationError(
            f"Unsupported file type '{mime}'. "
            "Please upload a JPEG, PNG, or GIF selfie."
        )
    if file.size > MAX_FILE_SIZE_BYTES:
        raise ValidationError("Selfie exceeds the 5 MB size limit.")
```

### 3. `OCRPipeline` (`accounts/services/ocr_pipeline.py`)

Extracts structured identity fields from an ID document. Uses `pytesseract` + `Pillow` for images and `pdfplumber` for PDFs, with regex post-processing for the Kenyan National ID card layout. The interface is provider-agnostic so a hosted OCR API can replace the local engine later.

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
1. Convert PDF first page to image (pdfplumber → PIL Image) or read JPEG/PNG/GIF directly.
2. Pre-process: grayscale → contrast enhancement → adaptive thresholding.
3. Run Tesseract OCR with `--psm 6`.
4. Apply regex patterns for Kenyan ID card layout to locate name, ID number, and DOB.
5. Return `OCRResult`; set fields to `None` if regex finds no match.

### 4. `NameMatcher` (`accounts/services/name_matcher.py`)

Compares the OCR-extracted name against the submitted registration name using token-set ratio from `thefuzz`.

```python
MATCH_THRESHOLD = 75  # configurable via NAME_MATCH_THRESHOLD setting

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
        f"submitted '{submitted_first} {submitted_last}' "
        f"(score {score}/100, threshold {MATCH_THRESHOLD})."
    )
```

### 5. `FaceVerificationService` (`accounts/services/face_verification_service.py`)

New service added for Requirement 9. Calls the Smile Identity SmartSelfie biometric API to compare a selfie against the face on the ID document. Builds on the existing Smile Identity credential setup in `accounts/id_verification.py`.

```python
FACE_MATCH_THRESHOLD = int(os.getenv("FACE_MATCH_THRESHOLD", "70"))

@dataclass
class FaceVerificationResult:
    face_match_score: float | None   # 0–100 from SmartSelfie API
    liveness_passed: bool
    outcome: str                     # "matched" | "flagged" | "pending"
    raw_response: dict

def verify(selfie_file, id_document_file) -> FaceVerificationResult:
    """
    Compare selfie against ID document photo via Smile Identity SmartSelfie.
    Returns FaceVerificationResult; never raises — transient failures return
    outcome="pending".
    """
```

Internal behaviour:

1. Read `SMILE_IDENTITY_API_KEY` and `SMILE_IDENTITY_PARTNER_ID` from settings.
2. If either credential is absent → return `FaceVerificationResult(face_match_score=None, liveness_passed=False, outcome="pending", raw_response={})`.
3. Build the SmartSelfie API request payload with base64-encoded selfie and id_document.
4. POST to `https://testapi.smileidentity.com/v1/smile_selfie` (or the production endpoint when `SMILE_IDENTITY_ENV=production`).
5. Parse the response:
   - Extract `SmileJobID`, `PartnerParams`, `Actions` (with `Liveness_Check` and `Selfie_To_ID_Document_Compare`), and `ResultCode`.
   - `liveness_passed = (Actions.Liveness_Check == "Passed")`
   - `face_match_score = float(Actions.get("Confidence_Value", 0))`
6. Determine outcome:
   - `liveness_passed = False` → `outcome = "flagged"`
   - `face_match_score < FACE_MATCH_THRESHOLD` → `outcome = "flagged"`
   - otherwise → `outcome = "matched"`
7. On any network or parse exception → log error, return `outcome = "pending"`.

### 6. `CRBService` (`core/services/crb_service.py`)

Queries a CRB provider and writes a `CRBCheck` record.

```python
def check(user, loan: Loan) -> CRBCheck:
    """Run a CRB check for a loan application. Returns the CRBCheck record."""
```

Internally delegates to:
- `TransUnionKenyaClient` or `MetropolClient` (chosen by `CRB_PROVIDER` env var)
- `ActiveLoanExtractor.parse(raw_response)` to derive `active_external_loans`

Fallback chain:
1. No credentials → `check_status = "not_configured"`
2. HTTP 5xx / timeout → `check_status = "pending_manual"`
3. Blacklisted/defaulted flag in response → `check_status = "flagged"`
4. `active_external_loans > 0` → `check_status = "flagged"`
5. Score below `CRB_FLAG_SCORE_THRESHOLD` (default 500) → `check_status = "flagged"`
6. Clean record → `check_status = "passed"`

### 7. `CRBClient` (`core/services/crb_client.py`)

Provider-agnostic interface. Concrete implementations swapped via `CRB_PROVIDER` env var.

```python
class CRBClientBase:
    def query(self, national_id: str, full_name: str) -> dict:
        raise NotImplementedError

class TransUnionKenyaClient(CRBClientBase):
    BASE_URL = "https://api.transunion.co.ke/v1"

class MetropolClient(CRBClientBase):
    BASE_URL = "https://api.metropol.co.ke/reference/v2"

def get_crb_client() -> CRBClientBase | None:
    provider = os.getenv("CRB_PROVIDER", "").lower()
    if provider == "transunion":
        return TransUnionKenyaClient()
    if provider == "metropol":
        return MetropolClient()
    return None  # not configured
```

### 8. `ActiveLoanExtractor` (`core/services/crb_service.py`)

Pure parsing function — given a raw CRB response dict, returns the count of active external loan facilities and a list of creditor names.

```python
def parse_active_loans(raw_response: dict) -> tuple[int | None, list[str]]:
    """
    Returns (count, creditor_names).
    Returns (None, []) if the response lacks a structured loans field.
    """
```

### 9. `LoanApplicationProcessor` extensions (`core/views.py`)

The existing `apply_loan` view is extended to:
1. Gate on `IDVerification.status != "unverified"` (or the member having no `IDVerification` at all).
2. Call `CRBService.check()` before writing `Loan.status`.
3. Assign `Loan.status = "flagged"` when `CRBCheck.check_status` is `flagged`.
4. Include `crb_status` and (if flagged) a human-readable `flag_reason` in the response.
5. Fire notifications and audit log entries.

---

## Data Models

### `IDVerification` (existing — extended)

The existing model in `accounts/models.py` gains four new fields:

```python
class IDVerification(models.Model):
    # ... existing fields unchanged ...

    # Added for Requirement 1 / 2 (document + OCR)
    id_document = models.FileField(
        upload_to="id_documents/%Y/%m/",
        null=True, blank=True,
        help_text="Uploaded National ID document (JPEG, PNG, GIF, or PDF)"
    )
    ocr_result = models.JSONField(
        default=dict, blank=True,
        help_text="Structured OCR output: ocr_full_name, ocr_id_number, ocr_dob, confidence"
    )

    # Added for Requirement 9 (face verification)
    selfie = models.FileField(
        upload_to="selfies/",
        null=True, blank=True,
        help_text="Selfie uploaded at registration for face match against ID document"
    )
    face_match_score = models.FloatField(
        null=True, blank=True,
        help_text="Smile Identity SmartSelfie confidence score (0–100); null if not yet checked"
    )
```

The existing `status` choices (`pending`, `verified`, `failed`, `flagged`) cover all face verification outcomes — no new status values are needed.

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
    override_by    = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="crb_overrides"
    )
    override_at    = models.DateTimeField(null=True, blank=True)
    override_notes = models.TextField(blank=True, default="")
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
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

### `AuditLog.ACTION_CHOICES` extension

Add all new action codes:

```python
("id_verify_submit",  "ID Verification Submitted"),
("id_verify_review",  "ID Verification Reviewed"),
("crb_check_run",     "CRB Check Run"),
("crb_override",      "CRB Flagged Loan Override"),
("loan_flagged",      "Loan Flagged by CRB"),
("face_verify",       "Face Verification Run"),   # NEW (Requirement 9)
```

---

## Interfaces

### Registration endpoint

`POST /api/register/` changes from `application/json` to `multipart/form-data` to accept file uploads alongside existing text fields.

`RegistrationSerializer` gains:

```python
id_document = serializers.FileField(required=False, allow_null=True)
selfie      = serializers.FileField(required=False, allow_null=True)

def validate_id_document(self, file):
    from accounts.services.file_validator import validate_id_document
    validate_id_document(file)  # raises ValidationError on bad type/size
    return file

def validate_selfie(self, file):
    from accounts.services.file_validator import validate_selfie
    validate_selfie(file)       # raises ValidationError on bad type (no PDF)
    return file
```

Response includes:
```json
{
  "id_status": "pending | verified | flagged | failed",
  "message": "..."
}
```

### File access endpoints (Requirement 9.11–9.12)

Selfie and ID document files must be served through a protected view — Django's default `MEDIA_URL` would expose them publicly. Add a protected media view:

```python
# accounts/views.py
class ProtectedMediaView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, path):
        # Resolve the IDVerification record from the file path
        verification = get_object_or_404(IDVerification, ...)
        if request.user != verification.user and not request.user.is_admin:
            raise PermissionDenied("You do not have permission to access this file.")
        response = FileResponse(open(full_path, "rb"))
        return response
```

Register under `/api/media/protected/<path:path>/` and do NOT serve `selfies/` or `id_documents/` via the default static media handler in production.

### New admin endpoints (ID verification)

| Method | URL | Description |
|---|---|---|
| `GET` | `/api/accounts/admin/id-verifications/` | List all IDVerification records (paginated, filterable by status) |
| `GET` | `/api/accounts/admin/id-verifications/<id>/` | Detail view including `ocr_result`, `id_document` URL, and `selfie` URL |
| `POST` | `/api/accounts/admin/id-verifications/<id>/review/` | Staff manually overrides status and posts review notes |

The detail response includes both file URLs so staff can compare the selfie against the ID document in the review workflow (Requirement 9.14).

### New admin endpoints (CRB)

| Method | URL | Description |
|---|---|---|
| `GET` | `/api/core/admin/crb-checks/` | List all CRBCheck records (filterable by status, loan) |
| `GET` | `/api/core/admin/crb-checks/<id>/` | Detail view with `raw_response` |
| `POST` | `/api/core/admin/crb-checks/<id>/override/` | Override flagged loan with notes; sets `Loan.status = "approved"` |

All admin endpoints require `IsAdmin` permission; return 403 for non-admin callers.

---

## Error Handling

| Scenario | HTTP status | Behaviour |
|---|---|---|
| Invalid id_document type | 400 | `{"id_document": ["Unsupported file type…"]}` |
| id_document too large | 400 | `{"id_document": ["ID document exceeds the 5 MB size limit."]}` |
| Invalid selfie type (e.g. PDF) | 400 | `{"selfie": ["Unsupported file type 'application/pdf'. Please upload a JPEG, PNG, or GIF selfie."]}` |
| selfie too large | 400 | `{"selfie": ["Selfie exceeds the 5 MB size limit."]}` |
| OCR extraction fails | 201 (account created) | `IDVerification.status = "flagged"`, staff notified |
| Name mismatch | 201 (account created) | `IDVerification.status = "flagged"`, member notified |
| Face match score below threshold | 201 (account created) | `IDVerification.status = "flagged"`, staff notified; `face_match_score` stored |
| Liveness check failure | 201 (account created) | `IDVerification.status = "flagged"`, staff notified |
| SmartSelfie not configured or transient error | 201 (account created) | `IDVerification.status = "pending"`, staff notified |
| No selfie provided | 201 (account created) | Face verification step skipped; `IDVerification.status = "pending"` |
| SmileIdentity KYC hard rejection | 400 | Registration blocked; `IDVerification.status = "failed"` |
| SmileIdentity KYC transient error | 201 (account created) | `IDVerification.status = "pending"`, staff notified |
| Unauthenticated request to protected file | 401 | Standard DRF 401 |
| Non-owner / non-admin request to protected file | 403 | `{"detail": "You do not have permission to access this file."}` |
| CRB not configured | 201 (loan created) | `CRBCheck.check_status = "not_configured"`, `Loan.status = "pending"` |
| CRB transient error | 201 (loan created) | `CRBCheck.check_status = "pending_manual"`, `Loan.status = "pending"` |
| CRB flags applicant | 201 (loan created) | `CRBCheck.check_status = "flagged"`, `Loan.status = "flagged"`, staff notified |
| Loan disbursal on flagged loan | 403 | `{"detail": "Loan is flagged and cannot be disbursed until reviewed."}` |
| Loan application while ID unverified | 403 | `{"detail": "Your identity has not been verified. Please await staff review."}` |

---

## Storage

Files are stored under `MEDIA_ROOT` and served only through the protected media view:

| File type | Upload path | Notes |
|---|---|---|
| ID document | `id_documents/%Y/%m/<uuid>.<ext>` | Images and PDFs; all identity-sensitive |
| Selfie | `selfies/<uuid>.<ext>` | Images only (no PDF); biometric data |

Both paths should be excluded from direct public URL access in the web server config (Nginx `deny` or S3 bucket policy). Access is routed through `ProtectedMediaView` which enforces owner-or-admin permission.

Settings additions (`sacco/settings.py`):

```python
NAME_MATCH_THRESHOLD      = int(os.getenv("NAME_MATCH_THRESHOLD", "75"))
FACE_MATCH_THRESHOLD      = int(os.getenv("FACE_MATCH_THRESHOLD", "70"))
ID_DOC_MAX_MB             = int(os.getenv("ID_DOC_MAX_MB", "5"))
CRB_PROVIDER              = os.getenv("CRB_PROVIDER", "")   # "transunion" | "metropol" | ""
CRB_FLAG_SCORE_THRESHOLD  = int(os.getenv("CRB_FLAG_SCORE_THRESHOLD", "500"))
SMILE_IDENTITY_API_KEY    = os.getenv("SMILE_IDENTITY_API_KEY", "")
SMILE_IDENTITY_PARTNER_ID = os.getenv("SMILE_IDENTITY_PARTNER_ID", "")
SMILE_IDENTITY_ENV        = os.getenv("SMILE_IDENTITY_ENV", "sandbox")  # "sandbox" | "production"
```

---

## Notification Strategy

All in-app notifications use the existing `Notification.send()` method.

| Event | Recipient | Type | Title |
|---|---|---|---|
| ID verification → `verified` | Member | `success` | "Identity Verified" |
| ID verification → `failed` | Member | `error` | "Identity Verification Failed" |
| ID verification → `flagged` (any reason) | Member | `warning` | "Identity Under Review" |
| ID verification → `flagged`/`pending` | All active StaffProfiles | `warning` | "New ID Verification Requires Review" |
| Face verification → `flagged` | Member | `warning` | "Selfie Verification Failed — Under Review" |
| Face verification → `flagged` | All active StaffProfiles | `warning` | "Face Verification Failed — Manual Review Required" |
| Face verification → `pending` (API unavailable) | All active StaffProfiles | `info` | "Face Verification Skipped — Manual Review Needed" |
| Loan → `flagged` | Member | `warning` | "Loan Application Under Review" |
| Loan → `flagged` | All loan officers + superadmins | `warning` | "Flagged Loan Application Requires Review" |
| Flagged loan → `approved` | Member | `success` | "Loan Application Approved" |
| Flagged loan → `rejected` | Member | `error` | "Loan Application Rejected" |

---

## Audit Log Strategy

Extends the existing `AuditLog` model with new `action` values:

```python
("id_verify_submit",  "ID Verification Submitted"),
("id_verify_review",  "ID Verification Reviewed"),
("crb_check_run",     "CRB Check Run"),
("crb_override",      "CRB Flagged Loan Override"),
("loan_flagged",      "Loan Flagged by CRB"),
("face_verify",       "Face Verification Run"),
```

Details logged per event:

| Event | `AuditLog.details` keys |
|---|---|
| `id_verify_submit` | `idverification_id`, `status`, `provider` |
| `face_verify` | `idverification_id`, `outcome` (`matched`/`flagged`/`pending`), `face_match_score` (float or `null`), `liveness_passed` (bool or `null`) |
| `id_verify_review` | `idverification_id`, `prev_status`, `new_status`, `notes` |
| `crb_check_run` | `crb_check_id`, `loan_id`, `bureau_name`, `check_status` |
| `loan_flagged` | `loan_id`, `crb_check_id`, `flag_reason` |
| `crb_override` | `crb_check_id`, `loan_id`, `override_by_username`, `notes` |

Raw document image bytes and full OCR text are **never** written to `AuditLog.details`. Face match scores are numeric only — no biometric image data is stored in the audit log.

---

## Frontend Components

### `IDDocumentUpload` (`frontend/src/components/IDDocumentUpload.js`)

A controlled file input that:
- Accepts `image/jpeg,image/png,image/gif,application/pdf`
- Shows file size and a thumbnail preview for images; a PDF icon for PDFs
- Displays client-side size validation error (> 5 MB) before upload
- On selection, calls the provided `onChange(file)` callback
- Accessible: label linked to input, `aria-describedby` for error messages

### `SelfieCapture` (`frontend/src/components/SelfieCapture.js`)

New component added for Requirement 9. Shown alongside `IDDocumentUpload` in `Register.js`.

```jsx
// SelfieCapture.js — webcam capture with file-upload fallback
import Webcam from "react-webcam";  // react-webcam library

function SelfieCapture({ onChange }) {
  const [mode, setMode] = useState("webcam"); // "webcam" | "upload"
  const webcamRef = useRef(null);

  const capture = () => {
    const imageSrc = webcamRef.current.getScreenshot();
    // Convert base64 data URL to a File object and pass to onChange
    dataUrlToFile(imageSrc, "selfie.jpg").then(onChange);
  };

  if (mode === "webcam") {
    return (
      <div>
        <Webcam ref={webcamRef} screenshotFormat="image/jpeg" />
        <button type="button" onClick={capture}>Take Photo</button>
        <button type="button" onClick={() => setMode("upload")}>
          Upload instead
        </button>
      </div>
    );
  }

  return (
    <input
      type="file"
      accept="image/jpeg,image/png,image/gif"
      onChange={(e) => onChange(e.target.files[0])}
      aria-label="Upload a selfie photo"
    />
  );
}
```

If `react-webcam` is unavailable (e.g. no camera permission), the component falls back to the file-upload mode automatically.

### `VerificationStatusBadge` (`frontend/src/components/VerificationStatusBadge.js`)

Reusable badge showing `pending` / `verified` / `flagged` / `failed` with appropriate colour (grey / green / amber / red).

### `AdminIDVerifications.js` (`frontend/src/pages/AdminIDVerifications.js`)

Staff page with:
- Filter tabs: All / Pending / Flagged / Verified / Failed
- Table: member name, member number, national ID, submitted date, status badge
- Detail panel: OCR result fields, ID document image/PDF preview, **selfie image preview** (new), face match score badge, Smile Identity responses
- Review action: inline form to set status + notes and call `POST .../review/`

### `AdminCRBChecks.js` (`frontend/src/pages/AdminCRBChecks.js`)

Staff page with:
- Filter tabs: All / Clear / Flagged / Error
- Table: member name, loan amount, CRB provider, score, active loans count, checked date, status badge
- Detail panel: raw CRB response, active loans list
- Override action: inline notes form calling `POST .../override/` to approve a flagged loan

---

## Dependency Additions

| Package | Version | Purpose |
|---|---|---|
| `pytesseract` | `0.3.13` | OCR engine wrapper |
| `Pillow` | `11.2.1` | Image processing for OCR pre-processing |
| `pdfplumber` | `0.11.4` | PDF text / image extraction |
| `thefuzz` | `0.22.1` | Fuzzy name matching |
| `python-magic` | `0.4.27` | Reliable MIME type detection |
| `react-webcam` | `^7.2.0` | Webcam selfie capture in the browser |

System requirements: `pytesseract` requires the Tesseract binary (`apt install tesseract-ocr`). `python-magic` requires `libmagic` (`apt install libmagic1`); on Windows use `python-magic-bin`.

---

## Testing Strategy

**Unit tests** cover specific examples, error-path branches, and integration points:
- `FileValidator` validates accepted MIME types for both ID documents (JPEG/PNG/GIF/PDF) and selfies (JPEG/PNG/GIF only, PDF rejected); size boundary enforcement.
- `FaceVerificationService` routes to the correct outcome for each scenario: liveness failure → `flagged`; low score → `flagged`; API not configured → `pending`; transient error → `pending`; all pass → `matched`.
- `IDVerificationService` correctly skips face verification when no selfie is provided and sets `status = "pending"`.
- Protected media view returns 403 for non-owner / non-admin; 200 with correct file for owner or admin.
- Admin detail endpoint returns both `selfie_url` and `id_document_url`.

**Property-based tests** (using Hypothesis) verify universal invariants:
- File format and size validation across the full input space (Properties 1–2)
- `NameMatcher` case/whitespace invariance (Property 3)
- Selfie persistence round-trip (Property 4)
- Face match threshold enforcement at every score level (Property 5)
- Liveness failure always flags regardless of score (Property 6)
- `FaceVerificationService` API call triggered iff both files present (Property 7)
- SmartSelfie response persisted faithfully in `provider_response` (Property 8)
- `AuditLog` `face_verify` entry created on every outcome (Property 9)
- Protected file access control across all user types (Property 10)
- Admin detail response always includes selfie URL (Property 11)
- `CRBCheck` record completeness (Property 12)
- Active loan count extraction correctness (Property 13)
- Flagged loan count triggers `flagged` status (Property 14)

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: File format validation is consistent for selfies

*For any* file submitted as a selfie, `FileValidator.validate_selfie()` SHALL accept it if and only if its detected MIME type is one of `image/jpeg`, `image/png`, or `image/gif` — in particular, `application/pdf` SHALL always be rejected.

**Validates: Requirements 9.2**

---

### Property 2: File size boundary is enforced for all uploaded files

*For any* uploaded file (selfie or ID document) of a valid MIME type, `FileValidator` SHALL accept the file if its size is ≤ `ID_DOC_MAX_MB × 1,048,576` bytes and reject it if its size exceeds that threshold.

**Validates: Requirements 1.3, 9.2**

---

### Property 3: Name comparison is case- and whitespace-invariant

*For any* OCR-extracted name string and submitted registration name, applying any combination of case transformation (upper, lower, mixed) or additional surrounding/internal whitespace to either name SHALL NOT change the boolean match outcome returned by `NameMatcher.compare()`.

**Validates: Requirements 3.1**

---

### Property 4: Selfie is persisted faithfully under the correct upload path

*For any* valid selfie file accepted by `FileValidator.validate_selfie()`, after `IDVerificationService.run()` completes, re-reading `IDVerification.selfie.name` from the database SHALL return a non-empty string that begins with `"selfies/"`.

**Validates: Requirements 9.3**

---

### Property 5: Face match threshold is enforced across all score values

*For any* call to `FaceVerificationService.verify()` where the Smile Identity SmartSelfie API responds with `liveness_passed = True` and a face match score `s`, the returned outcome SHALL be `"flagged"` when `s < FACE_MATCH_THRESHOLD` and SHALL be `"matched"` when `s >= FACE_MATCH_THRESHOLD`.

**Validates: Requirements 9.5, 9.6**

---

### Property 6: Liveness failure always produces a flagged outcome regardless of score

*For any* call to `FaceVerificationService.verify()` where the Smile Identity SmartSelfie API reports `liveness_passed = False`, the returned outcome SHALL be `"flagged"` regardless of the face match score value.

**Validates: Requirements 9.7**

---

### Property 7: Face verification API is called if and only if both files are present

*For any* invocation of `IDVerificationService.run()`, `FaceVerificationService.verify()` SHALL be called exactly once when `IDVerification` has both a non-null `selfie` and a non-null `id_document`, and SHALL NOT be called when either file is absent.

**Validates: Requirements 9.4, 9.13**

---

### Property 8: SmartSelfie API response is persisted faithfully in provider_response

*For any* non-empty response dict returned by the Smile Identity SmartSelfie API, after `IDVerificationService` saves the `IDVerification` record, re-reading `IDVerification.provider_response` from the database SHALL contain the same `face_match_score` value and top-level keys as the original response dict.

**Validates: Requirements 9.9**

---

### Property 9: AuditLog face_verify entry is created for every face verification outcome

*For any* call to `FaceVerificationService.verify()` that produces any outcome (`matched`, `flagged`, or `pending`), the `IDVerificationService` SHALL create exactly one `AuditLog` record with `action = "face_verify"` whose `details` dict contains `idverification_id`, `outcome`, and `face_match_score` (as a float or `null`).

**Validates: Requirements 9.10, 9.15**

---

### Property 10: Protected files are accessible only to owner and admin

*For any* `IDVerification` record and any authenticated user who is neither the owning member nor a staff user with `is_admin = True`, a GET request to the selfie URL or the id_document URL SHALL return a 403 response.

**Validates: Requirements 9.11, 9.12**

---

### Property 11: Admin detail endpoint always includes both file URLs

*For any* `IDVerification` record where both `selfie` and `id_document` are non-null, the admin detail response from `GET /api/accounts/admin/id-verifications/<id>/` SHALL include non-empty `selfie_url` and `id_document_url` fields.

**Validates: Requirements 9.14**

---

### Property 12: CRBCheck record always contains all required fields after creation

*For any* invocation of `CRBService.check()`, the resulting `CRBCheck` record persisted in the database SHALL have non-null values for `bureau_name` (may be empty string when not configured), `check_status`, `checked_at`, and a `raw_response` dict (may be empty `{}`).

**Validates: Requirements 5.2**

---

### Property 13: Active external loans count is extracted correctly from bureau responses

*For any* bureau response dict that contains a structured list of active loan facilities, `ActiveLoanExtractor.parse_active_loans()` SHALL return a count equal to the number of active facility entries in that list.

**Validates: Requirements 6.1**

---

### Property 14: Any positive active loan count triggers a flagged status

*For any* bureau response where the extracted active loan count is a positive integer N > 0, `CRBService.check()` SHALL set `CRBCheck.check_status` to `"flagged"` and `Loan.status` to `"flagged"`.

**Validates: Requirements 6.1, 6.2**
