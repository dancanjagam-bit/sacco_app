"""Create repeatable, synthetic accounts for isolated browser acceptance."""
import os
from datetime import datetime, time, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.transport_models import CrewAssignment, TransportRole, TransportRoute, Vehicle
from members.models import Member


class Command(BaseCommand):
    help = "Create synthetic member, crew, owner, and staff accounts in acceptance_settings only."

    def handle(self, *args, **options):
        if settings.SETTINGS_MODULE != "sacco.acceptance_settings":
            raise CommandError("Use --settings=sacco.acceptance_settings; production settings are not accepted.")
        database = Path(settings.DATABASES["default"]["NAME"]).resolve()
        allowed = (settings.BASE_DIR / ".recovery" / "transport-acceptance").resolve()
        if not database.is_relative_to(allowed):
            raise CommandError("The synthetic database must be inside .recovery/transport-acceptance.")
        password = os.environ.get("SACCO_ACCEPTANCE_PASSWORD", "")
        if len(password) < 12:
            raise CommandError("Set SACCO_ACCEPTANCE_PASSWORD to a private test password of at least 12 characters.")

        User = get_user_model()
        definitions = [
            ("acceptance_member", "Test Member", "member", False, []),
            ("acceptance_driver", "Test Driver", "driver", False, ["driver"]),
            ("acceptance_conductor", "Test Conductor", "conductor", False, ["conductor"]),
            ("acceptance_owner", "Test Owner", "owner", False, ["owner"]),
            ("acceptance_staff", "Test Operations", "staff", True, []),
            ("acceptance_other", "Test Other Crew", "other", False, ["driver"]),
        ]
        users = {}
        with transaction.atomic():
            for index, (username, name, tag, is_manager, roles) in enumerate(definitions, start=1):
                user, _ = User.objects.get_or_create(username=username, defaults={"email": f"{username}@example.invalid"})
                user.first_name = name.split(" ", 1)[0]
                user.last_name = name.split(" ", 1)[1] if " " in name else ""
                user.email = f"{username}@example.invalid"
                user.is_active = True
                user.is_staff = is_manager
                user.is_superuser = is_manager
                user.is_admin = False
                user.is_member = not is_manager
                user.set_password(password)
                user.save()
                users[tag] = user

                if not is_manager:
                    Member.objects.update_or_create(
                        user=user,
                        defaults={
                            "member_number": f"TEST{index:06d}",
                            "national_id": f"SYNTH-{index:06d}",
                            "phone_number": f"254700000{index:03d}",
                            "gender": "other",
                            "date_of_birth": datetime(1990, 1, min(index, 28)).date(),
                            "county": "Synthetic test county",
                            "address": "Acceptance data only",
                            "status": "active",
                        },
                    )
                for role in roles:
                    TransportRole.objects.update_or_create(user=user, role=role, defaults={"active": True})

            route, _ = TransportRoute.objects.get_or_create(name="ACCEPTANCE · Town to Market", defaults={"origin": "Test Origin", "destination": "Test Market", "active": True})
            vehicle, _ = Vehicle.objects.get_or_create(registration="TEST-TR-001", defaults={"owner": users["owner"], "make_model": "Synthetic Tuk Tuk", "active": True})
            if vehicle.owner_id != users["owner"].id:
                vehicle.owner = users["owner"]
                vehicle.save(update_fields=["owner"])

            today = timezone.localdate()
            local_start = timezone.make_aware(datetime.combine(today, time.min), timezone.get_current_timezone())
            local_end = local_start + timedelta(days=1)
            CrewAssignment.objects.get_or_create(
                vehicle=vehicle,
                driver=users["driver"],
                starts_at=local_start,
                defaults={
                    "route": route,
                    "conductor": users["conductor"],
                    "ends_at": local_end,
                    "status": "active",
                    "created_by": users["staff"],
                },
            )
        self.stdout.write(self.style.SUCCESS("Synthetic acceptance users are ready. Password is the value you supplied locally."))
        for tag in ("member", "driver", "conductor", "owner", "staff", "other"):
            self.stdout.write(f"{tag}: {users[tag].username}")
