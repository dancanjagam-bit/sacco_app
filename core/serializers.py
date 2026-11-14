from decimal import Decimal
from django.core.exceptions import ObjectDoesNotExist
import uuid
from rest_framework import serializers
from .models import Savings, Loan, Transaction, FosaWithdrawal
from .services.fosa_payouts import normalize_payout_destination


class SavingsSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    account_type = serializers.ChoiceField(choices=Savings.ACCOUNT_TYPES, default="fosa")

    class Meta:
        model = Savings
        fields = ['amount', 'account_type']


class LoanEstimateSerializer(serializers.Serializer):
    product = serializers.CharField(max_length=30, required=False, default="savings_tier")
    amount           = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("1.00"))
    repayment_months = serializers.IntegerField()


class LoanApplicationSerializer(LoanEstimateSerializer):
    purpose          = serializers.ChoiceField(choices=[
        "business","education","medical","asset","housing","farming","personal","other"
    ], default="personal")
    purpose_details  = serializers.CharField(max_length=500, required=False, allow_blank=True)


class RepaymentSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))


class WithdrawalSerializer(serializers.Serializer):
    amount       = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("1.00"))
    account_type = serializers.ChoiceField(choices=[("fosa", "FOSA"), ("bosa", "BOSA")], default="fosa")
    destination_type = serializers.ChoiceField(
        choices=FosaWithdrawal.DESTINATION_CHOICES, required=False,
    )
    destination = serializers.CharField(max_length=24, required=False, write_only=True)
    client_request_id = serializers.UUIDField(required=False)

    def validate(self, attrs):
        if attrs.get("account_type", "fosa") == "fosa":
            missing = [key for key in ("destination_type", "destination", "client_request_id") if not attrs.get(key)]
            if missing:
                raise serializers.ValidationError({key: "This field is required." for key in missing})
            try:
                attrs["destination"] = normalize_payout_destination(
                    attrs["destination_type"], attrs["destination"],
                )
            except ValueError as exc:
                raise serializers.ValidationError({"destination": str(exc)}) from exc
        return attrs


class TransactionFilterSerializer(serializers.Serializer):
    type = serializers.ChoiceField(
        choices=[("all", "All activity"), *Transaction.TYPE_CHOICES],
        required=False, default="all",
    )
    from_date = serializers.DateField(required=False)
    to_date = serializers.DateField(required=False)
    search = serializers.CharField(required=False, allow_blank=True, max_length=120)

    def validate(self, attrs):
        start, end = attrs.get("from_date"), attrs.get("to_date")
        if start and end and start > end:
            raise serializers.ValidationError({"to_date": "End date must be on or after start date."})
        return attrs


class ExitRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class ExitReviewSerializer(serializers.Serializer):
    action  = serializers.ChoiceField(choices=["approve", "reject"])
    notes   = serializers.CharField(max_length=500, required=False, allow_blank=True)
    rejection_reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class LoanSerializer(serializers.ModelSerializer):
    member      = serializers.SerializerMethodField()
    approved_by = serializers.CharField(source="approved_by.username", read_only=True, default="")

    def get_member(self, obj):
        return obj.user.get_full_name() or obj.user.username

    class Meta:
        model = Loan
        fields = [
            "id", "member", "amount", "purpose", "purpose_details",
            "interest", "repayment_months", "balance", "status",
            "remarks", "savings_months", "total_savings_at_application",
            "approved_by", "approved_at", "created_at",
        ]


class TransactionSerializer(serializers.ModelSerializer):
    withdrawal_status = serializers.SerializerMethodField()
    withdrawal_reference = serializers.SerializerMethodField()
    withdrawal_destination = serializers.SerializerMethodField()
    provider_reference = serializers.SerializerMethodField()
    provider_transaction_id = serializers.SerializerMethodField()
    withdrawal_settled_at = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()
    payment_reference = serializers.SerializerMethodField()
    payment_receipt = serializers.SerializerMethodField()
    payment_payer_masked = serializers.SerializerMethodField()
    payment_account_type = serializers.SerializerMethodField()

    def _withdrawal(self, obj):
        try:
            return obj.fosa_withdrawal
        except ObjectDoesNotExist:
            return None

    def get_withdrawal_status(self, obj):
        if obj.type != "withdrawal":
            return None
        withdrawal = self._withdrawal(obj)
        if withdrawal:
            if withdrawal.status == "succeeded":
                return "confirmed" if withdrawal.provider_transaction_id else "needs_review"
            return withdrawal.status
        # BOSA exit is an internal ledger release; unlinked FOSA debits have no
        # provider evidence and must remain visibly under review.
        if "bosa exit" in (obj.note or "").lower():
            return "posted"
        return "needs_review"

    def get_withdrawal_reference(self, obj):
        withdrawal = self._withdrawal(obj)
        return str(withdrawal.reference) if withdrawal else None

    def get_withdrawal_destination(self, obj):
        withdrawal = self._withdrawal(obj)
        if not withdrawal:
            return None
        return f"{withdrawal.get_destination_type_display()} …{withdrawal.destination_phone[-3:]}"

    def get_provider_reference(self, obj):
        withdrawal = self._withdrawal(obj)
        return withdrawal.provider_reference if withdrawal else None

    def get_provider_transaction_id(self, obj):
        withdrawal = self._withdrawal(obj)
        return withdrawal.provider_transaction_id if withdrawal else None

    def get_withdrawal_settled_at(self, obj):
        withdrawal = self._withdrawal(obj)
        return withdrawal.settled_at if withdrawal else None

    def _payment(self, obj):
        try:
            return obj.mpesa_payment
        except ObjectDoesNotExist:
            return None

    def get_payment_status(self, obj):
        payment = self._payment(obj)
        return payment.status if payment else None

    def get_payment_reference(self, obj):
        payment = self._payment(obj)
        return payment.checkout_request_id if payment else None

    def get_payment_receipt(self, obj):
        payment = self._payment(obj)
        return payment.mpesa_receipt or None if payment else None

    def get_payment_payer_masked(self, obj):
        payment = self._payment(obj)
        return f"…{payment.phone[-3:]}" if payment and payment.phone else None

    def get_payment_account_type(self, obj):
        payment = self._payment(obj)
        return payment.account_type or None if payment else None

    class Meta:
        model = Transaction
        fields = [
            "id", "type", "account_type", "amount", "note", "created_at", "withdrawal_status",
            "withdrawal_reference", "withdrawal_destination", "provider_reference",
            "provider_transaction_id", "withdrawal_settled_at",
            "payment_status", "payment_reference", "payment_receipt",
            "payment_payer_masked", "payment_account_type",
        ]
