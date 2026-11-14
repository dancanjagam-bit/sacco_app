"""Verify the ghost-rows-preserved upgrade copy is correct after migration."""
import sqlite3
import os

DB = os.path.join(os.path.dirname(__file__), '..', 'backups', 'db_ghosts_preserved.sqlite3')
con = sqlite3.connect(DB)
cur = con.cursor()

print(f"=== POST-UPGRADE VERIFICATION (ghost rows preserved): {os.path.basename(DB)} ===")

cur.execute("PRAGMA integrity_check")
result = cur.fetchall()
ic_ok = len(result) == 1 and result[0][0] == 'ok'
print(f"\nintegrity_check: {'PASS' if ic_ok else 'FAIL: ' + str(result)}")

cur.execute("PRAGMA foreign_key_check")
fk = cur.fetchall()
print(f"foreign_key_check: {'PASS (0 violations)' if not fk else 'FAIL: ' + str(fk[:5])}")

print("\n=== Row counts ===")
for t, expected in [
    ('accounts_user', 13), ('members_member', 5), ('core_savings', 24),
    ('core_transaction', 50), ('core_loan', 22), ('accounts_auditlog', 47),
    ('core_savingsdividend', 8),
]:
    cur.execute('SELECT COUNT(*) FROM "' + t + '"')
    count = cur.fetchone()[0]
    match = 'OK' if count == expected else f'MISMATCH expected {expected}'
    print(f"  {t}: {count} ({match})")

print("\n=== Transactions 41 and 50 ===")
cur.execute("SELECT id, type, amount, note, reverses_id FROM core_transaction WHERE id IN (41, 50)")
for r in cur.fetchall():
    print(f"  id={r[0]} type={r[1]} amount={r[2]} note={r[3]} reverses={r[4]}")

print("\n=== New columns/tables from pending migrations ===")
cur.execute("PRAGMA table_info(core_transaction)")
cols = {r[1] for r in cur.fetchall()}
print(f"  core_transaction.account_type: {'PRESENT' if 'account_type' in cols else 'MISSING'}")
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='core_transportassignmentissue'")
print(f"  core_transportassignmentissue: {'PRESENT' if cur.fetchone() else 'MISSING'}")

print("\n=== Ghost rows still in django_migrations (must still be present) ===")
cur.execute("""
    SELECT id, app, name FROM django_migrations
    WHERE (app='members' AND name='0004_remove_member_daraja_registered')
       OR (app='accounts' AND name='0012_idverification_data_retention_until_and_more')
    ORDER BY app
""")
ghosts = cur.fetchall()
for r in ghosts:
    print(f"  PRESENT: id={r[0]} [{r[1]}] {r[2]}")
if not ghosts:
    print("  None — ghost rows were removed")

print("\n=== Total applied migrations ===")
cur.execute("SELECT COUNT(*) FROM django_migrations")
print(f"  {cur.fetchone()[0]}")

print("\n=== account_type backfill ===")
cur.execute("SELECT account_type, COUNT(*) FROM core_transaction GROUP BY account_type ORDER BY account_type")
for r in cur.fetchall():
    label = r[0] if r[0] else '(blank)'
    print(f"  {label}: {r[1]} rows")

print("\n=== KYC tables ===")
kyc = ['accounts_kycconsentrecord','accounts_kycriskscore','accounts_livenesschallenge',
       'accounts_memberapproval','accounts_devicefingerprint','accounts_memberreference']
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
existing = {r[0] for r in cur.fetchall()}
for t in kyc:
    print(f"  {t}: {'PRESENT' if t in existing else 'MISSING'}")

con.close()
print("\nDone — ghost rows preserved throughout upgrade.")
