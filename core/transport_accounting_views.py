from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounting.permissions import IsActiveAccountant
from accounting.services import AccountingConflict, AccountingPermissionDenied, InvalidJournal
from .services.transport_accounting import allocate_transport_receipt
from .transport_models import TransportPayment
from .transport_serializers import TransportReasonInput


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsActiveAccountant])
def transport_allocate_receipt(request, payment_id):
    serializer = TransportReasonInput(data=request.data)
    if not serializer.is_valid():
        return Response({"detail": "Enter an allocation reason of 1–500 characters."}, status=400)
    try:
        entry = allocate_transport_receipt(payment_id, actor=request.user, reason=serializer.validated_data["reason"])
    except TransportPayment.DoesNotExist:
        return Response({"detail": "Payment not found."}, status=404)
    except AccountingPermissionDenied as exc:
        return Response({"detail": str(exc)}, status=403)
    except (AccountingConflict, InvalidJournal) as exc:
        return Response({"detail": str(exc)}, status=409)
    return Response({"payment_id": payment_id, "allocation_journal_id": str(entry.pk)})
