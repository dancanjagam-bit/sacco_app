"""
CRB Service
============
Orchestrates Credit Reference Bureau checks for loan applications.
"""
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


class ActiveLoanExtractor:
    @staticmethod
    def extract(raw_response: dict) -> list:
        if not raw_response or not isinstance(raw_response, dict):
            return []
        for key in ("active_facilities", "CreditFacilities", "active_loans", "loans"):
            loans = raw_response.get(key)
            if isinstance(loans, list):
                return loans
        data = raw_response.get("data", {})
        if isinstance(data, dict):
            for key in ("active_facilities", "CreditFacilities", "active_loans", "loans"):
                loans = data.get(key)
                if isinstance(loans, list):
                    return loans
        return []


class CRBService:
    def run_check(self, loan):
        from core.models import CRBCheck
        from core.services.crb_client import get_crb_client
        from accounts.models import AuditLog, Notification, StaffProfile

        member = loan.user
        national_id = ""
        try:
            national_id = member.id_verification.national_id
        except Exception:
            pass

        client = get_crb_client()
        provider_name = client.provider_name

        try:
            result = client.check(national_id)
        except Exception as exc:
            logger.error("CRB client.check raised: %s", exc)
            result = {"provider": provider_name, "score": None, "active_loans": [], "raw": {}, "error": str(exc)}

        error = result.get("error")
        raw_response = result.get("raw", {})
        score = result.get("score")
        active_loans_list = ActiveLoanExtractor.extract(raw_response) or result.get("active_loans", [])
        active_loans_count = len(active_loans_list)

        threshold = getattr(settings, "CRB_FLAG_SCORE_THRESHOLD", 500)
        flag_reason = ""

        if error and "not configured" in (error or "").lower():
            crb_status = "not_configured"
        elif error:
            crb_status = "error"
        elif active_loans_count > 0:
            crb_status = "flagged"
            creditors = [l.get("creditor", l.get("institution", "Unknown")) for l in active_loans_list]
            flag_reason = f"{active_loans_count} active external loan(s) at: " + ", ".join(creditors[:5])
        elif score is not None and score < threshold:
            crb_status = "flagged"
            flag_reason = f"Credit score {score} is below the minimum threshold of {threshold}."
        else:
            crb_status = "clear"

        crb_check = CRBCheck.objects.create(
            loan=loan,
            member=member,
            provider=provider_name,
            status=crb_status,
            score=score,
            active_loans_count=active_loans_count,
            raw_response=raw_response,
        )

        if crb_status == "flagged":
            loan.status = "flagged"
            loan.remarks = flag_reason
            loan.save(update_fields=["status", "remarks"])
            _send_flag_notifications(loan, member, flag_reason)

        AuditLog.log(
            actor=None,
            action="crb_check_run",
            target=f"Loan #{loan.pk}",
            details={"crb_check_id": crb_check.pk, "loan_id": loan.pk,
                     "bureau_name": provider_name, "check_status": crb_status},
        )
        if crb_status == "flagged":
            AuditLog.log(
                actor=None,
                action="loan_flagged",
                target=f"Loan #{loan.pk}",
                details={"loan_id": loan.pk, "crb_check_id": crb_check.pk, "flag_reason": flag_reason},
            )

        return crb_check


def _send_flag_notifications(loan, member, flag_reason: str):
    from accounts.models import Notification, StaffProfile
    Notification.send(
        user=member,
        title="Loan Application Under Review",
        message=f"Your loan application of KES {loan.amount:,} has been flagged. Reason: {flag_reason}.",
        ntype="warning",
    )
    for sp in StaffProfile.objects.filter(status="active", role__in=("loan_officer", "superadmin")).select_related("user"):
        Notification.send(
            user=sp.user,
            title="Flagged Loan Application Requires Review",
            message=f"Loan #{loan.pk} for {member.get_full_name() or member.username} flagged. Reason: {flag_reason}",
            ntype="warning",
        )
