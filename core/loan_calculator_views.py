from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.access import has_sacco_permission
from .eligibility import VALID_PERIODS, get_eligibility
from .serializers import LoanEstimateSerializer
from .services.loan_calculation import (
    MINIMUM_AMOUNT, PRODUCT, PRODUCT_NAME, LoanCalculationError, quote_savings_loan, serialize_quote,
)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def loan_products(request):
    if not has_sacco_permission(request.user, "loans.read_own"):
        return Response({"detail": "Member loan access is required."}, status=403)
    return Response({"products": [{
        "id": PRODUCT, "name": PRODUCT_NAME, "repayment_periods": VALID_PERIODS,
        "minimum_amount": str(MINIMUM_AMOUNT), "interest_method": "flat_term",
    }]})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def loan_estimate(request):
    if not has_sacco_permission(request.user, "loans.read_own"):
        return Response({"detail": "Member loan access is required."}, status=403)
    serializer = LoanEstimateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    report = get_eligibility(request.user)
    try:
        quote = quote_savings_loan(data["product"], data["amount"], data["repayment_months"], report["interest_band"])
    except LoanCalculationError as exc:
        return Response({"detail": str(exc)}, status=400)
    return Response({
        **serialize_quote(quote),
        "estimate": True,
        "application_notice": (
            "The requested amount exceeds the limit in your current savings assessment."
            if data["amount"] > report["max_loan"] else ""
        ),
    })
