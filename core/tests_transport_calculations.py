import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from core.services.transport_operations import calculate_shift_closure
from core.transport_models import (
    CrewAssignment,
    TransportCollection,
    TransportDeductionRule,
    TransportExpense,
    TransportRoute,
    Vehicle,
)


class TransportShiftCalculationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.driver = user_model.objects.create_user(username="calculation-driver")
        cls.approver = user_model.objects.create_user(username="calculation-approver", is_superuser=True)
        vehicle = Vehicle.objects.create(registration="TEST-CALC", owner=cls.driver)
        route = TransportRoute.objects.create(name="Synthetic calculation route")
        cls.assignment = CrewAssignment.objects.create(
            vehicle=vehicle, route=route, driver=cls.driver, starts_at=timezone.now(), status="active",
        )
        cls.shift = cls.assignment.shift
        for amount in ("10.01", "2.02"):
            TransportCollection.objects.create(
                assignment=cls.assignment, recorded_by=cls.driver,
                amount=Decimal(amount), client_key=uuid.uuid4(),
            )

    def create_rule(self, *, active=True):
        return TransportDeductionRule.objects.create(
            version="synthetic-calculation-v1", active=active, deductible_categories=["fuel"],
            approval_reference="TEST-APPROVAL", approved_by=self.approver, approved_at=timezone.now(),
        )

    def record_expense(self, category, amount, status="approved"):
        TransportExpense.objects.create(
            assignment=self.assignment, shift=self.shift, vehicle=self.assignment.vehicle,
            route=self.assignment.route, reported_by=self.driver, client_key=uuid.uuid4(),
            category=category, amount=Decimal(amount), status=status,
        )

    def test_inactive_approved_rule_does_not_calculate_expected_remittance(self):
        self.create_rule(active=False)
        self.record_expense("fuel", "0.10")

        amounts = calculate_shift_closure(self.shift)

        self.assertEqual(amounts.status, "rule_required")
        self.assertEqual(amounts.reported_gross, Decimal("12.03"))
        self.assertEqual(amounts.approved_expenses, Decimal("0.10"))
        self.assertEqual(amounts.deductible_expenses, Decimal("0.00"))
        self.assertIsNone(amounts.expected_remittance)

    def test_only_approved_expenses_in_rule_categories_reduce_remittance(self):
        rule = self.create_rule()
        self.record_expense("fuel", "0.10")
        self.record_expense("fuel", "0.20")
        self.record_expense("repairs", "0.60")
        self.record_expense("fuel", "2.00", "reported")
        self.record_expense("fuel", "3.00", "rejected")

        amounts = calculate_shift_closure(self.shift)

        self.assertEqual(amounts.status, "calculated")
        self.assertEqual(amounts.rule_version, rule.version)
        self.assertEqual(amounts.reported_gross, Decimal("12.03"))
        self.assertEqual(amounts.approved_expenses, Decimal("0.90"))
        self.assertEqual(amounts.deductible_expenses, Decimal("0.30"))
        self.assertEqual(amounts.expected_remittance, Decimal("11.73"))

    def test_deductions_equal_to_gross_leave_zero_due_and_excess_requires_review(self):
        self.create_rule()
        self.record_expense("fuel", "12.03")

        equal_amounts = calculate_shift_closure(self.shift)

        self.assertEqual(equal_amounts.status, "calculated")
        self.assertEqual(equal_amounts.expected_remittance, Decimal("0.00"))

        self.record_expense("fuel", "0.01")
        excess_amounts = calculate_shift_closure(self.shift)

        self.assertEqual(excess_amounts.status, "review_required")
        self.assertEqual(excess_amounts.deductible_expenses, Decimal("12.04"))
        self.assertIsNone(excess_amounts.expected_remittance)
