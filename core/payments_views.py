"""
core/payments_views.py
~~~~~~~~~~~~~~~~~~~~~~~
Daraja / M-Pesa payment endpoints.

URL map (all under /api/payments/mpesa/):
  POST  stk/            — member initiates an STK push payment
  GET   status/<cid>/   — member polls for payment status
  POST  callback/       — Daraja posts the STK result (public, no JWT)

Payment types handled
---------------------
  registration  — one-time registration fee; sets member.daraja_registered=True
  deposit       — savings deposit (bosa or fosa); creates Savings + Transaction
  repayment     — loan repayment; reduces Loan.balance + creates Transaction
"""

import logging
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction as db_transaction
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from members.models import Member
from .models import Loan, MpesaTransaction, Savings, Transaction
from .services.daraja_service import DarajaError, initiate_stk_push, parse_stk_callback, to_safaricom_phone
from accounts.models import AuditLog, Notification
from .transport_models import TransportPayment, TransportRemittance

logger = logging.getLogger("sacco.daraja")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _member_ref(member: Member) -> str:
    """Short account reference shown on the M-Pesa receipt (max 12 chars)."""
    return member.member_number[:12]


def _notify(user, title: str, message: str, ntype: str = "success"):
    Notification.objects.create(user=user, type=ntype, title=title, message=message)


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/payments/mpesa/stk/
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def initiate_payment(request):
    """
    Trigger an STK push to the member's M-Pesa phone.

    Request body
    ------------
    {
        "payment_type": "registration" | "deposit" | "repayment",
        "amount":        <number — KES, whole numbers only>,
        "account_type":  "bosa" | "fosa",          # required for deposit
        "loan_id":       <int>,                    # required for repayment
        "phone":         "07XXXXXXXX"              # optional — defaults to member's phone
    }

    Success response (HTTP 200)
    ---------------------------
    {
        "checkout_request_id": "ws_CO_...",
        "message": "STK push sent — enter your M-Pesa PIN to complete."
    }
    """
    user = request.user

    try:
        member = user.member_profile
    except Member.DoesNotExist:
        return Response({"error": "Member profile not found."}, status=400)

    payment_type = request.data.get("payment_type", "")
    if payment_type not in ("registration", "deposit", "repayment"):
        return Response(
            {"error": "payment_type must be 'registration', 'deposit', or 'repayment'."},
            status=400,
        )

    # ── Amount ──────────────────────────────────────────────────────────────
    if payment_type == "registration":
        amount = settings.MPESA_REGISTRATION_FEE
        if amount <= 0:
            return Response({"error": "Registration fee is not configured."}, status=400)
        if member.daraja_registered:
            return Response(
                {"error": "You have already completed Daraja registration."},
                status=400,
            )
        if MpesaTransaction.objects.filter(user=user, payment_type="registration", status="pending").exists():
            return Response({"error": "A registration payment is already pending. Check its status before retrying."}, status=409)
    else:
        try:
            amount_value = Decimal(str(request.data.get("amount", "0")))
            if not amount_value.is_finite() or amount_value != amount_value.to_integral_value() or amount_value < 1:
                raise ValueError
            amount = int(amount_value)
        except (ValueError, TypeError):
            return Response({"error": "Enter a valid amount (whole KES, min 1)."}, status=400)
        except InvalidOperation:
            return Response({"error": "Enter a valid amount (whole KES, min 1)."}, status=400)

    # ── Deposit-specific validation ──────────────────────────────────────────
    account_type = ""
    if payment_type == "deposit":
        account_type = request.data.get("account_type", "")
        if account_type not in ("bosa", "fosa"):
            return Response({"error": "account_type must be 'bosa' or 'fosa'."}, status=400)

    # ── Repayment-specific validation ────────────────────────────────────────
    loan = None
    if payment_type == "repayment":
        loan_id = request.data.get("loan_id")
        if not loan_id:
            return Response({"error": "loan_id is required for repayments."}, status=400)
        try:
            loan = Loan.objects.get(id=loan_id, user=user, status="approved")
        except Loan.DoesNotExist:
            return Response({"error": "Active loan not found."}, status=404)
        if amount > loan.balance:
            return Response(
                {"error": f"Amount exceeds outstanding balance of KES {loan.balance}."},
                status=400,
            )

    # ── Phone ────────────────────────────────────────────────────────────────
    phone = str(request.data.get("phone") or member.phone_number)
    try:
        phone = to_safaricom_phone(phone)
    except DarajaError as exc:
        return Response({"error": exc.message}, status=400)

    # ── STK push ─────────────────────────────────────────────────────────────
    desc_map = {
        "registration": "Reg Fee",
        "deposit":      f"{account_type.upper()} Deposit" if account_type else "Deposit",
        "repayment":    "Loan Repayment",
    }
    try:
        resp = initiate_stk_push(
            phone=phone,
            amount=amount,
            account_ref=_member_ref(member),
            transaction_desc=desc_map[payment_type],
            callback_tag=payment_type,
        )
    except DarajaError as exc:
        logger.error("STK push failed for user %s: %s", user.username, exc.message)
        return Response({"error": exc.message}, status=502)

    # ── Persist the pending MpesaTransaction ─────────────────────────────────
    MpesaTransaction.objects.create(
        user=user,
        phone=to_safaricom_phone(phone),
        payment_type=payment_type,
        amount=amount,
        checkout_request_id=resp["CheckoutRequestID"],
        merchant_request_id=resp.get("MerchantRequestID", ""),
        account_type=account_type,
        loan=loan,
        status="pending",
    )

    logger.info(
        "STK push initiated — user=%s type=%s amount=%s cid=%s",
        user.username, payment_type, amount, resp["CheckoutRequestID"],
    )
    return Response({
        "checkout_request_id": resp["CheckoutRequestID"],
        "message": "STK push sent to your phone — enter your M-Pesa PIN to complete.",
    })


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/payments/mpesa/status/<checkout_request_id>/
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payment_status(request, checkout_request_id: str):
    """
    Poll for the result of an STK push.

    Returns
    -------
    {
        "status":        "pending" | "confirmed" | "failed" | "cancelled",
        "mpesa_receipt": "QJL7XXXXXX" | "",
        "amount":        500,
        "payment_type":  "registration"
    }
    """
    try:
        txn = MpesaTransaction.objects.get(
            checkout_request_id=checkout_request_id,
            user=request.user,
        )
    except MpesaTransaction.DoesNotExist:
        return Response({"error": "Transaction not found."}, status=404)

    return Response({
        "status":        txn.status,
        "mpesa_receipt": txn.mpesa_receipt,
        "amount":        txn.amount,
        "payment_type":  txn.payment_type,
    })


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/payments/mpesa/callback/   (also handles sub-paths like /registration/)
# Public endpoint — Daraja posts here; no JWT auth.
# ─────────────────────────────────────────────────────────────────────────────

@csrf_exempt
@api_view(["POST"])
@permission_classes([AllowAny])
@db_transaction.atomic
def mpesa_callback(request, payment_type: str = ""):
    """
    Receive and process the Daraja STK push callback.

    Daraja guarantees at-least-once delivery — we guard against duplicates
    using the unique constraint on checkout_request_id + mpesa_receipt.

    On success:
      - Updates MpesaTransaction.status = "confirmed"
      - Runs the appropriate ledger action inside a DB transaction
      - For 'registration': sets member.daraja_registered = True
      - For 'deposit': creates Savings + Transaction records
      - For 'repayment': reduces Loan.balance + creates Transaction record
    """
    try:
        parsed = parse_stk_callback(request.data)
    except DarajaError as exc:
        logger.error("Bad STK callback body (%s)", type(exc).__name__)
        # Always return 200 to Daraja — otherwise it retries indefinitely
        return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

    checkout_id = parsed["checkout_request_id"]

    try:
        mpesa_txn = MpesaTransaction.objects.select_for_update().get(
            checkout_request_id=checkout_id
        )
    except MpesaTransaction.DoesNotExist:
        logger.warning("Callback for unknown CheckoutRequestID: %s", checkout_id)
        return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

    # Idempotency — ignore duplicate callbacks for already-processed payments
    if mpesa_txn.status != "pending":
        logger.info("Duplicate callback ignored for cid=%s (status=%s)", checkout_id, mpesa_txn.status)
        return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

    # ── Payment failed / cancelled ────────────────────────────────────────────
    if not parsed["success"]:
        mpesa_txn.status      = "failed"
        mpesa_txn.result_code = parsed["result_code"]
        mpesa_txn.result_desc = parsed["result_desc"]
        mpesa_txn.raw_callback = request.data
        mpesa_txn.save(update_fields=["status", "result_code", "result_desc", "raw_callback", "updated_at"])
        logger.info(
            "STK payment failed — cid=%s code=%s desc=%s",
            checkout_id, parsed["result_code"], parsed["result_desc"],
        )
        _notify(
            mpesa_txn.user,
            "Payment failed",
            f"Your M-Pesa payment of KES {mpesa_txn.amount} was not completed. "
            f"Reason: {parsed['result_desc']}",
            ntype="error",
        )
        return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

    # Credit the ledger only when the callback matches the payment we requested.
    try:
        expected_phone = to_safaricom_phone(mpesa_txn.phone)
        callback_amount = Decimal(str(parsed["amount"]))
        callback_phone = to_safaricom_phone(parsed["phone"] or "")
    except (InvalidOperation, DarajaError):
        expected_phone = None
        callback_amount = None
        callback_phone = None

    if (
        callback_amount != mpesa_txn.amount
        or callback_phone != expected_phone
        or not parsed["mpesa_receipt"]
    ):
        mpesa_txn.result_desc = "Callback details did not match the requested payment; manual reconciliation is required."
        mpesa_txn.raw_callback = request.data
        mpesa_txn.save(update_fields=["result_desc", "raw_callback", "updated_at"])
        logger.error("M-Pesa callback integrity mismatch for cid=%s", checkout_id)
        return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

    # ── Payment confirmed ─────────────────────────────────────────────────────
    receipt = parsed["mpesa_receipt"] or ""

    # Guard against duplicate receipts (Daraja retries can carry the same code)
    if receipt and MpesaTransaction.objects.filter(mpesa_receipt=receipt).exclude(id=mpesa_txn.id).exists():
        logger.warning("Duplicate M-Pesa receipt %s — ignoring callback", receipt)
        return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

    user    = mpesa_txn.user
    ptype   = mpesa_txn.payment_type
    amount  = mpesa_txn.amount

    try:
        with db_transaction.atomic():
            core_txn = None

            if ptype == "registration":
                # Mark member as Daraja-registered — no ledger entry needed
                Member.objects.filter(user=user).update(daraja_registered=True)
                AuditLog.log(
                    actor=user,
                    action="deposit",
                    target=f"Member #{user.member_profile.member_number}",
                    details={
                        "event":   "daraja_registration_fee",
                        "amount":  str(amount),
                        "receipt": receipt,
                    },
                )
                _notify(
                    user,
                    "Daraja registration complete 🎉",
                    f"Your registration fee of KES {amount} has been received "
                    f"(M-Pesa ref: {receipt}). You can now make all SACCO payments via M-Pesa.",
                )

            elif ptype == "deposit":
                acct = mpesa_txn.account_type or "fosa"
                Savings.objects.create(user=user, amount=amount, account_type=acct)
                core_txn = Transaction.objects.create(
                    user=user,
                    type="deposit",
                    amount=amount,
                    note=f"M-Pesa deposit ({acct.upper()}) — {receipt}",
                )
                _notify(
                    user,
                    "Deposit confirmed ✅",
                    f"KES {amount:,} deposited to your {acct.upper()} account "
                    f"(M-Pesa ref: {receipt}).",
                )

            elif ptype == "repayment":
                loan = mpesa_txn.loan
                if loan:
                    from decimal import Decimal
                    paid = Decimal(str(amount))
                    loan.balance = max(Decimal("0.00"), loan.balance - paid)
                    if loan.balance == 0:
                        loan.status = "repaid"
                    loan.save(update_fields=["balance", "status"])
                    core_txn = Transaction.objects.create(
                        user=user,
                        type="repayment",
                        amount=amount,
                        note=f"M-Pesa repayment Loan #{loan.id} — {receipt}",
                    )
                    _notify(
                        user,
                        "Loan repayment received ✅",
                        f"KES {amount:,} repaid on Loan #{loan.id}. "
                        f"Remaining balance: KES {loan.balance:,}. "
                        f"M-Pesa ref: {receipt}.",
                    )

            elif ptype == "transport_remittance":
                payment=TransportPayment.objects.select_for_update().get(mpesa_transaction=mpesa_txn)
                if payment.status != "confirmed":
                    payment.status="confirmed"; payment.mpesa_receipt=receipt
                    payment.confirmed_at=timezone.now(); payment.unallocated_amount=amount
                    payment.save(update_fields=["status","mpesa_receipt","confirmed_at","unallocated_amount"])
                    if payment.remittance:
                        from .transport_views import _refresh_remittance_status
                        _refresh_remittance_status(payment.remittance)
                    AuditLog.log(None,"other",f"Transport payment #{payment.id}",
                        {"event":"provider_confirmed","amount":str(amount),"receipt":receipt})

            # Update the MpesaTransaction record
            mpesa_txn.status       = "confirmed"
            mpesa_txn.mpesa_receipt = receipt
            mpesa_txn.result_code  = parsed["result_code"]
            mpesa_txn.result_desc  = parsed["result_desc"]
            mpesa_txn.raw_callback = request.data
            mpesa_txn.transaction  = core_txn
            mpesa_txn.save(update_fields=[
                "status", "mpesa_receipt", "result_code", "result_desc",
                "raw_callback", "transaction", "updated_at",
            ])

    except Exception as exc:
        logger.exception("Error processing confirmed STK callback cid=%s (%s)", checkout_id, type(exc).__name__)
        # Return 200 so Daraja doesn't retry — the pending status will let us replay manually
        return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

    logger.info(
        "STK payment confirmed — user=%s type=%s amount=%s receipt=%s",
        user.username, ptype, amount, receipt,
    )
    return Response({"ResultCode": 0, "ResultDesc": "Accepted"})


# ─────────────────────────────────────────────────────────────────────────────
# C2B Paybill — Validation & Confirmation
#
# How it works for a button-phone member:
#   1. Member goes to M-Pesa menu → Lipa na M-Pesa → Pay Bill
#   2. Business Number: <MPESA_SHORTCODE>  (e.g. 174379)
#   3. Account Number:  their SACCO member number  (e.g. SACCO000001)
#   4. Amount: how much they want to deposit
#   5. Enter PIN — money leaves their phone
#   6. Safaricom POSTs to our confirmation URL
#   7. We match account number → member, credit their BOSA account, notify them
#
# The account_type defaults to BOSA. To deposit to FOSA the member uses
# account number format:  <member_number>-FOSA  e.g. SACCO000001-FOSA
# ─────────────────────────────────────────────────────────────────────────────

@csrf_exempt
@api_view(["POST"])
@permission_classes([AllowAny])
def c2b_validation(request):
    """
    Safaricom calls this BEFORE money moves.
    We always accept — return ResultCode 0.
    If you want to reject (e.g. unknown account) return ResultCode C2B00012.
    """
    logger.info("C2B validation received: %s", request.data)
    return Response({"ResultCode": 0, "ResultDesc": "Accepted"})


@csrf_exempt
@api_view(["POST"])
@permission_classes([AllowAny])
@db_transaction.atomic
def c2b_confirmation(request):
    """
    Safaricom calls this AFTER money is successfully received.

    Expected payload fields:
        TransactionType     : "Pay Bill"
        TransID             : M-Pesa receipt e.g. "QJL7XXXXXX"
        TransTime           : "20241110120000"
        TransAmount         : "1000.00"
        BusinessShortCode   : "174379"
        BillRefNumber       : member number e.g. "SACCO000001" or "SACCO000001-FOSA"
        MSISDN              : payer phone "2547XXXXXXXX"
        FirstName / LastName: payer name from M-Pesa
    """
    data = request.data
    logger.info("C2B confirmation received: %s", data)

    receipt     = data.get("TransID", "")
    amount_raw  = data.get("TransAmount", "0")
    bill_ref    = str(data.get("BillRefNumber", "")).strip().upper()
    phone_raw   = str(data.get("MSISDN", ""))
    first_name  = data.get("FirstName", "")
    last_name   = data.get("LastName", "")

    # Transport Paybill references are generated per persisted remittance.
    # A phone number is retained only as supporting payment information.
    if receipt and TransportPayment.objects.filter(mpesa_receipt=receipt).exists():
        return Response({"ResultCode":0,"ResultDesc":"Accepted"})
    try:
        amount = Decimal(str(amount_raw))
        if not amount.is_finite() or amount <= 0: raise ValueError
    except (ValueError, InvalidOperation):
        return Response({"ResultCode":0,"ResultDesc":"Accepted"})
    remittance=TransportRemittance.objects.filter(payment_reference=bill_ref).first()
    if remittance or bill_ref.startswith("TR"):
        try:
            with db_transaction.atomic():
                payment=TransportPayment.objects.create(remittance=remittance,payer=None,method="c2b",
                    status="confirmed" if remittance else "unmatched",amount=amount,payer_phone=phone_raw,
                    provider_reference=bill_ref,mpesa_receipt=receipt or None,
                    unallocated_amount=amount if remittance else Decimal("0.00"))
                if remittance:
                    from .transport_views import _refresh_remittance_status
                    _refresh_remittance_status(remittance)
                AuditLog.log(None,"other",f"Transport payment #{payment.id}",
                    {"event":"c2b_received" if remittance else "c2b_unmatched","amount":str(amount),"reference":bill_ref})
        except Exception:
            # C2B callbacks are acknowledged to avoid provider retries creating
            # duplicate posting; staff can inspect unmatched/error references.
            logger.exception("Transport C2B callback could not be recorded")
        return Response({"ResultCode":0,"ResultDesc":"Accepted"})

    # ── Determine account type from bill ref ─────────────────────────────────
    # Format: SACCO000001       → BOSA deposit (default)
    # Format: SACCO000001-FOSA  → FOSA deposit
    # Format: SACCO000001-BOSA  → explicit BOSA
    if "-FOSA" in bill_ref:
        member_number = bill_ref.replace("-FOSA", "").strip()
        account_type  = "fosa"
    elif "-BOSA" in bill_ref:
        member_number = bill_ref.replace("-BOSA", "").strip()
        account_type  = "bosa"
    else:
        member_number = bill_ref
        account_type  = "bosa"   # default paybill deposits go to BOSA

    # ── Guard against duplicate receipts ─────────────────────────────────────
    if receipt and Transaction.objects.filter(note__icontains=receipt).exists():
        logger.warning("Duplicate C2B receipt ignored: %s", receipt)
        return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

    # ── Find the member ───────────────────────────────────────────────────────
    try:
        member = Member.objects.select_related("user").get(member_number__iexact=member_number)
    except Member.DoesNotExist:
        # Unknown account — log and accept (money already received; handle manually)
        logger.error(
            "C2B: unknown member number '%s' — receipt %s amount %s phone %s",
            member_number, receipt, amount_raw, phone_raw,
        )
        # Still return 0 — Safaricom expects 0, non-0 causes retries
        return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

    # ── Parse amount ──────────────────────────────────────────────────────────
    try:
        amount = Decimal(str(amount_raw))
        if amount <= 0:
            raise ValueError
    except (ValueError, InvalidOperation):
        logger.error("C2B: invalid amount '%s' for receipt %s", amount_raw, receipt)
        return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

    user = member.user

    # ── Credit the account ────────────────────────────────────────────────────
    try:
        with db_transaction.atomic():
            Savings.objects.create(user=user, amount=amount, account_type=account_type)
            Transaction.objects.create(
                user=user,
                type="deposit",
                amount=amount,
                note=f"Paybill deposit ({account_type.upper()}) — {receipt} from {first_name} {last_name}".strip(),
            )
            _notify(
                user,
                f"Paybill Deposit Confirmed ✅",
                f"KES {amount:,.0f} received via M-Pesa Paybill and deposited to your "
                f"{account_type.upper()} account.\n"
                f"M-Pesa Ref: {receipt}",
            )
            AuditLog.log(
                actor=None,   # system-initiated (no logged-in user)
                action="deposit",
                target=f"Member {member_number}",
                details={
                    "method":       "c2b_paybill",
                    "amount":       str(amount),
                    "account":      account_type,
                    "receipt":      receipt,
                    "payer_phone":  phone_raw,
                    "payer_name":   f"{first_name} {last_name}".strip(),
                },
            )
    except Exception as exc:
        logger.exception("C2B: error crediting account for receipt %s: %s", receipt, exc)
        return Response({"ResultCode": 0, "ResultDesc": "Accepted"})

    logger.info(
        "C2B: credited KES %s to %s (%s) — receipt %s",
        amount, member_number, account_type, receipt,
    )
    return Response({"ResultCode": 0, "ResultDesc": "Accepted"})
