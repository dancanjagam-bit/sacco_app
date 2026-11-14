"""Automated KYC risk decisions are intentionally unavailable.

The former weighted score treated missing inputs as negative evidence and
included automatic approve/reject outcomes. It is retained as an explicit
guard so an older caller cannot silently activate that policy. A future
assessment requires an approved, versioned policy and authorized review.
"""


class AutomatedKycAssessmentDisabled(RuntimeError):
    """Raised when code attempts to run the unapproved automated assessment."""


def compute_risk_score(verification):
    raise AutomatedKycAssessmentDisabled(
        "Automated KYC risk decisions are disabled pending an approved policy."
    )
