"""Second read-only inspection pass: anomalies, financial integrity, withdrawal detail."""
import sqlite3
import os

DB = os.path.join(os.path.dirname(__file__), '..', 'db.sqlite3')

con = sqlite3.connect(DB)
cur = con.cursor()

# 1. Full accounts_idverification columns - confirmed above, skip
# 2. Check for duplicate migration names (the two 0012 for accounts and two 0004 for members)
print("=== DUPLICATE MIGRATION NAMES IN django_migrations ===")
cur.execute("""
    SELECT app, name, COUNT(*) as cnt
    FROM django_migrations
    GROUP BY app, name
    HAVING cnt > 1
    ORDER BY app, name
""")
rows = cur.fetchall()
if rows:
    for r in rows:
        print(f"  DUPLICATE: [{r[0]}] {r[1]} appears {r[2]} times")
else:
    print("  None")

# 3. Full members.0004 situation
print("\n=== members migrations in django_migrations ===")
cur.execute("SELECT id, app, name, applied FROM django_migrations WHERE app='members' ORDER BY id")
for r in cur.fetchall():
    print(f"  id={r[0]} [{r[1]}] {r[2]} applied={r[3]}")

# 4. Full accounts.0012 situation
print("\n=== accounts 0011/0012 migrations in django_migrations ===")
cur.execute("SELECT id, app, name, applied FROM django_migrations WHERE app='accounts' AND name LIKE '001%' ORDER BY id")
for r in cur.fetchall():
    print(f"  id={r[0]} [{r[1]}] {r[2]} applied={r[3]}")

# 5. core_transaction: does account_type column exist?
print("\n=== core_transaction COLUMNS (full check) ===")
cur.execute("PRAGMA table_info(core_transaction)")
cols = {row[1]: row for row in cur.fetchall()}
for name, row in cols.items():
    print(f"  col {row[0]}: {row[1]} ({row[2]}) notnull={row[3]} default={row[4]}")
print(f"  'account_type' present: {'account_type' in cols}")
print(f"  'reverses_id' present: {'reverses_id' in cols}")

# 6. core_transportassignmentissue - confirm it is missing
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='core_transportassignmentissue'")
present = cur.fetchone()
print(f"\n=== core_transportassignmentissue table: {'EXISTS' if present else 'MISSING'} ===")

# 7. Transaction rows 41 and 50 full detail
print("\n=== FULL DETAIL: core_transaction rows 41 and 50 ===")
cur.execute("SELECT * FROM core_transaction WHERE id IN (41, 50)")
rows = cur.fetchall()
cur.execute("PRAGMA table_info(core_transaction)")
col_names = [c[1] for c in cur.fetchall()]
print("  Columns:", col_names)
for row in rows:
    print("  Row:", dict(zip(col_names, row)))

# 8. FosaWithdrawal table - all rows (there are 0, but confirm)
print("\n=== core_fosawithdrawal ALL ROWS ===")
cur.execute("SELECT COUNT(*) FROM core_fosawithdrawal")
count = cur.fetchone()[0]
print(f"  Total rows: {count}")

# 9. Check if the two transaction-41/50 user_ids match a member
print("\n=== USERS for transactions 41 and 50 ===")
cur.execute("SELECT t.id, t.type, t.amount, t.note, t.user_id, u.username FROM core_transaction t JOIN accounts_user u ON t.user_id = u.id WHERE t.id IN (41, 50)")
for r in cur.fetchall():
    print(f"  tx_id={r[0]} type={r[1]} amount={r[2]} note={r[3]} user_id={r[4]} username={r[5]}")

# 10. Financial summary: total savings, total transactions by type
print("\n=== SAVINGS TOTALS BY ACCOUNT TYPE ===")
cur.execute("SELECT account_type, COUNT(*), SUM(amount) FROM core_savings GROUP BY account_type")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]} rows, total={r[2]}")

print("\n=== TRANSACTION TOTALS BY TYPE ===")
cur.execute("SELECT type, COUNT(*), SUM(amount) FROM core_transaction GROUP BY type ORDER BY type")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]} rows, total={r[2]}")

# 11. Active loans summary
print("\n=== LOAN SUMMARY ===")
cur.execute("SELECT status, COUNT(*), SUM(amount), SUM(balance) FROM core_loan GROUP BY status ORDER BY status")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]} loans, sum_amount={r[2]}, sum_balance={r[3]}")

# 12. Members.0004 file: which name does the file on disk have?
print("\n=== members migration files on disk ===")
mig_dir = os.path.join(os.path.dirname(__file__), '..', 'members', 'migrations')
for f in sorted(os.listdir(mig_dir)):
    if f.endswith('.py') and not f.startswith('_'):
        print(f"  {f}")

# 13. accounts migration files on disk
print("\n=== accounts migration files on disk ===")
acc_dir = os.path.join(os.path.dirname(__file__), '..', 'accounts', 'migrations')
for f in sorted(os.listdir(acc_dir)):
    if f.endswith('.py') and not f.startswith('_'):
        print(f"  {f}")

# 14. core migration files on disk
print("\n=== core migration files on disk ===")
core_dir = os.path.join(os.path.dirname(__file__), '..', 'core', 'migrations')
for f in sorted(os.listdir(core_dir)):
    if f.endswith('.py') and not f.startswith('_'):
        print(f"  {f}")

con.close()
print("\nDone.")
