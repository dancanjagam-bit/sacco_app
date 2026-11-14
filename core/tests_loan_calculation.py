from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from .models import Loan
from .services.loan_calculation import LoanCalculationError, calculate_flat_term, quote_savings_loan


class FlatTermTests(SimpleTestCase):
    def test_flat_term_rounds_half_up_and_distributes_exact_cents(self):
        quote = calculate_flat_term(Decimal("1.10"), 3, Decimal("5"))
        self.assertEqual(quote["total_interest"], Decimal("0.06"))
        self.assertEqual(quote["fees"], Decimal("0.00"))
        self.assertEqual(sum(row["principal"] for row in quote["schedule"]), Decimal("1.10"))
        self.assertEqual(sum(row["payment"] for row in quote["schedule"]), Decimal("1.16"))
        self.assertEqual(quote["schedule"][-1]["remaining"], Decimal("0.00"))

    def test_rate_depends_on_term_and_band_and_has_no_fallback(self):
        self.assertEqual(quote_savings_loan("savings_tier", Decimal("1000"), 12, "C")["interest_rate"], Decimal("8.00"))
        self.assertEqual(quote_savings_loan("savings_tier", Decimal("1000"), 6, "B")["interest_rate"], Decimal("6.50"))
        with self.assertRaises(LoanCalculationError):
            quote_savings_loan("savings_tier", Decimal("1000"), 6, None)


class LoanEstimateTests(APITestCase):
    def setUp(self):
        self.member = get_user_model().objects.create_user(username="loan-calculator-test", is_member=True)
        self.client.force_authenticate(self.member)
        self.payload = {"product": "savings_tier", "amount": "1234.57", "repayment_months": 6}

    def test_member_product_and_quote_match_application(self):
        report = {
            "eligible": True, "interest_band": "B", "max_loan": Decimal("9000"),
            "tier_label": "Silver", "consistent_months": 9, "total_savings": Decimal("4000"),
        }
        products = self.client.get("/api/loan/products/")
        self.assertEqual(products.data["products"][0]["id"], self.payload["product"])
        with patch("core.loan_calculator_views.get_eligibility", return_value=report), patch(
            "core.views.get_eligibility", return_value=report,
        ), patch("core.services.crb_service.CRBService.run_check", return_value=SimpleNamespace(status="not_configured")):
            quote = self.client.post("/api/loan/estimate/", self.payload, format="json")
            self.assertEqual(quote.status_code, 200, quote.data)
            self.assertTrue(quote.data["estimate"])
            self.assertFalse(Loan.objects.exists())
            application = self.client.post("/api/loan/apply/", self.payload, format="json")
            self.assertEqual(application.status_code, 200, application.data)
        self.assertEqual(application.data["repayment_estimate"]["schedule"], quote.data["schedule"])
        self.assertEqual(Loan.objects.get().interest, Decimal("6.50"))

    def test_quote_rejects_malformed_amount_and_missing_tier(self):
        response = self.client.post("/api/loan/estimate/", {**self.payload, "amount": "1.005"}, format="json")
        self.assertEqual(response.status_code, 400)
        response = self.client.post("/api/loan/estimate/", self.payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("savings tier", response.data["detail"])

    def test_member_permission_is_required(self):
        self.member.is_member = False
        self.assertEqual(self.client.get("/api/loan/products/").status_code, 403)
        self.assertEqual(self.client.post("/api/loan/estimate/", self.payload, format="json").status_code, 403)
