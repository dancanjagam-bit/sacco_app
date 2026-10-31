import logging
import os
from django.conf import settings

logger = logging.getLogger(__name__)

_STUB_RESPONSE = {
    "provider": "stub",
    "score": 750,
    "active_loans": [],
    "raw": {"stub": True, "message": "CRB stub — no real bureau configured"},
    "error": None,
}


class CRBClientBase:
    provider_name = "base"

    def check(self, national_id: str) -> dict:
        raise NotImplementedError


class TransUnionKenyaClient(CRBClientBase):
    provider_name = "transunion"
    BASE_URL = "https://api.transunion.co.ke/v1"

    def check(self, national_id: str) -> dict:
        try:
            import requests
            api_key = getattr(settings, "CRB_API_KEY", "") or os.getenv("CRB_API_KEY", "")
            api_url = getattr(settings, "CRB_API_URL", self.BASE_URL) or self.BASE_URL
            if not api_key:
                return {**_STUB_RESPONSE, "provider": self.provider_name,
                        "error": "CRB_API_KEY not configured"}
            resp = requests.get(
                f"{api_url}/credit-report",
                params={"national_id": national_id},
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=15,
            )
            resp.raise_for_status()
            raw = resp.json()
            return {
                "provider": self.provider_name,
                "score": raw.get("credit_score"),
                "active_loans": raw.get("active_facilities", []),
                "raw": raw,
                "error": None,
            }
        except Exception as exc:
            logger.error("TransUnion CRB check failed: %s", exc)
            return {
                "provider": self.provider_name,
                "score": None,
                "active_loans": [],
                "raw": {},
                "error": str(exc),
            }


class MetropolClient(CRBClientBase):
    provider_name = "metropol"
    BASE_URL = "https://api.metropol.co.ke/reference/v2"

    def check(self, national_id: str) -> dict:
        try:
            import requests
            api_key = getattr(settings, "CRB_API_KEY", "") or os.getenv("CRB_API_KEY", "")
            api_url = getattr(settings, "CRB_API_URL", self.BASE_URL) or self.BASE_URL
            if not api_key:
                return {**_STUB_RESPONSE, "provider": self.provider_name,
                        "error": "CRB_API_KEY not configured"}
            resp = requests.post(
                f"{api_url}/delisting/identity",
                json={"identity_number": national_id, "identity_type": "001"},
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                timeout=15,
            )
            resp.raise_for_status()
            raw = resp.json()
            return {
                "provider": self.provider_name,
                "score": raw.get("Score"),
                "active_loans": raw.get("CreditFacilities", []),
                "raw": raw,
                "error": None,
            }
        except Exception as exc:
            logger.error("Metropol CRB check failed: %s", exc)
            return {
                "provider": self.provider_name,
                "score": None,
                "active_loans": [],
                "raw": {},
                "error": str(exc),
            }


class StubCRBClient(CRBClientBase):
    provider_name = "stub"

    def check(self, national_id: str) -> dict:
        return {**_STUB_RESPONSE, "provider": "stub"}


def get_crb_client() -> CRBClientBase:
    """Return the configured CRB client based on CRB_PROVIDER env var."""
    provider = (getattr(settings, "CRB_PROVIDER", "") or os.getenv("CRB_PROVIDER", "")).lower()
    if provider == "transunion":
        return TransUnionKenyaClient()
    if provider == "metropol":
        return MetropolClient()
    return StubCRBClient()
