from decimal import Decimal
from rest_framework import serializers
from .models import Savings, Loan, Transaction


class SavingsSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    account_type = serializers.ChoiceField(choices=Savings.ACCOUNT_TYPES, default="fosa")

    class Meta:
        model = Savings
        fields = ['amount', 'account_type']


class LoanApplicationSerializer(serializers.Serializer):
    amount           = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("1.00"))
    repayment_months = serializers.IntegerField()
    purpose          = serializers.ChoiceField(choices=[
        "business","education","medical","asset","housing","farming","personal","other"
    ], default="personal")
    purpose_details  = serializers.CharField(max_length=500, required=False, allow_blank=True)


class RepaymentSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))


class WithdrawalSerializer(serializers.Serializer):
    amount       = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("1.00"))
    account_type = serializers.ChoiceField(choices=[("fosa", "FOSA"), ("bosa", "BOSA")], default="fosa")


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
    class Meta:
        model = Transaction
        fields = ["id", "type", "amount", "note", "created_at"]
