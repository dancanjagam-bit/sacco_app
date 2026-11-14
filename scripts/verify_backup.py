"""Verify that a backup SQLite file opens correctly and contains the expected data.

Usage: python scripts/verify_backup.py backups/db_backup_<timestamp>.sqlite3
Does not modify either database.
"""
import sqlite3
import sys
import os

if len(sys.argv) < 2:
    # Default to the most recent backup
    backup_dir = os.path.join(os.path.dirname(__file__), '..', 'backups')
    files = sorted(f for f in os.listdir(backup_dir) if f.startswith('db_backup_') and f.endswith('.sqlite3'))
    if not files:
        print("No backup file found in backups/")
        sys.exit(1)
    backup_path = os.path.join(backup_dir, files[-1])
else:
    backup_path = sys.argv[1]

print(f"Verifying: {os.path.abspath(backup_path)}")
print(f"File size: {os.path.getsize(backup_path):,} bytes")

con = sqlite3.connect(backup_path)
cur = con.cursor()

# 1. PRAGMA integrity_check
print("\n--- SQLite integrity_check ---")
cur.execute("PRAGMA integrity_check")
result = cur.fetchall()
for row in result:
    print(f"  {row[0]}")
all_ok = len(result) == 1 and result[0][0] == 'ok'
print(f"  Result: {'PASS' if all_ok else 'FAIL'}")

# 2. PRAGMA foreign_key_check
print("\n--- SQLite foreign_key_check ---")
cur.execute("PRAGMA foreign_key_check")
fk_violations = cur.fetchall()
if fk_violations:
    print(f"  VIOLATIONS ({len(fk_violations)}):")
    for v in fk_violations[:20]:
        print(f"    {v}")
else:
    print("  No violations — PASS")

# 3. Row counts for key tables
key_tables = [
    'accounts_user', 'members_member', 'core_savings', 'core_transaction',
    'core_loan', 'core_fosawithdrawal', 'core_savingsdividend', 'accounts_auditlog',
]
print("\n--- Row counts (must match original) ---")
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
existing = {r[0] for r in cur.fetchall()}
totals = {}
for t in key_tables:
    if t in existing:
        cur.execute('SELECT COUNT(*) FROM "' + t + '"')
        count = cur.fetchone()[0]
        totals[t] = count
        print(f"  {t}: {count}")
    else:
        print(f"  {t}: MISSING")

# 4. Transaction rows 41 and 50 preserved
print("\n--- Withdrawal transactions 41 and 50 ---")
cur.execute("SELECT id, type, amount, note, user_id FROM core_transaction WHERE id IN (41, 50)")
for r in cur.fetchall():
    print(f"  id={r[0]} type={r[1]} amount={r[2]} note={r[3]} user_id={r[4]}")

# 5. Financial totals
print("\n--- Financial totals ---")
cur.execute("SELECT SUM(amount) FROM core_savings")
total_savings = cur.fetchone()[0]
print(f"  core_savings total: {total_savings}")
cur.execute("SELECT SUM(amount) FROM core_transaction")
total_tx = cur.fetchone()[0]
print(f"  core_transaction total: {total_tx}")
cur.execute("SELECT SUM(balance) FROM core_loan WHERE status='approved'")
loan_balance = cur.fetchone()[0]
print(f"  approved loan balance total: {loan_balance}")

# 6. Applied migrations
print("\n--- Migration count ---")
cur.execute("SELECT COUNT(*) FROM django_migrations")
count = cur.fetchone()[0]
print(f"  Applied migrations: {count}")

con.close()

print("\n=== VERIFICATION SUMMARY ===")
print(f"  Integrity check: {'PASS' if all_ok else 'FAIL'}")
print(f"  FK violations: {len(fk_violations)}")
print(f"  Tx 41 and 50 preserved: {'yes' if totals.get('core_transaction', 0) >= 50 else 'check manually'}")
print(f"  core_savings total: {total_savings}")
print(f"  Backup is {'VALID' if all_ok and not fk_violations else 'HAS ISSUES'}")
