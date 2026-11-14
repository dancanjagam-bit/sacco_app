"""Seed separate synthetic users for role/workspace acceptance in an isolated DB."""
import os
from datetime import timedelta
from pathlib import Path
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import MemberApproval, StaffDutyAssignment, StaffRoleGrant
from core.models import Loan
from core.transport_models import (
    CrewAssignment, TransportAssignmentIssue, TransportCollection,
    TransportPayment, TransportRemittance, TransportRole, TransportRoute, Vehicle,
)
from members.models import Member


class Command(BaseCommand):
    help = "Create synthetic workspaces in .recovery/workspace-acceptance only."

    def handle(self, *args, **options):
        if "acceptance_settings" not in getattr(settings, "SETTINGS_MODULE", ""):
            raise CommandError("Use --settings=sacco.acceptance_settings. This command cannot run under normal application settings.")
        database = Path(settings.DATABASES["default"]["NAME"]).resolve()
        allowed = (Path(settings.BASE_DIR) / ".recovery" / "workspace-acceptance").resolve()
        try:
            database.relative_to(allowed)
        except ValueError as exc:
            raise CommandError("Workspace demo database must be inside .recovery/workspace-acceptance.") from exc
        password = os.environ.get("SACCO_ACCEPTANCE_PASSWORD", "")
        if len(password) < 12:
            raise CommandError("Set SACCO_ACCEPTANCE_PASSWORD locally to a private synthetic password of at least 12 characters.")

        User = get_user_model()
        definitions = {
            "member": ("Workspace Demo Member", True, False),
            "driver": ("Workspace Demo Driver", True, False),
            "conductor": ("Workspace Demo Conductor", True, False),
            "owner": ("Workspace Demo Owner", True, False),
            "multi": ("Workspace Demo Multi Role", True, False),
            "clerk": ("Workspace Demo Clerk", False, False),
            "credit": ("Workspace Demo Credit Officer", False, False),
            "treasurer": ("Workspace Demo Treasurer", False, False),
            "secretary": ("Workspace Demo Secretary", False, False),
            "chairman": ("Workspace Demo Chairman", False, False),
            "welfare": ("Workspace Demo Welfare Officer", True, False),
            "manager": ("Workspace Demo System Admin", False, True),
        }
        users = {}
        with transaction.atomic():
            for slug, (name, is_member, is_superuser) in definitions.items():
                username = f"ws_demo_{slug}"
                user, _ = User.objects.get_or_create(username=username)
                user.first_name, user.last_name = name.split(" ", 2)[-2:]
                user.email = f"{username}@example.invalid"
                user.recovery_email = ""
                user.recovery_phone = ""
                user.recovery_email_verified = False
                user.recovery_phone_verified = False
                user.is_active = True
                user.is_staff = is_superuser
                user.is_superuser = is_superuser
                user.is_admin = False
                user.is_member = is_member
                user.set_password(password)
                user.save()
                users[slug] = user
                if is_member:
                    member_number = f"WSD{list(definitions).index(slug)+1:06d}"
                    Member.objects.update_or_create(user=user, defaults={
                        "member_number": member_number,
                        "national_id": f"SYNTH-WSD-{list(definitions).index(slug)+1:04d}",
                        "phone_number": f"254711000{list(definitions).index(slug)+1:03d}",
                        "gender": "other", "date_of_birth": "1990-01-01",
                        "county": "Synthetic test county", "address": "Acceptance fixture only",
                        "status": "active",
                    })

            staff_role_for = {
                "clerk": ("clerk", users["clerk"]),
                "credit_officer": ("credit_officer", users["credit"]),
                "treasurer": ("treasurer", users["treasurer"]),
                "secretary": ("secretary", users["secretary"]),
                "chairman": ("chairman", users["chairman"]),
                "welfare_officer": ("welfare_officer", users["welfare"]),
            }
            for role, user in staff_role_for.values():
                StaffRoleGrant.objects.update_or_create(
                    user=user, role=role,
                    defaults={"active": True, "granted_by": users["manager"], "revoked_by": None, "revoked_at": None, "reason": "Synthetic workspace acceptance account."},
                )

            # Multi-role account: member + driver + owner transport roles AND welfare_officer staff role.
            for role in ("welfare_officer", "secretary"):
                StaffRoleGrant.objects.update_or_create(
                    user=users["multi"], role=role,
                    defaults={"active": True, "granted_by": users["manager"], "revoked_by": None, "revoked_at": None, "reason": "Synthetic multi-role acceptance account."},
                )

            for user, role in ((users["driver"], "driver"), (users["conductor"], "conductor"), (users["owner"], "owner"),
                               (users["multi"], "driver"), (users["multi"], "owner")):
                TransportRole.objects.update_or_create(user=user, role=role, defaults={"active": True})

            route, _ = TransportRoute.objects.get_or_create(
                name="WORKSPACE DEMO · Town to Market",
                defaults={"origin": "Synthetic origin", "destination": "Synthetic destination", "active": True},
            )
            owner_vehicle, _ = Vehicle.objects.get_or_create(
                registration="WS-DEMO-001",
                defaults={"owner": users["owner"], "make_model": "Synthetic tuk tuk", "active": True},
            )
            owner_vehicle_two, _ = Vehicle.objects.get_or_create(
                registration="WS-DEMO-002",
                defaults={"owner": users["owner"], "make_model": "Synthetic tuk tuk", "active": True},
            )
            multi_vehicle, _ = Vehicle.objects.get_or_create(
                registration="WS-DEMO-003",
                defaults={"owner": users["multi"], "make_model": "Synthetic tuk tuk", "active": True},
            )
            for vehicle, owner in ((owner_vehicle, users["owner"]), (owner_vehicle_two, users["owner"]), (multi_vehicle, users["multi"])):
                if vehicle.owner_id != owner.id:
                    vehicle.owner = owner
                    vehicle.save(update_fields=["owner"])

            now = timezone.localtime()
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
            driver_assignment, _ = CrewAssignment.objects.get_or_create(
                vehicle=owner_vehicle, driver=users["driver"], starts_at=start,
                defaults={"route": route, "conductor": None, "ends_at": end, "status": "active", "created_by": users["manager"]},
            )
            multi_assignment, _ = CrewAssignment.objects.get_or_create(
                vehicle=multi_vehicle, driver=users["multi"], starts_at=start,
                defaults={"route": route, "conductor": None, "ends_at": end, "status": "active", "created_by": users["manager"]},
            )
            issue, _ = TransportAssignmentIssue.objects.get_or_create(
                reported_by=users["driver"], assignment=driver_assignment,
                message="Synthetic acceptance issue: verify today’s route assignment.",
                defaults={"status": "pending"},
            )
            TransportCollection.objects.get_or_create(
                recorded_by=users["driver"], client_key=uuid.UUID("a034d983-69b3-4fc4-bf63-8f865ef8c001"),
                defaults={"assignment": driver_assignment, "amount": "250.00", "notes": "Synthetic acceptance collection."},
            )
            remittance, _ = TransportRemittance.objects.get_or_create(
                requested_by=users["driver"], idempotency_key=uuid.UUID("a034d983-69b3-4fc4-bf63-8f865ef8c002"),
                defaults={"payer": users["driver"], "assignment": driver_assignment, "shift": driver_assignment.shift,
                          "vehicle": owner_vehicle, "route": route, "amount": "250.00", "status": "pending"},
            )
            TransportPayment.objects.get_or_create(
                requested_by=users["driver"], idempotency_key=uuid.UUID("a034d983-69b3-4fc4-bf63-8f865ef8c003"),
                defaults={"remittance": remittance, "payer": users["driver"], "method": "cash", "status": "pending", "amount": "250.00"},
            )

            loan, _ = Loan.objects.get_or_create(
                user=users["member"], status="pending", amount="10000.00",
                defaults={"purpose": "business", "interest": "10.00", "repayment_months": 6, "balance": "0.00"},
            )
            self._duty(users["clerk"], users["manager"], "transport_assignment", {"vehicle": owner_vehicle}, "Synthetic clerk vehicle scope.")
            self._duty(users["clerk"], users["manager"], "cash_handover", {"crew_assignment": driver_assignment}, "Synthetic clerk cash-count scope.")
            self._duty(users["clerk"], users["manager"], "transport_issue", {"transport_issue": issue}, "Synthetic clerk issue-review scope.")
            self._duty(users["credit"], users["manager"], "loan_appraisal", {"loan": loan}, "Synthetic assigned appraisal.")
            self._duty(users["chairman"], users["manager"], "loan_approval", {"loan": loan}, "Synthetic assigned decision.")
            MemberApproval.objects.get_or_create(applicant=users["member"], stage="secretary_review", decision="pending")

            # ── Welfare module synthetic data ──────────────────────────────────
            from accounts.welfare_models import WelfarePolicy, WelfareRequest
            WelfarePolicy.objects.update_or_create(
                version="ws-demo-v1",
                defaults={
                    "approval_reference": "Synthetic AGM minute 2026-01-15",
                    "approved_by": users["manager"],
                    "active": True,
                    "benefits": {
                        "medical": {"maximum_benefit": "50000.00", "minimum_contributions": "2000.00"},
                        "funeral": {"maximum_benefit": "30000.00", "minimum_contributions": "1000.00"},
                        "education": {"maximum_benefit": "20000.00", "minimum_contributions": "5000.00"},
                    },
                },
            )
            # Member welfare request for officer to review.
            member_obj = Member.objects.filter(user=users["member"]).first()
            if member_obj:
                WelfareRequest.objects.update_or_create(
                    member=member_obj, category="medical", status="submitted",
                    defaults={
                        "description": "Synthetic welfare request for acceptance testing.",
                        "requested_amount": "10000.00",
                    },
                )

        self.stdout.write(self.style.SUCCESS("Synthetic role workspaces are ready in the isolated workspace acceptance database."))
        self.stdout.write("Login names: ws_demo_member, ws_demo_driver, ws_demo_conductor, ws_demo_owner, ws_demo_multi, ws_demo_clerk, ws_demo_credit, ws_demo_treasurer, ws_demo_secretary, ws_demo_chairman, ws_demo_welfare, ws_demo_manager")
        self.stdout.write("All accounts use only the private password supplied in SACCO_ACCEPTANCE_PASSWORD; no real member was modified.")

    @staticmethod
    def _duty(user, actor, duty, scope, reason):
        query = {"staff": user, "duty": duty, **{f"{key}_id": value.pk for key, value in scope.items()}, "active": True}
        StaffDutyAssignment.objects.update_or_create(**query, defaults={
            "assigned_by": actor, "starts_at": timezone.now(), "ends_at": None, "reason": reason,
        })
