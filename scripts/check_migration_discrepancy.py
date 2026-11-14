"""Detailed check of migration records vs actual table schema."""
import sqlite3
import os

BASE = r"c:\Users\USER\sacco_app"

# Check main db
db_path = os.path.join(BASE, "db.sqlite3")
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("=== django_migrations records for accounts ===")
c.execute("SELECT id, app, name, applied FROM django_migrations WHERE app='accounts' ORDER BY id")
for row in c.fetchall():
    print("  id={} app={} name={} applied={}".format(*row))

print("\n=== All welfare-related tables ===")
c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'accounts_welfare%' ORDER BY name")
for row in c.fetchall():
    print("  {}".format(row[0]))

print("\n=== WelfareRequest columns ===")
c.execute("PRAGMA table_info(accounts_welfarerequest)")
for row in c.fetchall():
    print("  {} {} {}".format(row[1], row[2], row[3]))

print("\n=== WelfarePolicy columns ===")
c.execute("PRAGMA table_info(accounts_welfarepolicy)")
for row in c.fetchall():
    print("  {} {}".format(row[1], row[2]))

print("\n=== Meeting/Notice tables ===")
c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('accounts_cooperativemeeting','accounts_membernotice') ORDER BY name")
for row in c.fetchall():
    print("  {}".format(row[0]))

print("\n=== StaffRoleGrant role column ===")
c.execute("PRAGMA table_info(accounts_staffrolegrant)")
for row in c.fetchall():
    if row[1] == 'role':
        print("  Found role column: type={}".format(row[2]))

# Check the pre-welfare backup
print("\n=== Pre-welfare backup comparison ===")
backup_path = os.path.join(BASE, ".recovery", "pre-welfare-migration-backup.sqlite3")
if os.path.exists(backup_path):
    conn2 = sqlite3.connect(backup_path)
    c2 = conn2.cursor()
    c2.execute("SELECT id, app, name, applied FROM django_migrations WHERE app='accounts' ORDER BY id")
    for row in c2.fetchall():
        print("  backup: id={} name={} applied={}".format(row[0], row[2], row[3]))
    c2.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'accounts_welfare%'")
    wt = [r[0] for r in c2.fetchall()]
    print("  backup welfare_tables={}".format(wt))
    conn2.close()

# Check the verification DBs that have 0018
print("\n=== Verification configured-copy DB ===")
vdb = os.path.join(BASE, ".recovery", "transport-acceptance", "verification-c33f63ee3a474680ac21342f954951e7", "configured-copy.sqlite3")
if os.path.exists(vdb):
    conn3 = sqlite3.connect(vdb)
    c3 = conn3.cursor()
    c3.execute("SELECT id, app, name, applied FROM django_migrations WHERE app='accounts' AND name LIKE '0018%' OR name LIKE '0019%' ORDER BY id")
    for row in c3.fetchall():
        print("  vdb: id={} name={} applied={}".format(row[0], row[2], row[3]))
    c3.execute("PRAGMA table_info(accounts_welfarerequest)")
    cols = [row[1] for row in c3.fetchall()]
    print("  vdb WelfareRequest columns: {}".format(cols))
    conn3.close()

conn.close()
