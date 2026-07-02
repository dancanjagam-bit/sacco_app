from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


# 💰 Savings
class Savings(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)


# 🏦 Loan
class Loan(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("repaid", "Repaid"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    interest = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=10,
    )

    repayment_months = models.PositiveIntegerField(
        default=12,
    )

    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_loans",
    )

    approved_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    remarks = models.TextField(
        blank=True,
        default="",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )


# 💳 Transactions (Ledger)
class Transaction(models.Model):
    TYPE_CHOICES = [
        ("deposit", "Deposit"),
        ("repayment", "Repayment"),
        ("loan", "Loan"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
