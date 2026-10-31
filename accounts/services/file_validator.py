# accounts/services/file_validator.py
import logging
from django.core.exceptions import ValidationError
from django.conf import settings

logger = logging.getLogger(__name__)

ID_DOC_ALLOWED_MIME = {"image/jpeg", "image/png", "image/gif", "application/pdf"}
SELFIE_ALLOWED_MIME = {"image/jpeg", "image/png", "image/gif"}


def _detect_mime(file):
    """Detect MIME type from file bytes (not Content-Type header)."""
    buf = file.read(2048)
    file.seek(0)

    # Primary: python-magic (most reliable — reads magic bytes)
    try:
        import magic
        return magic.from_buffer(buf, mime=True)
    except ImportError:
        pass

    # Fallback 1: check known magic bytes manually
    # PDF
    if buf[:4] == b"%PDF":
        return "application/pdf"
    # JPEG
    if buf[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    # PNG
    if buf[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    # GIF87a / GIF89a
    if buf[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"

    # Fallback 2: imghdr (deprecated in 3.11, removed in 3.13 — try anyway)
    try:
        import imghdr
        img_type = imghdr.what(None, h=buf)
        if img_type:
            return f"image/{img_type}"
    except (ImportError, AttributeError):
        pass

    return "application/octet-stream"


def _get_max_bytes():
    max_mb = getattr(settings, "ID_DOC_MAX_MB", 5)
    return int(max_mb) * 1024 * 1024


def validate_id_document(file) -> None:
    """Raise ValidationError if file MIME type or size is invalid for an ID document."""
    mime = _detect_mime(file)
    if mime not in ID_DOC_ALLOWED_MIME:
        raise ValidationError(
            f"Unsupported file type '{mime}'. Please upload a JPEG, PNG, GIF, or PDF."
        )
    max_bytes = _get_max_bytes()
    if file.size > max_bytes:
        raise ValidationError(
            f"ID document exceeds the {getattr(settings, 'ID_DOC_MAX_MB', 5)} MB size limit."
        )


def validate_selfie(file) -> None:
    """Raise ValidationError if selfie MIME type is invalid (PDF not allowed) or too large."""
    mime = _detect_mime(file)
    if mime not in SELFIE_ALLOWED_MIME:
        raise ValidationError(
            f"Unsupported file type '{mime}'. Please upload a JPEG, PNG, or GIF selfie."
        )
    max_bytes = _get_max_bytes()
    if file.size > max_bytes:
        raise ValidationError(
            f"Selfie exceeds the {getattr(settings, 'ID_DOC_MAX_MB', 5)} MB size limit."
        )
