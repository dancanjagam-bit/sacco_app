"""Investigate withdrawal transactions 41 and 50 and the current withdrawal safeguard."""
import sqlite3
import os

DB = os.path.join(os.path.dirname(__file__), '..', 'db.sqlite3')
con = sqlite3.connect(DB)
cur = con.cursor()

print("=== WITHDRAWAL INVESTIGATION ===")
print("\n1. Transaction rows 41 and 50 with user context:")
cur.execute("""
    SELECT t.id, t.type, t.amount, t.note, t.created_at, t.reverses_id,
           u.id as user_id, u.username,
           m.member_number, m.status as member_status
    FROM core_transaction t
    JOIN accounts_user u ON t.user_id = u.id
    LEFT JOIN members_member m ON m.user_id = u.id
    WHERE t.id IN (41, 50)
""")
for r in cur.fetchall():
    print(f"  tx_id={r[0]} type={r[1]} amount={r[2]} note={r[3]} created={r[4]} reverses={r[5]}")
    print(f"    user: id={r[6]} username={r[7]} member_number={r[8]} member_status={r[9]}")

print("\n2. Corresponding FosaWithdrawal records for user_id 9 and 13:")
cur.execute("SELECT COUNT(*) FROM core_fosawithdrawal WHERE user_id IN (9, 13)")
print(f"  FosaWithdrawal rows for these users: {cur.fetchone()[0]}")

print("\n3. MpesaTransaction records referencing transactions 41 or 50:")
cur.execute("""
    SELECT id, payment_type, amount, status, receipt_number, account_type, transaction_id
    FROM core_mpesatransaction
    WHERE transaction_id IN (41, 50)
""")
rows = cur.fetchall()
print(f"  Matching MpesaTransaction rows: {len(rows)}")
for r in rows:
    print(f"    mpesa_id={r[0]} payment_type={r[1]} amount={r[2]} status={r[3]} receipt={r[4]} account={r[5]} tx={r[6]}")

print("\n4. WithdrawalCorrectionProposal records for these transactions:")
cur.execute("SELECT COUNT(*) FROM core_withdrawalcorrectionproposal WHERE original_transaction_id IN (41, 50)")
print(f"  CorrectionProposal rows: {cur.fetchone()[0]}")

print("\n5. FosaWithdrawal state for all users (confirm zero total):")
cur.execute("SELECT status, COUNT(*), SUM(amount) FROM core_fosawithdrawal GROUP BY status")
rows = cur.fetchall()
if not rows:
    print("  No FosaWithdrawal records exist in the database.")
else:
    for r in rows:
        print(f"  status={r[0]} count={r[1]} total={r[2]}")

print("\n6. All withdrawal-type transactions:")
cur.execute("""
    SELECT t.id, t.amount, t.note, t.created_at, u.username
    FROM core_transaction t
    JOIN accounts_user u ON t.user_id = u.id
    WHERE t.type='withdrawal'
    ORDER BY t.id
""")
for r in cur.fetchall():
    print(f"  tx_id={r[0]} amount={r[1]} note={r[2]} date={r[3]} user={r[4]}")

print("\n7. Exit requests:")
cur.execute("SELECT id, user_id, status, reason, created_at FROM core_exitrequest ORDER BY id")
rows = cur.fetchall()
print(f"  Total exit requests: {len(rows)}")
for r in rows:
    print(f"  id={r[0]} user={r[1]} status={r[2]} reason={r[3]} created={r[4]}")

print("\n8. Current FOSA/BOSA balances for users 9 and 13:")
for uid, uname in [(9, 'dan'), (13, 'Violet')]:
    cur.execute("SELECT account_type, SUM(amount) FROM core_savings WHERE user_id=? GROUP BY account_type", (uid,))
    rows = cur.fetchall()
    print(f"  user_id={uid} ({uname}):")
    for r in rows:
        print(f"    {r[0]}: {r[1]}")
    if not rows:
        print("    (no savings rows)")

print("\n9. Transactions context for users 9 and 13:")
for uid, uname in [(9, 'dan'), (13, 'Violet')]:
    cur.execute("SELECT id, type, amount, note, created_at FROM core_transaction WHERE user_id=? ORDER BY id", (uid,))
    rows = cur.fetchall()
    print(f"  user_id={uid} ({uname}) — {len(rows)} transactions:")
    for r in rows:
        print(f"    tx_id={r[0]} type={r[1]} amount={r[2]} note={r[3]} date={r[4]}")

con.close()
print("\nDone.")
