from datetime import timedelta
from decimal import Decimal
import uuid

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import AuditLog, StaffProfile
from .transport_models import TransportRole, TransportRoute, Vehicle, CrewAssignment, TransportCollection

User = get_user_model()


class TransportPhaseOneTests(APITestCase):
    def setUp(self):
        self.staff=User.objects.create_user(username="ops",password="pass",is_staff=True)
        StaffProfile.objects.create(user=self.staff,role="secretary")
        self.owner=User.objects.create_user(username="owner",password="pass")
        self.driver=User.objects.create_user(username="driver",password="pass",first_name="Test Driver")
        self.other=User.objects.create_user(username="other",password="pass")
        for u,r in ((self.owner,"owner"),(self.driver,"driver")):
            TransportRole.objects.create(user=u,role=r)
        self.route=TransportRoute.objects.create(name="Town - Market")
        self.vehicle=Vehicle.objects.create(registration="KAA 123A",owner=self.owner)
        self.assignment=CrewAssignment.objects.create(vehicle=self.vehicle,route=self.route,driver=self.driver,starts_at=timezone.now()-timedelta(hours=1),created_by=self.staff)

    def test_staff_can_create_assignment_and_historical_snapshot_persists(self):
        self.client.force_authenticate(self.staff)
        resp=self.client.post("/api/transport/assignments/",{"vehicle":self.vehicle.id,"route":self.route.id,"driver":self.driver.id,"starts_at":(timezone.now()+timedelta(days=1)).isoformat()},format="json")
        self.assertEqual(resp.status_code,409) # one open vehicle/driver assignment
        self.assignment.status="ended"; self.assignment.ends_at=timezone.now(); self.assignment.save()
        resp=self.client.post("/api/transport/assignments/",{"vehicle":self.vehicle.id,"route":self.route.id,"driver":self.driver.id,"starts_at":(timezone.now()+timedelta(days=1)).isoformat()},format="json")
        self.assertEqual(resp.status_code,201)
        self.route.name="Renamed route"; self.route.save()
        self.assertEqual(CrewAssignment.objects.get(pk=resp.data["id"]).route_label,"Town - Market")
        self.assertTrue(AuditLog.objects.filter(target__contains="Transport assignment").exists())

    def test_crew_scope_and_collection_idempotency(self):
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get("/api/transport/crew/today/").data["assignment"],None)
        self.client.force_authenticate(self.driver)
        self.assertEqual(self.client.get("/api/transport/crew/today/").data["assignment"]["id"],self.assignment.id)
        key=str(uuid.uuid4()); body={"assignment":self.assignment.id,"amount":"1250.50","notes":"Cash","client_key":key}
        one=self.client.post("/api/transport/crew/today/",body,format="json")
        two=self.client.post("/api/transport/crew/today/",body,format="json")
        self.assertEqual(one.status_code,201); self.assertEqual(two.status_code,200)
        self.assertTrue(two.data["duplicate"])
        self.assertEqual(TransportCollection.objects.count(),1)
        self.assertEqual(TransportCollection.objects.aggregate(total=__import__("django.db.models",fromlist=["Sum"]).Sum("amount"))["total"],Decimal("1250.50"))

    def test_collection_is_assignment_scoped(self):
        self.client.force_authenticate(self.other)
        response=self.client.post("/api/transport/crew/today/",{"assignment":self.assignment.id,"amount":"500","client_key":str(uuid.uuid4())},format="json")
        self.assertEqual(response.status_code,403)
        self.assertEqual(TransportCollection.objects.count(),0)

    def test_staff_role_assignment_endpoint_and_duplicate_key_conflict(self):
        self.client.force_authenticate(self.staff)
        response=self.client.post("/api/transport/roles/",{"user":self.other.id,"role":"driver"},format="json")
        self.assertEqual(response.status_code,201)
        self.assertTrue(TransportRole.objects.filter(user=self.other,role="driver",active=True).exists())
        self.client.force_authenticate(self.driver)
        key=str(uuid.uuid4()); body={"assignment":self.assignment.id,"amount":"100","notes":"one","client_key":key}
        self.assertEqual(self.client.post("/api/transport/crew/today/",body,format="json").status_code,201)
        body["amount"]="101"
        self.assertEqual(self.client.post("/api/transport/crew/today/",body,format="json").status_code,409)
        self.assertEqual(TransportCollection.objects.count(),1)

    def test_today_excludes_future_and_expired_assignments(self):
        now=timezone.now()
        self.assignment.starts_at=now+timedelta(hours=1); self.assignment.ends_at=now+timedelta(hours=2); self.assignment.status="scheduled"; self.assignment.save()
        self.client.force_authenticate(self.driver)
        self.assertIsNone(self.client.get("/api/transport/crew/today/").data["assignment"])
        self.assignment.starts_at=now-timedelta(hours=3); self.assignment.ends_at=now-timedelta(hours=1); self.assignment.status="ended"; self.assignment.save()
        self.assertIsNone(self.client.get("/api/transport/crew/today/").data["assignment"])

    def test_schedule_conflicts_rejected_and_non_overlapping_future_schedule_allowed(self):
        self.client.force_authenticate(self.staff)
        now=timezone.now()
        self.assignment.status="ended"; self.assignment.ends_at=now; self.assignment.save()
        body={"vehicle":self.vehicle.id,"route":self.route.id,"driver":self.driver.id,"starts_at":(now+timedelta(hours=1)).isoformat(),"ends_at":(now+timedelta(hours=3)).isoformat()}
        first=self.client.post("/api/transport/assignments/",body,format="json")
        self.assertEqual(first.status_code,201)
        conflict=dict(body); conflict["starts_at"]=(now+timedelta(hours=2)).isoformat(); conflict["ends_at"]=(now+timedelta(hours=4)).isoformat()
        self.assertEqual(self.client.post("/api/transport/assignments/",conflict,format="json").status_code,409)
        after=dict(body); after["starts_at"]=(now+timedelta(hours=4)).isoformat(); after["ends_at"]=(now+timedelta(hours=5)).isoformat()
        self.assertEqual(self.client.post("/api/transport/assignments/",after,format="json").status_code,201)

    def test_assignment_label_snapshots_survive_vehicle_route_and_crew_renames(self):
        self.vehicle.registration="KBB 999Z"; self.vehicle.save(); self.route.name="New route"; self.route.save(); self.driver.first_name="Changed"; self.driver.save()
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.vehicle_label,"KAA 123A")
        self.assertEqual(self.assignment.route_label,"Town - Market")
        self.assertEqual(self.assignment.driver_label,"Test Driver")
