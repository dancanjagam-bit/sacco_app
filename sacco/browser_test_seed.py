from datetime import date, timedelta
import os

from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import StaffProfile
from core.transport_models import CrewAssignment, TransportRole, TransportRoute, Vehicle
from members.models import Member

User = get_user_model()
test_password = os.environ.get("SACCO_BROWSER_TEST_PASSWORD")
if not test_password:
    raise RuntimeError("Set SACCO_BROWSER_TEST_PASSWORD to a local-only test password before seeding.")

member, _ = User.objects.get_or_create(
    username="browser_member",
    defaults={"first_name": "Test", "last_name": "Member", "email": "member@example.invalid"},
)
member.set_password(test_password)
member.save()
Member.objects.get_or_create(
    user=member,
    defaults={
        "member_number": "TEST-0001",
        "national_id": "TEST-NID-0001",
        "phone_number": "0700000001",
        "gender": "other",
        "date_of_birth": date(1990, 1, 1),
        "county": "Nairobi",
        "address": "Local browser verification only",
    },
)

admin, _ = User.objects.get_or_create(
    username="browser_admin",
    defaults={"first_name": "Test", "last_name": "Staff", "email": "admin@example.invalid", "is_staff": True},
)
admin.is_staff = True
admin.set_password(test_password)
admin.save()
StaffProfile.objects.get_or_create(user=admin, defaults={"role": "secretary", "status": "active"})

driver, _ = User.objects.get_or_create(
    username="browser_driver",
    defaults={"first_name": "Test", "last_name": "Driver"},
)
driver.set_password(test_password)
driver.save()
TransportRole.objects.get_or_create(user=driver, role="driver")
route, _ = TransportRoute.objects.get_or_create(name="Browser Test Route")
vehicle, _ = Vehicle.objects.get_or_create(registration="TEST 001", defaults={"owner": admin})
now = timezone.now()
CrewAssignment.objects.get_or_create(
    vehicle=vehicle,
    starts_at__date=timezone.localdate(),
    defaults={
        "route": route,
        "driver": driver,
        "starts_at": now - timedelta(hours=1),
        "ends_at": now + timedelta(hours=8),
        "status": "active",
        "created_by": admin,
    },
)
print("Created isolated browser test member, staff, driver, and assignment.")
