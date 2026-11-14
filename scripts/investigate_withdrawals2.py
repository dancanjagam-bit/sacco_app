"""Investigate withdrawal transactions 41 and 50 — corrected column names."""
import sqlite3
import os

DB = os.path.join(os.path.dirname(__file__), '..', 'db.sqlite3')
con = sqlite3.connect(DB)
cur = con.cursor()

# Get actual MpesaTransaction columns first
print("=== core_mpesatransaction COLUMNS ===")
cur.execute("PRAGMA table_info(core_mpesatransaction)")
mpesa_cols = [r[1] for r in cur.fetchall()]
for c in mpesa_cols:
    print(f"  {c}")

print("\n=== MpesaTransaction records referencing tx 41 or 50 ===")
# transaction_id column might be named differently
if 'transaction_id' in mpesa_cols:
    cur.execute("SELECT * FROM core_mpesatransaction WHERE transaction_id IN (41, 50)")
    rows = cur.fetchall()
    print(f"  Rows: {len(rows)}")
    for r in rows:
        print(f"  {dict(zip(mpesa_cols, r))}")
else:
    print("  No 'transaction_id' column — checking all mpesa records:")
    cur.execute("SELECT * FROM core_mpesatransaction")
    rows = cur.fetchall()
    for r in rows:
        print(f"  {dict(zip(mpesa_cols, r))}")

print("\n=== All MpesaTransaction records (full) ===")
cur.execute("SELECT * FROM core_mpesatransaction")
rows = cur.fetchall()
print(f"  Total: {len(rows)}")
for r in rows:
    print(f"  {dict(zip(mpesa_cols, r))}")

print("\n=== WithdrawalCorrectionProposal COLUMNS ===")
cur.execute("PRAGMA table_info(core_withdrawalcorrectionproposal)")
wcp_cols = [r[1] for r in cur.fetchall()]
for c in wcp_cols:
    print(f"  {c}")

print("\n=== WithdrawalCorrectionProposal records for tx 41/50 ===")
if 'original_transaction_id' in wcp_cols:
    cur.execute("SELECT * FROM core_withdrawalcorrectionproposal WHERE original_transaction_id IN (41, 50)")
    rows = cur.fetchall()
    print(f"  Rows: {len(rows)}")
    for r in rows:
        print(f"  {dict(zip(wcp_cols, r))}")
else:
    print("  No original_transaction_id column — listing all:")
    cur.execute("SELECT * FROM core_withdrawalcorrectionproposal")
    rows = cur.fetchall()
    for r in rows:
        print(f"  {dict(zip(wcp_cols, r))}")

print("\n=== All withdrawal transactions ===")
cur.execute("""
    SELECT t.id, t.amount, t.note, t.created_at, t.reverses_id, u.username
    FROM core_transaction t
    JOIN accounts_user u ON t.user_id = u.id
    WHERE t.type='withdrawal' ORDER BY t.id
""")
for r in cur.fetchall():
    print(f"  tx_id={r[0]} amount={r[1]} note={r[2]} date={r[3]} reverses={r[4]} user={r[5]}")

print("\n=== Savings transactions for user Violet (id=13) ===")
cur.execute("SELECT id, account_type, amount, created_at FROM core_savings WHERE user_id=13 ORDER BY id")
for r in cur.fetchall():
    print(f"  savings_id={r[0]} account_type={r[1]} amount={r[2]} date={r[3]}")

print("\n=== Savings transactions for user dan (id=9) ===")
cur.execute("SELECT id, account_type, amount, created_at FROM core_savings WHERE user_id=9 ORDER BY id")
for r in cur.fetchall():
    print(f"  savings_id={r[0]} account_type={r[1]} amount={r[2]} date={r[3]}")

print("\n=== Exit requests ===")
cur.execute("PRAGMA table_info(core_exitrequest)")
exit_cols = [r[1] for r in cur.fetchall()]
cur.execute("SELECT * FROM core_exitrequest ORDER BY id")
rows = cur.fetchall()
print(f"  Total: {len(rows)}")
for r in rows:
    print(f"  {dict(zip(exit_cols, r))}")

con.close()
print("\nDone.")
