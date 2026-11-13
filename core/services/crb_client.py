"""Credit provider boundary. No undocumented endpoint is called from this app."""
import os
from django.conf import settings


class CRBClientBase:
    provider_name="unconfigured"
    def check(self, *, national_id, consent):
        raise NotImplementedError


class SandboxCRBClient(CRBClientBase):
    """No fixture looks like a real report; all unknown values remain null."""
    provider_name="sandbox"
    def check(self, *, national_id, consent):
        return {"provider":self.provider_name,"request_reference":"","report_date":None,
            "score":None,"external_obligations":None,"repayment_default_information":None,
            "missing_data":["provider_report","external_obligations","repayment_history"],
            "coverage_limitations":"Sandbox has no bureau data. No clean-credit conclusion is available.",
            "error":"Authorized bureau onboarding and credentials are required.","raw":{}}


def get_crb_client():
    provider=(getattr(settings,"CRB_PROVIDER","") or os.getenv("CRB_PROVIDER","")).lower()
    # Provider adapters are intentionally unavailable until a bureau-specific,
    # authorized integration contract and credentials have been configured.
    return SandboxCRBClient()
