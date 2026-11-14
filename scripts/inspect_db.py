"""Read-only inspection of db.sqlite3 — tables, columns, and financial row counts."""
import sqlite3
import os

DB = os.path.join(os.path.dirname(__file__), '..', 'db.sqlite3')

con = sqlite3.connect(DB)
cur = con.cursor()

# 1. All tables
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall()]
print("=== TABLES ===")
for t in tables:
    print(" ", t)

# 2. Row counts for key financial and auth tables
key_tables = [
    'accounts_user', 'members_member', 'core_savings', 'core_transaction',
    'core_loan', 'core_loanguarantor', 'core_fosawithdrawal',
    'core_savingsdividend', 'core_mpesatransaction',
    'accounts_notification', 'accounts_auditlog',
    'core_crbcheck', 'core_assetcollateral', 'core_exitrequest',
    'core_saccosettings', 'core_auditfinding',
    'core_transportcollection', 'core_transportremittance',
    'core_transportpayment', 'core_transportassignmentissue',
    'accounts_idverification',
    'django_migrations',
]
print("\n=== ROW COUNTS ===")
for t in key_tables:
    if t in tables:
        cur.execute('SELECT COUNT(*) FROM "' + t + '"')
        print(f"  {t}: {cur.fetchone()[0]}")
    else:
        print(f"  {t}: TABLE MISSING")

# 3. Physical columns of core_transaction (check for reverses, account_type)
print("\n=== core_transaction COLUMNS ===")
if 'core_transaction' in tables:
    cur.execute("PRAGMA table_info(core_transaction)")
    for row in cur.fetchall():
        print(f"  col {row[0]}: {row[1]} ({row[2]})")

# 4. Physical columns of core_fosawithdrawal (check provider_reference length)
print("\n=== core_fosawithdrawal COLUMNS ===")
if 'core_fosawithdrawal' in tables:
    cur.execute("PRAGMA table_info(core_fosawithdrawal)")
    for row in cur.fetchall():
        print(f"  col {row[0]}: {row[1]} ({row[2]})")

# 5. Physical columns of accounts_idverification (check national_id_hash etc.)
print("\n=== accounts_idverification COLUMNS ===")
if 'accounts_idverification' in tables:
    cur.execute("PRAGMA table_info(accounts_idverification)")
    for row in cur.fetchall():
        print(f"  col {row[0]}: {row[1]} ({row[2]})")

# 6. Physical columns of accounts_otprequest (check attempt_count, delivery_status)
print("\n=== accounts_otprequest COLUMNS ===")
if 'accounts_otprequest' in tables:
    cur.execute("PRAGMA table_info(accounts_otprequest)")
    for row in cur.fetchall():
        print(f"  col {row[0]}: {row[1]} ({row[2]})")

# 7. Physical columns of accounts_auditlog (check action choices field type)
print("\n=== accounts_auditlog COLUMNS ===")
if 'accounts_auditlog' in tables:
    cur.execute("PRAGMA table_info(accounts_auditlog)")
    for row in cur.fetchall():
        print(f"  col {row[0]}: {row[1]} ({row[2]})")

# 8. Transport-related tables presence
transport_tables = [
    'core_transportrole', 'core_transportrolegrant', 'core_transportroute',
    'core_vehicle', 'core_vehicleownership', 'core_crewassignment',
    'core_transportshift', 'core_transportcollection',
    'core_transportremittance', 'core_transportpayment',
    'core_transportallocationrule', 'core_transportpaymentallocation',
    'core_transportassignmentissue',
]
print("\n=== TRANSPORT TABLES ===")
for t in transport_tables:
    status = "EXISTS" if t in tables else "MISSING"
    print(f"  {t}: {status}")

# 9. KYC tables (expected missing as 0013 not yet generated)
kyc_tables = [
    'accounts_kycconsentrecord', 'accounts_kycriskscore',
    'accounts_livenesschallenge', 'accounts_memberapproval',
    'accounts_devicefingerprint', 'accounts_memberreference',
]
print("\n=== KYC TABLES (expected absent) ===")
for t in kyc_tables:
    status = "EXISTS" if t in tables else "MISSING"
    print(f"  {t}: {status}")

# 10. Specific withdrawal rows 41 and 50
print("\n=== WITHDRAWAL ROWS 41 and 50 ===")
if 'core_transaction' in tables:
    cur.execute("SELECT id, type, amount, note, created_at FROM core_transaction WHERE id IN (41, 50)")
    rows = cur.fetchall()
    if rows:
        for r in rows:
            print(f"  id={r[0]} type={r[1]} amount={r[2]} note={r[3]} created_at={r[4]}")
    else:
        print("  No rows with id 41 or 50 found in core_transaction")

# 11. FosaWithdrawal rows 41 and 50 (they might be there instead)
if 'core_fosawithdrawal' in tables:
    cur.execute("SELECT id, status, amount, provider_reference, client_request_id FROM core_fosawithdrawal WHERE id IN (41, 50)")
    rows = cur.fetchall()
    if rows:
        for r in rows:
            print(f"  FosaWithdrawal id={r[0]} status={r[1]} amount={r[2]} provider_ref={r[3]} client_req={r[4]}")

# 12. SACCO settings row
print("\n=== SACCO SETTINGS ===")
if 'core_saccosettings' in tables:
    cur.execute("SELECT * FROM core_saccosettings LIMIT 1")
    row = cur.fetchone()
    if row:
        cur.execute("PRAGMA table_info(core_saccosettings)")
        cols = [c[1] for c in cur.fetchall()]
        for col, val in zip(cols, row):
            print(f"  {col}: {val}")
    else:
        print("  (no rows)")

# 13. Applied migration names
print("\n=== APPLIED MIGRATIONS (django_migrations) ===")
if 'django_migrations' in tables:
    cur.execute("SELECT app, name FROM django_migrations ORDER BY app, id")
    for r in cur.fetchall():
        print(f"  [{r[0]}] {r[1]}")

con.close()
print("\nDone — db.sqlite3 inspected read-only.")
