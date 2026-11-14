"""Confirm what is actually in db.sqlite3 django_migrations — read-only."""
import sqlite3
import os

DB = os.path.join(os.path.dirname(__file__), '..', 'db.sqlite3')
con = sqlite3.connect(DB)
cur = con.cursor()

print("=== db.sqlite3 migration history rows — members 0004* and accounts 0012* ===")
cur.execute("""
    SELECT id, app, name, applied
    FROM django_migrations
    WHERE (app='members' AND name LIKE '0004%')
       OR (app='accounts' AND name LIKE '0012%')
    ORDER BY app, id
""")
for r in cur.fetchall():
    print(f"  id={r[0]} [{r[1]}] {r[2]} applied={r[3]}")

print("\n=== All pending migrations as Django sees them ===")
# We can't run showmigrations from Python directly, but we can compare
# disk files vs django_migrations rows for accounts and members
disk_accounts = []
acc_dir = os.path.join(os.path.dirname(__file__), '..', 'accounts', 'migrations')
for f in sorted(os.listdir(acc_dir)):
    if f.endswith('.py') and not f.startswith('_'):
        disk_accounts.append(f[:-3])  # strip .py

cur.execute("SELECT name FROM django_migrations WHERE app='accounts' ORDER BY id")
applied_accounts = {r[0] for r in cur.fetchall()}

print("  accounts migrations on disk vs applied:")
for m in disk_accounts:
    status = "[X]" if m in applied_accounts else "[ ]"
    print(f"    {status} {m}")

disk_members = []
mem_dir = os.path.join(os.path.dirname(__file__), '..', 'members', 'migrations')
for f in sorted(os.listdir(mem_dir)):
    if f.endswith('.py') and not f.startswith('_'):
        disk_members.append(f[:-3])

cur.execute("SELECT name FROM django_migrations WHERE app='members' ORDER BY id")
applied_members = {r[0] for r in cur.fetchall()}

print("  members migrations on disk vs applied:")
for m in disk_members:
    status = "[X]" if m in applied_members else "[ ]"
    print(f"    {status} {m}")

# Applied rows without a file on disk
print("\n=== Applied rows with no matching file on disk (ghost check) ===")
applied_no_file = []
for name in applied_accounts:
    if name + '.py' not in os.listdir(acc_dir):
        applied_no_file.append(('accounts', name))
for name in applied_members:
    if name + '.py' not in os.listdir(mem_dir):
        applied_no_file.append(('members', name))

if applied_no_file:
    for app, name in applied_no_file:
        print(f"  GHOST: [{app}] {name} — applied in DB but no file on disk")
else:
    print("  None — every applied row has a matching file on disk")

con.close()
print("\nDone — db.sqlite3 not modified.")
