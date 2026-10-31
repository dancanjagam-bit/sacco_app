import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def _get_threshold() -> int:
    return int(getattr(settings, "NAME_MATCH_THRESHOLD", 75))


def match_names(ocr_name: str, form_name: str) -> tuple[bool, float]:
    """
    Compare ocr_name against form_name using fuzzy token-set-ratio matching.

    Returns (matches, score) where:
      - matches is True when score >= NAME_MATCH_THRESHOLD
      - score is 0.0–100.0
    Returns (False, 0.0) when either input is empty or None.
    """
    if not ocr_name or not form_name:
        return False, 0.0

    try:
        from thefuzz import fuzz
    except ImportError:
        logger.error("thefuzz not installed — name matching unavailable; defaulting to mismatch")
        return False, 0.0

    normalised_ocr = " ".join(ocr_name.strip().lower().split())
    normalised_form = " ".join(form_name.strip().lower().split())

    if not normalised_ocr or not normalised_form:
        return False, 0.0

    score = float(fuzz.token_set_ratio(normalised_ocr, normalised_form))
    threshold = _get_threshold()
    return score >= threshold, score
