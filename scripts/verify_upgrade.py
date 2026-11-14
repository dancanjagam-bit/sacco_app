"""Verify data integrity after upgrade migration on the test copy."""
import sqlite3
import os

UPGRADE = os.path.join(os.path.dirname(__file__), '..', 'backups', 'db_upgrade_test.sqlite3')

con = sqlite3.connect(UPGRADE)
cur = con.cursor()

print("=== POST-UPGRADE INTEGRITY CHECK ===")
cur.execute("PRAGMA integrity_check")
result = cur.fetchall()
ic_ok = len(result) == 1 and result[0][0] == 'ok'
print(f"  integrity_check: {'PASS' if ic_ok else 'FAIL - ' + str(result)}")

cur.execute("PRAGMA foreign_key_check")
fk = cur.fetchall()
print(f"  foreign_key_check: {'PASS (0 violations)' if not fk else 'FAIL - ' + str(fk[:5])}")

print("\n=== ROW COUNTS (must match backup) ===")
for t, expected in [
    ('accounts_user', 13), ('members_member', 5), ('core_savings', 24),
    ('core_transaction', 50), ('core_loan', 22), ('accounts_auditlog', 47),
    ('core_savingsdividend', 8),
]:
    cur.execute('SELECT COUNT(*) FROM "' + t + '"')
    count = cur.fetchone()[0]
    match = '✓' if count == expected else f'✗ expected {expected}'
    print(f"  {t}: {count} {match}")

print("\n=== TRANSACTION ROWS 41 AND 50 (must be unchanged) ===")
cur.execute("SELECT id, type, amount, note, reverses_id FROM core_transaction WHERE id IN (41, 50)")
for r in cur.fetchall():
    print(f"  id={r[0]} type={r[1]} amount={r[2]} note={r[3]} reverses_id={r[4]}")

print("\n=== FINANCIAL TOTALS ===")
cur.execute("SELECT SUM(amount) FROM core_savings")
print(f"  core_savings total: {cur.fetchone()[0]}")
cur.execute("SELECT SUM(balance) FROM core_loan WHERE status='approved'")
print(f"  approved loan balance total: {cur.fetchone()[0]}")

print("\n=== NEW COLUMNS ADDED BY MIGRATIONS ===")
# core_transaction.account_type (migration 0019)
cur.execute("PRAGMA table_info(core_transaction)")
cols = {r[1] for r in cur.fetchall()}
print(f"  core_transaction.account_type: {'PRESENT' if 'account_type' in cols else 'MISSING'}")
print(f"  core_transaction.reverses_id: {'PRESENT' if 'reverses_id' in cols else 'MISSING'}")

# core_transportassignmentissue (migration 0018)
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='core_transportassignmentissue'")
print(f"  core_transportassignmentissue table: {'PRESENT' if cur.fetchone() else 'MISSING'}")

# KYC tables adopted by accounts.0013
kyc = ['accounts_kycconsentrecord','accounts_kycriskscore','accounts_livenesschallenge',
       'accounts_memberapproval','accounts_devicefingerprint','accounts_memberreference']
print("\n=== KYC TABLES (adopted/created by 0013) ===")
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
existing = {r[0] for r in cur.fetchall()}
for t in kyc:
    print(f"  {t}: {'PRESENT' if t in existing else 'MISSING'}")

# account_type backfill
print("\n=== account_type BACKFILL (0019) ===")
cur.execute("SELECT account_type, COUNT(*) FROM core_transaction GROUP BY account_type ORDER BY account_type")
for r in cur.fetchall():
    label = r[0] if r[0] else '(blank/unclassified)'
    print(f"  account_type={label}: {r[1]} rows")

print("\n=== APPLIED MIGRATIONS ===")
cur.execute("SELECT COUNT(*) FROM django_migrations")
print(f"  Total applied: {cur.fetchone()[0]}")
cur.execute("SELECT app, name FROM django_migrations WHERE app IN ('accounts','core','members') ORDER BY app, id")
for r in cur.fetchall():
    print(f"  [{r[0]}] {r[1]}")

con.close()
print("\nUpgrade verification complete.")
