"""Inspect actual database state: users, roles, workspace snapshots."""
import os
import django

os.environ["DJANGO_SETTINGS_MODULE"] = "sacco.settings"
os.environ["USE_POSTGRES"] = "0"
django.setup()

from django.contrib.auth import get_user_model
from accounts.models import StaffRoleGrant, StaffProfile
from accounts.access import access_snapshot
from core.transport_models import TransportRole

User = get_user_model()

print("=== ALL USERS ===")
for u in User.objects.all().order_by("id"):
    print(
        "id={} username={} is_member={} is_staff={} is_superuser={} is_active={}".format(
            u.id, u.username, getattr(u, "is_member", None),
            u.is_staff, u.is_superuser, u.is_active,
        )
    )

print("\n=== STAFF PROFILES ===")
for p in StaffProfile.objects.all():
    print("user={} role={} status={}".format(p.user.username, p.role, p.status))

print("\n=== STAFF ROLE GRANTS ===")
try:
    for g in StaffRoleGrant.objects.all():
        print(
            "user={} role={} active={} granted_by={}".format(
                g.user.username, g.role, g.active, g.granted_by.username
            )
        )
except Exception as e:
    print("Error: {}".format(e))

print("\n=== TRANSPORT ROLES ===")
for r in TransportRole.objects.all():
    print("user={} role={} active={}".format(r.user.username, r.role, r.active))

print("\n=== ACCESS SNAPSHOTS (non-trivial) ===")
for u in User.objects.filter(is_active=True).order_by("id"):
    snap = access_snapshot(u)
    ws_ids = [w["id"] for w in snap["workspaces"]]
    if ws_ids:
        print(
            "{}: workspaces={} roles={} permissions={}".format(
                u.username, ws_ids, snap.get("staff_roles", []),
                snap["permissions"],
            )
        )

print("\n=== MIGRATION STATE ===")
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute("SELECT app, name, applied FROM django_migrations WHERE app IN ('accounts','accounting','members') ORDER BY app, id")
    for row in cursor.fetchall():
        print("{} {} applied={}".format(row[0], row[1], row[2]))

print("\n=== WELFARE TABLES CHECK ===")
with connection.cursor() as cursor:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'accounts_welfare%' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]
    print("Welfare tables in DB: {}".format(tables if tables else "NONE"))

print("\n=== MEETINGS/NOTICES TABLES CHECK ===")
with connection.cursor() as cursor:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('accounts_cooperativemeeting','accounts_membernotice') ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]
    print("Meeting/notice tables in DB: {}".format(tables if tables else "NONE"))
