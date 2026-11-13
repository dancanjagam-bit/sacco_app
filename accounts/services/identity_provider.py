"""Identity provider boundary. Live verification is deliberately disabled until onboarding."""
from dataclasses import dataclass


@dataclass
class IdentityResult:
    status: str
    provider: str
    reference: str = ""
    reason_code: str = "provider_onboarding_required"


class IdentityProvider:
    provider_name = "base"
    def verify_kenya_national_id(self, *, national_id, first_name, last_name, date_of_birth, consent):
        raise NotImplementedError


class SandboxIdentityProvider(IdentityProvider):
    """Deterministic sandbox: always pending and never promotes a member to verified."""
    provider_name = "sandbox"
    def verify_kenya_national_id(self, *, national_id, first_name, last_name, date_of_birth, consent):
        return IdentityResult(status="provider_unavailable", provider=self.provider_name,
                              reason_code="sandbox_does_not_verify_identity")


def get_identity_provider():
    # No live provider endpoint/contract or approved credentials exist in settings.
    # Live verification remains blocked until provider onboarding is documented.
    return SandboxIdentityProvider()
