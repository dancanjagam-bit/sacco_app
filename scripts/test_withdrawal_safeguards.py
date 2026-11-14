"""
Isolated test: confirm every withdrawal and exit path that could write accounting
entries is blocked when no live payout provider is available.

Runs against an isolated in-memory database. Does not touch db.sqlite3 or any backup.
Does not send messages or initiate payments.
"""
import os
import sys
import django

os.environ["DJANGO_SETTINGS_MODULE"] = "sacco.browser_test_settings"
os.environ["SACCO_BROWSER_TEST_DB"] = ":memory:"

# Point Django at an in-memory DB for this test only
import django.conf
django.setup()

from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from decimal import Decimal

User = get_user_model()

# Run migrations on the in-memory test database
from django.test.utils import setup_test_environment
setup_test_environment()

from django.test.runner import DiscoverRunner
runner = DiscoverRunner(verbosity=0)
old_config = runner.setup_databases()

# ── Setup ──────────────────────────────────────────────────────────────────
from members.models import Member
from core.models import Savings, Transaction, FosaWithdrawal, Loan, ExitRequest, SACCOSettings
from accounts.models import AuditLog

User = get_user_model()

# Create a test user and member
user = User.objects.create_user(
    username="testwith", password="Testpass1!",
    first_name="Test", last_name="Withdraw",
    email="test@example.com",
)
member = Member.objects.create(
    user=user,
    member_number="TEST001",
    national_id="12345678",
    phone_number="0712345678",
    gender="male",
    date_of_birth="1990-01-01",
    county="Nairobi",
    address="123 Test St",
    status="active",
)

# Give them FOSA savings
Savings.objects.create(user=user, amount=Decimal("10000.00"), account_type="fosa")
# Give them BOSA savings
Savings.objects.create(user=user, amount=Decimal("5000.00"), account_type="bosa")

# Snapshot counts before tests
def snapshot():
    return {
        "savings": Savings.objects.filter(user=user).count(),
        "transactions": Transaction.objects.filter(user=user).count(),
        "fosa_withdrawals": FosaWithdrawal.objects.filter(user=user).count(),
    }

client = APIClient()
token = RefreshToken.for_user(user)
client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(token.access_token)}")

PASS = []
FAIL = []

def check(label, response, expected_status, should_have_no_financial_writes):
    before = snapshot() if should_have_no_financial_writes else None
    # (response already captured by caller)
    after = snapshot()
    status_ok = response.status_code == expected_status
    if should_have_no_financial_writes and before:
        writes = (after["savings"] - before["savings"]) + (after["transactions"] - before["transactions"]) + (after["fosa_withdrawals"] - before["fosa_withdrawals"])
        no_writes = writes == 0
    else:
        no_writes = True

    result = "PASS" if status_ok and no_writes else "FAIL"
    detail = f"status={response.status_code} (expected {expected_status})"
    if should_have_no_financial_writes:
        detail += f" | financial_writes={'YES (BAD)' if not no_writes else 'none (good)'}"
    print(f"  [{result}] {label}: {detail}")
    if 'code' in response.data or 'error' in response.data:
        print(f"         response={dict(response.data)}")
    (PASS if result == "PASS" else FAIL).append(label)

import uuid

print("\n=== WITHDRAWAL SAFEGUARD TESTS ===\n")

# Test 1: FOSA withdrawal with no provider — must return 503, no accounting writes
before = snapshot()
resp = client.post("/api/withdraw/", {
    "amount": "1000.00",
    "account_type": "fosa",
    "destination_type": "mpesa",
    "destination": "0712345678",
    "client_request_id": str(uuid.uuid4()),
}, format="json")
after = snapshot()
writes = (after["savings"] - before["savings"]) + (after["transactions"] - before["transactions"])
result = "PASS" if resp.status_code == 503 and writes == 0 else "FAIL"
print(f"  [{result}] FOSA withdrawal, no provider: status={resp.status_code} (expect 503) | financial_writes={writes} (expect 0)")
if hasattr(resp, 'data'):
    print(f"         code={resp.data.get('code','?')} error={resp.data.get('error','?')[:80]}")
(PASS if result == "PASS" else FAIL).append("FOSA withdrawal no provider")

# Test 2: BOSA withdrawal with no exit request — must return 400, no accounting writes
before = snapshot()
resp = client.post("/api/withdraw/", {
    "amount": "5000.00",
    "account_type": "bosa",
}, format="json")
after = snapshot()
writes = (after["savings"] - before["savings"]) + (after["transactions"] - before["transactions"])
result = "PASS" if resp.status_code == 400 and writes == 0 else "FAIL"
print(f"  [{result}] BOSA withdrawal no exit request: status={resp.status_code} (expect 400) | writes={writes} (expect 0)")
if hasattr(resp, 'data') and 'error' in resp.data:
    print(f"         error={resp.data['error'][:80]}")
(PASS if result == "PASS" else FAIL).append("BOSA no exit request")

# Test 3: BOSA withdrawal with pending exit request — must return 400, no writes
exit_req = ExitRequest.objects.create(user=user, reason="Relocating", status="pending")
before = snapshot()
resp = client.post("/api/withdraw/", {
    "amount": "5000.00",
    "account_type": "bosa",
}, format="json")
after = snapshot()
writes = (after["savings"] - before["savings"]) + (after["transactions"] - before["transactions"])
result = "PASS" if resp.status_code == 400 and writes == 0 else "FAIL"
print(f"  [{result}] BOSA withdrawal pending exit: status={resp.status_code} (expect 400) | writes={writes} (expect 0)")
if hasattr(resp, 'data') and 'error' in resp.data:
    print(f"         error={resp.data['error'][:80]}")
(PASS if result == "PASS" else FAIL).append("BOSA pending exit")

# Test 4: BOSA withdrawal with approved exit but holding period NOT over — must return 400
from django.utils import timezone
exit_req.status = "approved"
exit_req.approved_at = timezone.now()  # just approved — holding period not over
exit_req.save()
before = snapshot()
resp = client.post("/api/withdraw/", {
    "amount": "5000.00",
    "account_type": "bosa",
}, format="json")
after = snapshot()
writes = (after["savings"] - before["savings"]) + (after["transactions"] - before["transactions"])
result = "PASS" if resp.status_code in (400, 503) and writes == 0 else "FAIL"
print(f"  [{result}] BOSA withdrawal approved exit, hold not over: status={resp.status_code} (expect 400 or 503) | writes={writes} (expect 0)")
if hasattr(resp, 'data') and 'error' in resp.data:
    print(f"         error={resp.data['error'][:80]}")
(PASS if result == "PASS" else FAIL).append("BOSA exit hold not over")

# Test 5: BOSA exit with approved exit, holding period OVER, no active loans,
#         but NO payout provider — must return 503, NO accounting writes
from datetime import timedelta
settings_obj = SACCOSettings.get_settings()
hold_days = settings_obj.bosa_exit_hold_days if settings_obj else 60
exit_req.approved_at = timezone.now() - timedelta(days=hold_days + 1)
exit_req.save()
before = snapshot()
resp = client.post("/api/withdraw/", {
    "amount": "5000.00",
    "account_type": "bosa",
}, format="json")
after = snapshot()
writes = (after["savings"] - before["savings"]) + (after["transactions"] - before["transactions"])
result = "PASS" if resp.status_code == 503 and writes == 0 else "FAIL"
print(f"  [{result}] BOSA exit approved+hold over, no provider: status={resp.status_code} (expect 503) | writes={writes} (expect 0)")
if hasattr(resp, 'data'):
    print(f"         code={resp.data.get('code','?')} error={str(resp.data.get('error','?'))[:80]}")
(PASS if result == "PASS" else FAIL).append("BOSA exit approved hold over no provider")

print(f"\n=== RESULTS: {len(PASS)} PASS, {len(FAIL)} FAIL ===")
if FAIL:
    print("FAILED:")
    for f in FAIL:
        print(f"  - {f}")
else:
    print("All safeguard tests passed.")

runner.teardown_databases(old_config)
sys.exit(0 if not FAIL else 1)
