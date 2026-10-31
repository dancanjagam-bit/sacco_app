import logging
import os
import re

logger = logging.getLogger(__name__)

# ── Regex patterns for Kenyan National ID ──────────────────────────────────
_ID_NUMBER_RE = re.compile(r"\b(\d{7,8})\b")
_DOB_RE = re.compile(
    r"\b(\d{2}[./]\d{2}[./]\d{4}|\d{4}-\d{2}-\d{2})\b"
)
_NAME_CONTEXT_RE = re.compile(
    r"(?:NAME|JINA|FULL\s+NAME)[:\s]+([A-Z][A-Z\s]+)", re.IGNORECASE
)
_ALLCAPS_LINE_RE = re.compile(r"^[A-Z][A-Z\s]{4,}$")


def _parse_fields(raw_text: str) -> dict:
    """Extract id_number, full_name, dob from raw OCR text."""
    fields = {"id_number": None, "full_name": None, "dob": None}

    # ID number — first 7-8 digit sequence
    id_match = _ID_NUMBER_RE.search(raw_text)
    if id_match:
        fields["id_number"] = id_match.group(1)

    # DOB — first date-like token
    dob_match = _DOB_RE.search(raw_text)
    if dob_match:
        raw_dob = dob_match.group(1)
        # Normalise to YYYY-MM-DD if possible
        for sep in [".", "/"]:
            if sep in raw_dob:
                parts = raw_dob.split(sep)
                if len(parts) == 3:
                    d, m, y = parts
                    fields["dob"] = f"{y}-{m.zfill(2)}-{d.zfill(2)}"
                    break
        else:
            fields["dob"] = raw_dob  # already YYYY-MM-DD

    # Full name — prefer context near NAME/JINA keyword
    name_ctx = _NAME_CONTEXT_RE.search(raw_text)
    if name_ctx:
        fields["full_name"] = " ".join(name_ctx.group(1).split())
    else:
        # Fallback: first all-caps line of reasonable length
        for line in raw_text.splitlines():
            line = line.strip()
            if _ALLCAPS_LINE_RE.match(line) and 5 <= len(line) <= 60:
                fields["full_name"] = line
                break

    return fields


def extract_text_from_image(file_path: str) -> str:
    """Extract raw text from an image file using pytesseract."""
    try:
        from PIL import Image, ImageFilter, ImageEnhance
        import pytesseract

        img = Image.open(file_path).convert("L")  # grayscale
        img = ImageEnhance.Contrast(img).enhance(2.0)
        img = img.filter(ImageFilter.SHARPEN)
        text = pytesseract.image_to_string(img, config="--psm 6")
        return text
    except ImportError:
        logger.error("pytesseract or Pillow not installed — OCR unavailable")
        return ""
    except Exception as exc:
        logger.error("OCR image extraction failed: %s", exc)
        return ""


def extract_text_from_pdf(file_path: str) -> str:
    """Extract raw text from the first page of a PDF using pdfplumber."""
    try:
        import pdfplumber

        with pdfplumber.open(file_path) as pdf:
            if not pdf.pages:
                return ""
            return pdf.pages[0].extract_text() or ""
    except ImportError:
        logger.error("pdfplumber not installed — PDF OCR unavailable")
        return ""
    except Exception as exc:
        logger.error("OCR PDF extraction failed: %s", exc)
        return ""


def run_ocr(file_path: str) -> dict:
    """
    Dispatcher: detect file type, run appropriate extractor, parse fields.
    Returns {"raw_text": str, "fields": {"id_number", "full_name", "dob"}}.
    Never raises — returns empty fields on any failure.
    """
    try:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            raw_text = extract_text_from_pdf(file_path)
        else:
            raw_text = extract_text_from_image(file_path)

        fields = _parse_fields(raw_text) if raw_text.strip() else {
            "id_number": None, "full_name": None, "dob": None
        }
        return {"raw_text": raw_text, "fields": fields}
    except Exception as exc:
        logger.error("run_ocr failed for %s: %s", file_path, exc)
        return {"raw_text": "", "fields": {"id_number": None, "full_name": None, "dob": None}}
