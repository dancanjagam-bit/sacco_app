"""Check migration state across all SQLite databases."""
import sqlite3
import os
import glob

BASE = r"c:\Users\USER\sacco_app"
DB_FILES = []

# Main DB
DB_FILES.append(os.path.join(BASE, "db.sqlite3"))

# Recovery DBs
for pattern in [
    os.path.join(BASE, ".recovery", "**", "*.sqlite3"),
    os.path.join(BASE, "sacco_*.sqlite3"),
]:
    DB_FILES.extend(glob.glob(pattern, recursive=True))

DB_FILES = sorted(set(DB_FILES))

for db_path in DB_FILES:
    rel = os.path.relpath(db_path, BASE)
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='django_migrations'")
        if not c.fetchone():
            print("{} -> NO MIGRATIONS TABLE".format(rel))
            conn.close()
            continue
        c.execute("SELECT app, name FROM django_migrations WHERE app='accounts' ORDER BY id")
        migrations = c.fetchall()
        has_0017 = any("0017" in name for _, name in migrations)
        has_0018 = any("0018" in name for _, name in migrations)
        welfare_tables = []
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'accounts_welfare%'")
        welfare_tables = [row[0] for row in c.fetchall()]
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('accounts_cooperativemeeting','accounts_membernotice')")
        meeting_tables = [row[0] for row in c.fetchall()]
        last_acct = migrations[-1][1] if migrations else "none"
        print("{} -> last_accounts={} has_0017={} has_0018={} welfare_tables={} meeting_tables={}".format(
            rel, last_acct, has_0017, has_0018, len(welfare_tables), len(meeting_tables)))
        conn.close()
    except Exception as e:
        print("{} -> ERROR: {}".format(rel, e))
