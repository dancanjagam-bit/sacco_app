from io import BytesIO
import base64
import re
import uuid
import zlib
from datetime import datetime

from django.contrib.auth import get_user_model
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework.test import APITestCase

from core.models import FosaWithdrawal, MpesaTransaction, Transaction

User = get_user_model()


def pdf_text(content):
    streams = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", content, re.DOTALL):
        encoded = match.group(1).strip().rstrip(b"~>")
        try:
            decoded = zlib.decompress(base64.a85decode(encoded))
            for literal in re.finditer(rb"\(((?:\\.|[^\\)])*)\)\s*Tj", decoded):
                value = literal.group(1)
                value = value.replace(b"\\(", b"(").replace(b"\\)", b")").replace(b"\\\\", b"\\")
                streams.append(value)
        except (ValueError, zlib.error):
            continue
    return b" ".join(streams)


class MemberStatementDownloadTests(APITestCase):
    def setUp(self):
        self.member = User.objects.create_user(
            username="statement_member", password="Pass12345",
            first_name="Statement", last_name="Member",
        )
        self.other = User.objects.create_user(username="statement_other", password="Pass12345")
        self.own_transaction = Transaction.objects.create(
            user=self.member, type="deposit", amount="1234.50", note="OWN-STATEMENT-ENTRY",
        )
        Transaction.objects.create(
            user=self.other, type="deposit", amount="9876.50", note="PRIVATE-OTHER-ENTRY",
        )

    def test_excel_download_is_a_real_member_scoped_xlsx(self):
        self.client.force_authenticate(self.member)
        response = self.client.get("/api/transactions/excel/?user_id=%s" % self.other.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("attachment; filename=\"sacco_statement.xlsx\"", response["Content-Disposition"])
        workbook = load_workbook(BytesIO(response.content), data_only=True)
        values = [cell.value for row in workbook.active.iter_rows() for cell in row]
        self.assertIn("Member: Statement Member", values)
        self.assertIn("OWN-STATEMENT-ENTRY", values)
        self.assertNotIn("PRIVATE-OTHER-ENTRY", values)
        self.assertIn(self.own_transaction.created_at.strftime("%d/%m/%Y %H:%M"), values)
        self.assertIn(1234.5, values)
        self.assertNotIn(9876.5, values)

    def test_pdf_download_is_a_nonempty_pdf_scoped_to_current_member(self):
        self.client.force_authenticate(self.member)
        response = self.client.get("/api/statement/pdf/?user_id=%s" % self.other.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment; filename=\"NWTCS_Statement_", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertGreater(len(response.content), 800)
        text_layer = pdf_text(response.content)
        self.assertTrue(text_layer, "PDF content stream should decode as ASCII85 + Flate data")
        self.assertIn(b"STATEMENT MEMBER", text_layer)
        self.assertIn(b"OWN-STATEMENT-ENTRY", text_layer)
        self.assertIn(b"1,234.50", text_layer)
        self.assertIn(self.own_transaction.created_at.strftime("%d/%m/%Y").encode(), text_layer)
        self.assertNotIn(b"PRIVATE-OTHER-ENTRY", text_layer)

    def test_unauthenticated_exports_are_rejected_not_returned_as_files(self):
        for endpoint in ("/api/transactions/excel/", "/api/statement/pdf/"):
            response = self.client.get(endpoint)
            self.assertEqual(response.status_code, 401)
            self.assertNotIn("attachment", response.get("Content-Disposition", ""))

    def test_empty_member_statements_still_return_valid_file_formats(self):
        empty = User.objects.create_user(username="empty_statement", password="Pass12345")
        self.client.force_authenticate(empty)
        xlsx = self.client.get("/api/transactions/excel/")
        self.assertEqual(xlsx.status_code, 200)
        workbook = load_workbook(BytesIO(xlsx.content), data_only=True)
        self.assertEqual(workbook.active["A7"].value, "#")
        pdf = self.client.get("/api/statement/pdf/")
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF-"))

    def test_excel_download_applies_date_range_without_changing_member_scope(self):
        self.client.force_authenticate(self.member)
        response = self.client.get("/api/transactions/excel/?from=2099-01-01&to=2099-12-31")
        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.content), data_only=True)
        values = [cell.value for row in workbook.active.iter_rows() for cell in row]
        self.assertNotIn("OWN-STATEMENT-ENTRY", values)
        self.assertNotIn("PRIVATE-OTHER-ENTRY", values)
        self.assertIn("Total Deposits", values)

    def test_excel_download_rejects_invalid_or_reversed_dates(self):
        self.client.force_authenticate(self.member)
        invalid = self.client.get("/api/transactions/excel/?from=not-a-date")
        reversed_range = self.client.get("/api/transactions/excel/?from=2026-12-31&to=2026-01-01")
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(reversed_range.status_code, 400)

    def test_pdf_download_rejects_invalid_or_reversed_dates_instead_of_silently_defaulting(self):
        self.client.force_authenticate(self.member)
        invalid = self.client.get("/api/statement/pdf/?from=not-a-date")
        reversed_range = self.client.get("/api/statement/pdf/?from=2026-12-31&to=2026-01-01")
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(reversed_range.status_code, 400)
        self.assertNotIn("application/pdf", invalid.get("Content-Type", ""))
        self.assertNotIn("attachment", invalid.get("Content-Disposition", ""))

    def test_transaction_history_marks_unverified_withdrawals_for_review_and_scopes_records(self):
        self.client.force_authenticate(self.member)
        unverified = Transaction.objects.create(
            user=self.member, type="withdrawal", amount="300.00", note="Legacy FOSA withdrawal",
        )
        paid = Transaction.objects.create(
            user=self.member, type="withdrawal", amount="200.00", note="Confirmed FOSA payout",
        )
        payout = FosaWithdrawal.objects.create(
            client_request_id=uuid.uuid4(), user=self.member, amount="200.00",
            destination_type="mpesa", destination_phone="+254712345678", status="succeeded",
            provider_reference="provider-request-1", provider_transaction_id="provider-tx-1",
            ledger_transaction=paid,
        )
        missing_provider_receipt = Transaction.objects.create(
            user=self.member, type="withdrawal", amount="50.00", note="Missing payout evidence",
        )
        FosaWithdrawal.objects.create(
            client_request_id=uuid.uuid4(), user=self.member, amount="50.00",
            destination_type="mpesa", destination_phone="+254712345678", status="succeeded",
            provider_reference="provider-request-missing-receipt",
            ledger_transaction=missing_provider_receipt,
        )
        deposit = Transaction.objects.create(
            user=self.member, type="deposit", amount="125.00", note="M-Pesa FOSA deposit",
        )
        MpesaTransaction.objects.create(
            user=self.member, phone="254712345678", payment_type="deposit", amount="125.00",
            checkout_request_id="checkout-request-test", status="confirmed", mpesa_receipt="QWERTY123",
            transaction=deposit, account_type="fosa",
        )
        Transaction.objects.create(user=self.other, type="deposit", amount="999.00", note="OTHER-PRIVATE")

        response = self.client.get("/api/transactions/")
        self.assertEqual(response.status_code, 200)
        rows = {row["id"]: row for row in response.data["results"]}
        self.assertEqual(rows[unverified.id]["withdrawal_status"], "needs_review")
        self.assertEqual(rows[paid.id]["withdrawal_status"], "confirmed")
        self.assertEqual(rows[paid.id]["withdrawal_reference"], str(payout.reference))
        self.assertEqual(rows[paid.id]["withdrawal_destination"], "M-Pesa …678")
        self.assertEqual(rows[paid.id]["provider_reference"], "provider-request-1")
        self.assertEqual(rows[missing_provider_receipt.id]["withdrawal_status"], "needs_review")
        self.assertEqual(rows[deposit.id]["payment_status"], "confirmed")
        self.assertEqual(rows[deposit.id]["payment_reference"], "checkout-request-test")
        self.assertEqual(rows[deposit.id]["payment_receipt"], "QWERTY123")
        self.assertEqual(rows[deposit.id]["payment_payer_masked"], "…678")
        self.assertEqual(rows[deposit.id]["payment_account_type"], "fosa")
        self.assertNotIn("OTHER-PRIVATE", [row["note"] for row in response.data["results"]])

    def test_pdf_keeps_accounts_separate_and_calculates_pre_period_opening(self):
        def at(year, month, day):
            return timezone.make_aware(datetime(year, month, day), timezone.get_current_timezone())

        records = [
            Transaction(user=self.member, type="deposit", account_type="bosa", amount="1000.00", note="BOSA opening", created_at=at(2026, 1, 1)),
            Transaction(user=self.member, type="deposit", account_type="bosa", amount="200.00", note="BOSA in range", created_at=at(2026, 2, 4)),
            Transaction(user=self.member, type="deposit", account_type="bosa", amount="25.00", note="Tie order A", created_at=at(2026, 2, 5)),
            Transaction(user=self.member, type="deposit", account_type="bosa", amount="30.00", note="Tie order B", created_at=at(2026, 2, 5)),
            Transaction(user=self.member, type="deposit", account_type="fosa", amount="500.00", note="FOSA in range", created_at=at(2026, 2, 6)),
        ]
        record_times = [entry.created_at for entry in records]
        created = Transaction.objects.bulk_create(records)
        for entry, created_at in zip(created, record_times):
            Transaction.objects.filter(pk=entry.pk).update(created_at=created_at)
        self.client.force_authenticate(self.member)

        response = self.client.get("/api/statement/pdf/?from=2026-02-01&to=2026-02-28")
        self.assertEqual(response.status_code, 200)
        text = pdf_text(response.content)
        self.assertIn(b"BOSA savings", text)
        self.assertIn(b"FOSA savings", text)
        self.assertTrue(b"Opening balance before period: KES 1,000.00" in text, "missing BOSA opening balance")
        self.assertTrue(b"Closing balance for period: KES 1,255.00" in text, "incorrect BOSA closing balance")
        self.assertTrue(b"Closing balance for period: KES 500.00" in text, "incorrect FOSA closing balance")
        self.assertLess(text.index(b"Tie order A"), text.index(b"Tie order B"))

    def test_pdf_separates_unverified_withdrawals_and_pending_payment_requests(self):
        unverified = Transaction.objects.create(
            user=self.member, type="withdrawal", account_type="fosa", amount="9000.00",
            note="Unverified payout must not enter the posted balance",
        )
        FosaWithdrawal.objects.create(
            client_request_id=uuid.uuid4(), user=self.member, amount="9000.00",
            destination_type="mpesa", destination_phone="+254712345678", status="uncertain",
            provider_reference="review-reference-long-000000000000000000000000000000000001",
            ledger_transaction=unverified,
        )
        MpesaTransaction.objects.create(
            user=self.member, phone="254712345678", payment_type="deposit", amount="350.00",
            checkout_request_id="pending-checkout-reference-000000000000000000000000000000000001",
            status="pending", account_type="fosa",
        )
        self.client.force_authenticate(self.member)

        response = self.client.get("/api/statement/pdf/?from=2026-01-01&to=2026-12-31")
        self.assertEqual(response.status_code, 200)
        text = pdf_text(response.content)
        self.assertIn(b"Pending and review items", text)
        self.assertIn(b"Needs provider investigation", text)
        self.assertIn(b"Pending provider confirmation", text)
        self.assertIn(b"pending-checkout-reference", text)
        self.assertIn(b"review-reference-long", text)
        self.assertNotIn(b"Closing balance for period: KES -9,000.00", text)
        compact_text = re.sub(rb"\s+", b"", text)
        self.assertTrue(b"Unverifiedpayoutmustnotenterthepostedbalance" in compact_text, "review note missing from pending section")

    def test_pdf_linked_reversal_nets_against_the_original_settled_debit(self):
        original = Transaction.objects.create(
            user=self.member, type="withdrawal", account_type="fosa", amount="300.00",
            note="Confirmed FOSA payout",
        )
        FosaWithdrawal.objects.create(
            client_request_id=uuid.uuid4(), user=self.member, amount="300.00",
            destination_type="mpesa", destination_phone="+254712345678", status="succeeded",
            provider_reference="provider-request-reversal-test", provider_transaction_id="provider-receipt-reversal-test",
            ledger_transaction=original,
        )
        Transaction.objects.create(
            user=self.member, type="adjustment", account_type="fosa", amount="300.00",
            note="Approved reversal", reverses=original,
        )
        self.client.force_authenticate(self.member)

        response = self.client.get("/api/statement/pdf/?from=2026-01-01&to=2026-12-31")
        self.assertEqual(response.status_code, 200)
        text = pdf_text(response.content)
        self.assertIn(b"Reversal of TX", text)
        self.assertIn(b"Closing balance for period: KES 0.00", text)

    def test_pdf_long_activity_spans_pages_repeats_headers_and_numbers_pages(self):
        when = timezone.make_aware(datetime(2026, 3, 1), timezone.get_current_timezone())
        long_note = "LONG-REFERENCE-" * 10 + "VISIBLE-TAIL-REFERENCE-0000123456789"
        bulk_entries = Transaction.objects.bulk_create([
            Transaction(
                user=self.member, type="deposit", account_type="fosa", amount="1.00",
                note=f"{index:03d}-{long_note}", created_at=when,
            )
            for index in range(100)
        ])
        Transaction.objects.filter(pk__in=[entry.pk for entry in bulk_entries]).update(created_at=when)
        self.client.force_authenticate(self.member)

        response = self.client.get("/api/statement/pdf/?from=2026-03-01&to=2026-03-31")
        self.assertEqual(response.status_code, 200)
        text = pdf_text(response.content)
        page_count = len(re.findall(rb"/Type\s*/Page(?!s)", response.content))
        self.assertGreaterEqual(page_count, 2, "statement did not paginate")
        self.assertGreaterEqual(text.count(b"Activity and notes"), 2, "transaction header was not repeated")
        self.assertTrue(b"Page 2" in text, "page number missing")
        compact_text = re.sub(rb"\s+", b"", text)
        self.assertTrue(b"VISIBLE-TAIL-REFERENCE-0000123456789" in compact_text, "long reference was truncated")
