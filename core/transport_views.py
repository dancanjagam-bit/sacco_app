from datetime import timedelta
from decimal import Decimal
import uuid

from django.db import IntegrityError, OperationalError, connection, transaction
from django.db.models import Q, Sum
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import AuditLog
from accounts.access import active_staff_duties, has_sacco_permission, is_staff_manager, access_snapshot, staff_roles_for_user
from .services.transport_accounting import transport_accounting_data, transport_journals
from .transport_models import (TransportRole, TransportRoute, Vehicle, VehicleOwnership, CrewAssignment,
    TransportCollection, TransportRoleGrant, TransportRemittance, TransportPayment,
    TransportExpense, TransportShiftClosure, TransportPaymentReviewEvent,
    TransportAssignmentIssue)
from .transport_serializers import (
    CrewAssignmentInput, TransportCollectionInput, TransportExpenseInput, TransportReasonInput,
)


def _money(value):
    """Serialize KES amounts consistently, including whole shilling values."""
    return str(Decimal(value or 0).quantize(Decimal("0.01")))


def _invalid_input(serializer):
    field, messages = next(iter(serializer.errors.items()))
    detail = messages[0]
    if field != "non_field_errors":
        detail = f"{field}: {detail}"
    return Response({"detail": detail, "errors": serializer.errors}, status=400)


def _locked_database_response(exc):
    # SQLite permits one writer and cannot always upgrade a read transaction
    # while another request writes. Retry the whole request with the same key.
    if connection.vendor != "sqlite" or "locked" not in str(exc).lower():
        raise exc
    return Response(
        {"detail": "Transport records are busy. Retry the request."},
        status=503, headers={"Retry-After": "1"},
    )


def _crew_scope(user):
    roles = set(TransportRole.objects.filter(
        user=user, active=True, role__in=(TransportRole.DRIVER, TransportRole.CONDUCTOR),
    ).values_list("role", flat=True))
    scope = Q(pk__in=[])
    if TransportRole.DRIVER in roles:
        scope |= Q(driver=user)
    if TransportRole.CONDUCTOR in roles:
        scope |= Q(conductor=user)
    return scope


def _assignment_status(assignment, now):
    if assignment.status == "ended" or (assignment.ends_at and assignment.ends_at <= now):
        return "ended"
    if assignment.starts_at > now:
        return "scheduled"
    return "active"


def _assignment_open(now):
    return Q(
        status__in=("scheduled", "active"), starts_at__lte=now,
        vehicle__active=True, route__active=True, shift__status__in=("scheduled", "active"),
    ) & (Q(ends_at__isnull=True) | Q(ends_at__gt=now))


def _staff(user, roles=None):
    if roles is None:
        return is_staff_manager(user)
    roles = set(roles)
    if "superadmin" in roles and is_staff_manager(user):
        return True
    aliases = {"accountant": "treasurer", "loan_officer": "credit_officer"}
    assigned = staff_roles_for_user(user)
    return bool({aliases.get(role, role) for role in roles if role != "superadmin"}.intersection(assigned))


def _staff_duties(user, duty=None):
    """Return time-valid scoped duties, or None when that schema is not installed."""
    if not access_snapshot(user).get("staff_role_grants_available", True):
        return None
    return active_staff_duties(user, duty)


def _clerk_has_duty(user, duty, assignment=None, vehicle=None):
    if "clerk" not in staff_roles_for_user(user):
        return False, "denied"
    duties = _staff_duties(user, duty)
    if duties is None:
        return False, "schema"
    if assignment is not None:
        duties = duties.filter(Q(crew_assignment_id=assignment.id) | Q(vehicle_id=assignment.vehicle_id))
    if vehicle is not None:
        duties = duties.filter(vehicle_id=vehicle.id)
    return duties.exists(), "scope"


def _assignment_data(a, include_collections=True):
    collections = a.collections.all() if include_collections else []
    shift = getattr(a, "shift", None)
    expenses = list(shift.expenses.order_by("created_at")) if shift and include_collections else []
    closure = getattr(shift, "closure", None) if shift else None
    remittances = list(a.remittances.prefetch_related("payments").all()) if include_collections else []
    confirmed_receipts = sum((p.received_amount for rem in remittances for p in rem.payments.all()
                              if (p.confirmed_at or p.status == "confirmed" or (p.method == "c2b" and p.status == "unmatched")) and p.received_amount is not None), Decimal("0.00"))
    pending_remittance = sum((max(Decimal("0.00"), rem.amount - sum((p.received_amount for p in rem.payments.all()
        if (p.confirmed_at or p.status == "confirmed" or (p.method == "c2b" and p.status == "unmatched")) and p.received_amount is not None), Decimal("0.00"))) for rem in remittances), Decimal("0.00"))
    status = _assignment_status(a, timezone.now())
    shift_status = shift.status if shift else "unavailable"
    if shift_status == "scheduled" and status == "active":
        shift_status = "active"
    return {"id": a.id, "vehicle": a.vehicle_id, "vehicle_registration": a.vehicle_label,
            "route": a.route_id, "route_name": a.route_label, "driver": a.driver_id,
            "driver_name": a.driver_label, "conductor": a.conductor_id,
            "conductor_name": a.conductor_label, "starts_at": a.starts_at,
            "ends_at": a.ends_at, "status": status,
            "shift_id": getattr(getattr(a, "shift", None), "id", None),
            "collection_total": _money(sum((c.amount for c in collections), Decimal("0.00"))),
            "confirmed_remittance_total": _money(confirmed_receipts),
            "pending_remittance_total": _money(pending_remittance),
            "collections": [{"id":c.id,"amount":_money(c.amount),"notes":c.notes,"recorded_at":c.recorded_at} for c in collections],
            "expenses": [{"id":e.id,"category":e.category,"amount":_money(e.amount),"notes":e.notes,"status":e.status,"created_at":e.created_at} for e in expenses],
            "expense_total_reported": _money(sum((e.amount for e in expenses), Decimal("0.00"))),
            "shift_status": shift_status,
            "closure": _closure_data(closure) if closure else None}


def _closure_data(closure):
    return {"closed_at":closure.closed_at,"reported_gross":_money(closure.reported_gross),
        "approved_expenses":_money(closure.approved_expenses),
        "deductible_expenses":_money(closure.deductible_expenses),
        "expected_remittance":_money(closure.expected_remittance) if closure.expected_remittance is not None else None,
        "deduction_rule_version":closure.deduction_rule_version,
        "calculation_status":closure.calculation_status,"calculation_note":closure.calculation_note}


def _remittance_data(remittance):
    payments=list(remittance.payments.prefetch_related("allocations__transaction").order_by("created_at"))
    journals = transport_journals(p.pk for p in payments)
    from .services.transport_payments import remittance_balance as _rb
    balance = _rb(remittance, payments)
    received = balance.received
    outstanding = balance.outstanding
    # Crew can pay if there is an outstanding balance and no pending attempt is
    # currently in-flight (pending attempts are already counted in reserved).
    can_pay = balance.available_to_pay > Decimal("0.00")
    return {"id":str(remittance.public_id),"payment_reference":remittance.payment_reference,
        "assignment":remittance.assignment_id,"vehicle":remittance.assignment.vehicle_label,"route":remittance.assignment.route_label,
        "amount":_money(remittance.amount),"reported_amount":_money(remittance.amount),"received_amount":_money(received),
        "outstanding_amount":_money(outstanding),"available_to_pay":_money(balance.available_to_pay),"can_pay":can_pay,
        "status":remittance.status,
        "payments":[{"id":p.id,"method":p.method,"status":p.status,"amount":_money(p.amount),
            "reported_amount":_money(p.amount),"received_amount":_money(p.received_amount) if p.received_amount is not None else None,
            "unallocated_amount":_money(max(Decimal("0.00"), p.unallocated_amount - Decimal(
                transport_accounting_data(p, journals)["journal_allocated_amount"]
            ))),
            **transport_accounting_data(p, journals),
            "receipt":p.mpesa_receipt,
            "provider_reference":p.provider_reference,"created_at":p.created_at,
            # Only expose account activity backed by a linked ledger transaction
            # and a confirmed receipt. Transport reports and pending amounts are
            # never presented as account credits.
            "account_activity":[{
                "allocation_id":allocation.pk,
                "category":allocation.category,
                "allocated_amount":_money(allocation.amount),
                "rule_version":allocation.rule_version or None,
                "transaction_id":allocation.transaction_id,
                "transaction_type":allocation.transaction.type,
                "account_type":allocation.transaction.account_type or "unclassified",
                "transaction_amount":_money(allocation.transaction.amount),
                "posted_at":allocation.transaction.created_at,
            } for allocation in p.allocations.all()
                if allocation.transaction_id and (p.confirmed_at or p.status == "confirmed")]} for p in payments]}


def _owner_assignment_filter(user):
    scope = Q(pk__in=[])
    for ownership in VehicleOwnership.objects.filter(owner=user):
        clause = Q(vehicle_id=ownership.vehicle_id, starts_at__gte=ownership.starts_at)
        if ownership.ends_at:
            clause &= Q(starts_at__lt=ownership.ends_at)
        scope |= clause
    return scope


def _owner_vehicle_scope(user, vehicle):
    return VehicleOwnership.objects.filter(owner=user, vehicle=vehicle).exists()


def _owner_assignments(user, vehicle=None):
    scope = _owner_assignment_filter(user)
    qs = CrewAssignment.objects.filter(scope)
    return qs.filter(vehicle=vehicle) if vehicle else qs


def _can_access_remittance(user, remittance):
    if is_staff_manager(user) or has_sacco_permission(user, "payments.reconcile"):
        return True
    if CrewAssignment.objects.filter(pk=remittance.assignment_id).filter(_crew_scope(user)).exists():
        return True
    return has_sacco_permission(user, "transport.read_owned") and _owner_assignments(
        user, remittance.vehicle
    ).filter(pk=remittance.assignment_id).exists()


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def transport_role_assign(request):
    if not is_staff_manager(request.user):
        return Response({"detail":"Authorized operations staff required."}, status=403)
    try:
        user = get_user_model().objects.get(pk=request.data.get("user"), is_active=True)
    except (get_user_model().DoesNotExist, ValueError, TypeError, OverflowError):
        return Response({"detail": "Choose an existing active user."}, status=400)
    if user.pk == request.user.pk:
        return Response({"detail": "You cannot grant a transport role to yourself."}, status=403)
    role = request.data.get("role")
    if role not in (TransportRole.OWNER, TransportRole.DRIVER, TransportRole.CONDUCTOR):
        return Response({"detail": "Select owner, driver, or conductor."}, status=400)
    reason_input = TransportReasonInput(data=request.data)
    if not reason_input.is_valid():
        return _invalid_input(reason_input)
    with transaction.atomic():
        transport_role, created = TransportRole.objects.get_or_create(user=user, role=role)
        if not transport_role.active:
            transport_role.active = True
            transport_role.save(update_fields=["active"])
        grant, _ = TransportRoleGrant.objects.get_or_create(
            user=user, role=role, defaults={"granted_by": request.user},
        )
        AuditLog.log(request.user, "other", f"Transport role {role} for user #{user.id}", {
            "operation": "transport_role_granted", "grant_id": grant.id,
            "reason": reason_input.validated_data["reason"],
        }, request)
    return Response({"user":user.id,"username":user.username,"role":role,"created":created},status=201 if created else 200)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def transport_staff_users(request):
    if is_staff_manager(request.user):
        users=get_user_model().objects.filter(is_active=True).prefetch_related("transport_roles").order_by("username")
    elif "clerk" in staff_roles_for_user(request.user):
        duties = _staff_duties(request.user, "transport_assignment")
        if duties is None:
            return Response({"detail": "Scoped staff duties are unavailable until the staff-access migration is applied."}, status=503)
        if not duties.exists():
            return Response({"detail": "No transport assignment duty is assigned to your account."}, status=403)
        users=get_user_model().objects.filter(
            is_active=True,
            transport_roles__active=True,
            transport_roles__role__in=("driver", "conductor"),
        ).prefetch_related("transport_roles").distinct().order_by("username")
    else:
        return Response({"detail":"System access management or an assigned clerk duty is required."},status=403)
    return Response([{"id":u.id,"username":u.username,"name":u.get_full_name() or u.username,
        "transport_roles":[grant.role for grant in u.transport_roles.all() if grant.active]} for u in users])


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def transport_routes(request):
    if request.method == "GET":
        if not is_staff_manager(request.user):
            if "clerk" not in staff_roles_for_user(request.user):
                return Response({"detail": "Transport assignment management permission required."}, status=403)
            duties = _staff_duties(request.user, "transport_assignment")
            if duties is None:
                return Response({"detail": "Scoped staff duties are unavailable until the staff-access migration is applied."}, status=503)
            if not duties.exists():
                return Response({"detail": "No transport assignment duty is assigned to your account."}, status=403)
        return Response([{"id":r.id,"name":r.name,"origin":r.origin,"destination":r.destination} for r in TransportRoute.objects.filter(active=True)])
    if not is_staff_manager(request.user):
        return Response({"detail":"Authorized operations staff required."}, status=403)
    data=request.data
    name=str(data.get("name", "")).strip()
    if not name: return Response({"detail":"Route name is required."}, status=400)
    route,created=TransportRoute.objects.get_or_create(name=name, defaults={"origin":data.get("origin", ""),"destination":data.get("destination", "")})
    if not created: return Response({"detail":"Route already exists."}, status=409)
    AuditLog.log(request.user,"other",f"Transport route {route.name}",{"operation":"create"},request)
    return Response({"id":route.id,"name":route.name,"origin":route.origin,"destination":route.destination},status=201)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def transport_vehicles(request):
    if request.method == "GET":
        qs=Vehicle.objects.select_related("owner")
        staff_view = is_staff_manager(request.user)
        if not staff_view:
            if "clerk" in staff_roles_for_user(request.user):
                duties = _staff_duties(request.user, "transport_assignment")
                if duties is None:
                    return Response({"detail": "Scoped staff duties are unavailable until the staff-access migration is applied."}, status=503)
                vehicle_ids = list(duties.exclude(vehicle_id__isnull=True).values_list("vehicle_id", flat=True))
                assignment_vehicle_ids = list(CrewAssignment.objects.filter(
                    pk__in=duties.exclude(crew_assignment_id__isnull=True).values_list("crew_assignment_id", flat=True)
                ).values_list("vehicle_id", flat=True))
                qs = qs.filter(pk__in=vehicle_ids + assignment_vehicle_ids)
            elif not TransportRole.objects.filter(user=request.user, role="owner", active=True).exists():
                return Response({"detail":"Transport operations staff or an active vehicle owner role is required."},status=403)
            else:
                qs=qs.filter(ownership_history__owner=request.user).distinct()
        return Response([{"id":v.id,"registration":v.registration,"owner":v.owner_id if staff_view or v.owner_id == request.user.id else None,"owner_name":(v.owner.get_full_name() or v.owner.username) if staff_view or v.owner_id == request.user.id else "No longer owned by you","make_model":v.make_model,"active":v.active} for v in qs])
    if not is_staff_manager(request.user): return Response({"detail":"System transport management permission required."},status=403)
    data=request.data
    try: owner=get_user_model().objects.get(pk=data.get("owner"))
    except Exception: return Response({"detail":"Choose a valid owner user."},status=400)
    if not TransportRole.objects.filter(user=owner,role="owner",active=True).exists(): return Response({"detail":"Owner must have the transport owner role."},status=400)
    reg=str(data.get("registration", "")).strip().upper()
    if not reg: return Response({"detail":"Vehicle registration is required."},status=400)
    if Vehicle.objects.filter(registration=reg).exists(): return Response({"detail":"Vehicle already exists."},status=409)
    vehicle=Vehicle.objects.create(registration=reg,owner=owner,make_model=str(data.get("make_model", ""))[:100])
    AuditLog.log(request.user,"other",f"Transport vehicle {reg}",{"owner_id":owner.id,"operation":"create"},request)
    return Response({"id":vehicle.id,"registration":vehicle.registration,"owner":owner.id},status=201)


def _owner_vehicle_payload(user, vehicle, today_start, today_end):
    ownerships = list(VehicleOwnership.objects.filter(owner=user, vehicle=vehicle).order_by("starts_at"))
    assignments = _owner_assignments(user, vehicle).select_related("route", "driver", "conductor", "vehicle").order_by("-starts_at")
    assignment_ids = assignments.values("id")
    current_owner = vehicle.owner_id == user.id
    now = timezone.now()
    current = assignments.filter(_assignment_open(now)).exclude(shift__status="closed").first() if current_owner else None
    collections = TransportCollection.objects.filter(assignment_id__in=assignment_ids, recorded_at__gte=today_start, recorded_at__lt=today_end)
    gross_today = collections.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    expenses = TransportExpense.objects.filter(assignment_id__in=assignment_ids, created_at__gte=today_start, created_at__lt=today_end)
    expense_today = expenses.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    approved_expenses = expenses.filter(status="approved").aggregate(total=Sum("amount"))["total"]
    remittances = TransportRemittance.objects.filter(assignment_id__in=assignment_ids)
    closures = TransportShiftClosure.objects.filter(shift__assignment_id__in=assignment_ids)
    expected_total = closures.aggregate(total=Sum("expected_remittance"))["total"]
    received_total = Decimal("0.00")
    pending_total = closures.filter(
        remittance__isnull=True, expected_remittance__isnull=False,
    ).aggregate(total=Sum("expected_remittance"))["total"] or Decimal("0.00")
    pending_count = 0
    unknown_confirmed = 0
    for remittance in remittances.prefetch_related("payments"):
        confirmed_payments = [p for p in remittance.payments.all() if p.confirmed_at or p.status == "confirmed" or (p.method == "c2b" and p.status == "unmatched")]
        received = sum((p.received_amount for p in confirmed_payments if p.received_amount is not None), Decimal("0.00"))
        unknown_confirmed += sum(1 for p in confirmed_payments if p.received_amount is None)
        received_total += received
        pending_total += max(Decimal("0.00"), remittance.amount - received)
        pending_count += sum(1 for p in remittance.payments.all() if p.status in {"pending", "needs_review", "unmatched"})
    return {
        "id": vehicle.id,
        "registration": vehicle.registration,
        "make_model": vehicle.make_model,
        "active": vehicle.active,
        "current_owner": current_owner,
        "operational_status": (
            "former_owner" if not current_owner else "inactive" if not vehicle.active
            else "active" if current else "available"
        ),
        "owner_label": (vehicle.owner.get_full_name() or vehicle.owner.username) if current_owner else "No longer owned by you",
        "ownership_periods": [{"starts_at": o.starts_at, "ends_at": o.ends_at} for o in ownerships],
        "current_assignment": _assignment_data(current, include_collections=False) if current else None,
        "assignments": [_assignment_data(a, include_collections=True) for a in assignments[:50]],
        "reported_collections_today": _money(gross_today),
        "reported_expenses_today": _money(expense_today),
        "approved_expenses_today": _money(approved_expenses),
        "expected_remittances": _money(expected_total),
        "expected_amount_unavailable_count": closures.filter(expected_remittance__isnull=True).count(),
        "confirmed_receipts": _money(received_total),
        "pending_remittance_amount": _money(pending_total),
        "payments_needing_review": pending_count,
        "confirmed_payments_with_unavailable_amount": unknown_confirmed,
        "remittances": [_remittance_data(r) for r in remittances.order_by("-created_at")[:20]],
        "ownership_history": [
            {
                "id": row.id,
                "owner_name": row.owner.get_full_name() or row.owner.username,
                "starts_at": row.starts_at.isoformat(),
                "ends_at": row.ends_at.isoformat() if row.ends_at else None,
            }
            for row in vehicle.ownership_history.select_related("owner").order_by("-starts_at")[:20]
        ],
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def transport_owner_dashboard(request):
    if not TransportRole.objects.filter(user=request.user, role="owner", active=True).exists():
        return Response({"detail": "An active vehicle owner role is required."}, status=403)
    now = timezone.localtime()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    vehicles = Vehicle.objects.filter(ownership_history__owner=request.user).select_related("owner").distinct().order_by("registration")
    return Response({"date": today_start.date(), "vehicles": [_owner_vehicle_payload(request.user, v, today_start, today_end) for v in vehicles]})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def transport_owner_vehicle(request, vehicle_id):
    if not TransportRole.objects.filter(user=request.user, role="owner", active=True).exists():
        return Response({"detail": "An active vehicle owner role is required."}, status=403)
    vehicle = Vehicle.objects.select_related("owner").filter(pk=vehicle_id).first()
    if not vehicle or not _owner_vehicle_scope(request.user, vehicle):
        return Response({"detail": "Vehicle not found."}, status=404)
    now = timezone.localtime()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return Response(_owner_vehicle_payload(request.user, vehicle, today_start, today_start + timedelta(days=1)))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def transport_remittance_receipt(request, remittance_id):
    remittance = TransportRemittance.objects.select_related("assignment", "vehicle", "route").filter(public_id=remittance_id).first()
    if not remittance:
        return Response({"detail": "Remittance not found."}, status=404)
    if not _can_access_remittance(request.user, remittance):
        return Response({"detail": "You cannot view this remittance receipt."}, status=403)
    return Response(_remittance_data(remittance))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def transport_vehicle_owner(request, vehicle_id):
    if not is_staff_manager(request.user): return Response({"detail":"System transport management permission required."},status=403)
    try: owner=get_user_model().objects.get(pk=request.data.get("owner"))
    except (get_user_model().DoesNotExist,ValueError,TypeError): return Response({"detail":"Choose an existing owner."},status=400)
    if not TransportRole.objects.filter(user=owner,role="owner",active=True).exists(): return Response({"detail":"New owner must hold the transport owner role."},status=400)
    with transaction.atomic():
        vehicle=Vehicle.objects.select_for_update().filter(pk=vehicle_id).first()
        if not vehicle: return Response({"detail":"Vehicle not found."},status=404)
        now=timezone.now()
        active_assignment=CrewAssignment.objects.select_for_update().filter(vehicle=vehicle,starts_at__lte=now).filter(
            Q(ends_at__isnull=True)|Q(ends_at__gt=now)
        ).exists()
        if active_assignment:
            return Response({"detail":"End the vehicle's active crew assignment before changing ownership. This preserves each owner's effective history."},status=409)
        old_owner=vehicle.owner_id
        vehicle.owner=owner
        vehicle.save(update_fields=["owner"])
        VehicleOwnership.objects.filter(vehicle=vehicle,owner=owner,ends_at__isnull=True).update(recorded_by=request.user)
        AuditLog.log(request.user,"other",f"Vehicle #{vehicle.id} ownership changed",{"previous_owner_id":old_owner,"new_owner_id":owner.id},request)
    return Response({"vehicle":vehicle.id,"previous_owner":old_owner,"owner":owner.id})


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def transport_assignments(request):
    if request.method == "GET":
        qs=CrewAssignment.objects.select_related("vehicle","route","driver","conductor")
        if not is_staff_manager(request.user):
            scope = _crew_scope(request.user)
            is_owner = has_sacco_permission(request.user, "transport.read_owned")
            if is_owner:
                scope |= _owner_assignment_filter(request.user)
            if "clerk" in staff_roles_for_user(request.user):
                duties = _staff_duties(request.user, "transport_assignment")
                if duties is None:
                    return Response({"detail": "Scoped staff duties are unavailable until the staff-access migration is applied."}, status=503)
                scoped_ids = duties.exclude(crew_assignment_id__isnull=True).values_list("crew_assignment_id", flat=True)
                vehicle_ids = duties.exclude(vehicle_id__isnull=True).values_list("vehicle_id", flat=True)
                scope |= Q(pk__in=scoped_ids) | Q(vehicle_id__in=vehicle_ids)
            elif not is_owner and scope == Q(pk__in=[]):
                return Response({"detail":"No transport workspace permission is assigned."}, status=403)
            qs = qs.filter(scope)
        return Response([_assignment_data(a) for a in qs[:100]])
    is_manager = is_staff_manager(request.user)
    if not is_manager and not has_sacco_permission(request.user, "transport.assignments.manage_assigned"):
        return Response({"detail": "Transport assignment management permission required."}, status=403)
    serializer = CrewAssignmentInput(data=request.data)
    if not serializer.is_valid():
        return _invalid_input(serializer)
    data = serializer.validated_data
    starts = data["starts_at"]
    ends = data["ends_at"]
    crew_ids = [data["driver"]]
    if data.get("conductor"):
        crew_ids.append(data["conductor"])
    try:
        with transaction.atomic():
            vehicle = Vehicle.objects.select_for_update().filter(pk=data["vehicle"], active=True).first()
            if not vehicle:
                return Response({"detail": "Choose an active vehicle."}, status=400)
            if not is_manager:
                allowed, scope_status = _clerk_has_duty(request.user, "transport_assignment", vehicle=vehicle)
                if scope_status == "schema":
                    return Response({"detail": "Scoped staff duties are unavailable until the staff-access migration is applied."}, status=503)
                if not allowed:
                    return Response({"detail": "This vehicle is not assigned to your transport duties."}, status=403)
            route = TransportRoute.objects.filter(pk=data["route"], active=True).first()
            if not route:
                return Response({"detail": "Choose an active route."}, status=400)
            users = {user.pk: user for user in get_user_model().objects.select_for_update().filter(
                pk__in=crew_ids, is_active=True,
            ).order_by("pk")}
            roles = set(TransportRole.objects.select_for_update().filter(
                user_id__in=crew_ids, active=True,
            ).order_by("pk").values_list("user_id", "role"))
            driver = users.get(data["driver"])
            conductor = users.get(data.get("conductor"))
            if not driver or (driver.pk, TransportRole.DRIVER) not in roles:
                return Response({"detail": "Choose an active account with the driver role."}, status=400)
            if data.get("conductor") and (not conductor or (conductor.pk, TransportRole.CONDUCTOR) not in roles):
                return Response({"detail": "Choose an active account with the conductor role."}, status=400)
            overlapping = CrewAssignment.objects.filter(starts_at__lt=ends).filter(
                Q(ends_at__isnull=True) | Q(ends_at__gt=starts),
                Q(vehicle=vehicle) | Q(driver_id__in=crew_ids) | Q(conductor_id__in=crew_ids),
            )
            if overlapping.exists():
                return Response({"detail": "Vehicle or crew already has an overlapping assignment."}, status=409)
            now = timezone.now()
            status = "ended" if ends <= now else "active" if starts <= now else "scheduled"
            assignment = CrewAssignment.objects.create(
                vehicle=vehicle, route=route, driver=driver, conductor=conductor,
                starts_at=starts, ends_at=ends, status=status, created_by=request.user,
            )
            AuditLog.log(request.user, "other", f"Transport assignment #{assignment.id}", {
                "operation": "create", "vehicle_id": vehicle.id, "route_id": route.id,
                "driver_id": driver.id, "conductor_id": conductor.id if conductor else None,
                "starts_at": starts.isoformat(), "ends_at": ends.isoformat(),
            }, request)
    except OperationalError as exc:
        return _locked_database_response(exc)
    return Response(_assignment_data(assignment), status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def transport_assignment_end(request, assignment_id):
    is_manager = is_staff_manager(request.user)
    if not is_manager and not has_sacco_permission(request.user, "transport.assignments.manage_assigned"):
        return Response({"detail": "Transport assignment management permission required."}, status=403)
    serializer = TransportReasonInput(data=request.data)
    if not serializer.is_valid():
        return _invalid_input(serializer)
    try:
        with transaction.atomic():
            assignment = CrewAssignment.objects.select_for_update().filter(pk=assignment_id).first()
            if not assignment:
                return Response({"detail": "Assignment not found."}, status=404)
            if not is_manager:
                allowed, scope_status = _clerk_has_duty(request.user, "transport_assignment", assignment=assignment)
                if scope_status == "schema":
                    return Response({"detail": "Scoped staff duties are unavailable until the staff-access migration is applied."}, status=503)
                if not allowed:
                    return Response({"detail": "This assignment is outside your transport duties."}, status=403)
            now = timezone.now()
            if _assignment_status(assignment, now) != "active" or assignment.starts_at >= now:
                return Response({"detail": "Only a started assignment that is still active can be ended early."}, status=409)
            previous_end = assignment.ends_at
            assignment.ends_at = now
            assignment.status = "ended"
            assignment.save(update_fields=("ends_at", "status"))
            AuditLog.log(request.user, "other", f"Transport assignment #{assignment.id}", {
                "operation": "end", "reason": serializer.validated_data["reason"],
                "previous_ends_at": previous_end.isoformat() if previous_end else None,
                "ends_at": now.isoformat(),
            }, request)
    except OperationalError as exc:
        return _locked_database_response(exc)
    return Response(_assignment_data(assignment))


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def crew_today(request):
    if request.method == "POST":
        return _save_collection(request)
    now = timezone.localtime()
    scope = _crew_scope(request.user)
    assignments = CrewAssignment.objects.select_related("vehicle", "route", "shift").filter(scope)
    assignment = assignments.filter(_assignment_open(now)).order_by("-starts_at").first()
    can_record_collection = assignment is not None
    if not assignment:
        local_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        local_end = local_start + timedelta(days=1)
        assignment = assignments.filter(
            Q(shift__closure__closed_at__gte=local_start, shift__closure__closed_at__lt=local_end)
            | (Q(ends_at__gte=local_start, ends_at__lte=now, shift__status__in=("scheduled", "active"))
                & (Q(collections__isnull=False) | Q(expenses__isnull=False))),
        ).order_by("-starts_at", "-id").first()
    if not assignment:
        return Response({"assignment":None,"message":"No transport assignment covers today. Contact operations staff to check your crew assignment."})
    return Response({"assignment": _crew_assignment_data(assignment, can_record_collection)})


def _crew_assignment_data(assignment, can_record_collection):
    data = _assignment_data(assignment)
    data["can_record_collection"] = can_record_collection
    data["can_close_shift"] = data["shift_status"] in ("scheduled", "active") and assignment.starts_at <= timezone.now()
    data["remittances"] = [
        _remittance_data(remittance)
        for remittance in assignment.remittances.order_by("-created_at")[:10]
    ]
    return data


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def crew_assignment_detail(request, assignment_id):
    now = timezone.now()
    assignment = CrewAssignment.objects.filter(
        _crew_scope(request.user), pk=assignment_id, starts_at__lte=now,
    ).select_related("vehicle", "route", "shift").first()
    if not assignment:
        return Response({"detail": "This assignment is unavailable to your account."}, status=404)
    can_record_collection = CrewAssignment.objects.filter(_assignment_open(now), pk=assignment.id).exists()
    return Response({"assignment": _crew_assignment_data(assignment, can_record_collection)})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def crew_assignment_history(request):
    """Return only past assignments where this user was assigned crew."""
    if not has_sacco_permission(request.user, "transport.read_assigned"):
        return Response({"detail": "An assigned driver or conductor role is required."}, status=403)
    now = timezone.localtime()
    assignments = CrewAssignment.objects.filter(
        _crew_scope(request.user), starts_at__lt=now,
    ).filter(
        Q(ends_at__lte=now) | Q(status="ended") | Q(shift__status="closed")
    ).select_related("vehicle", "route", "driver", "conductor", "shift").order_by("-starts_at", "-id")[:50]
    return Response([_assignment_data(item) for item in assignments])


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def transport_assignment_issues(request):
    """Crew can report their own assignment issue; clerks see only assigned issues."""
    if request.method == "POST":
        message = str(request.data.get("message", "")).strip()
        assignment_id = request.data.get("assignment_id")
        if not message or len(message) > 500:
            return Response({"detail": "Describe the assignment problem in 1–500 characters."}, status=400)
        if not TransportRole.objects.filter(user=request.user, role__in=("driver", "conductor"), active=True).exists():
            return Response({"detail": "Only assigned transport crew can report an assignment issue."}, status=403)
        assignment = None
        if assignment_id:
            try:
                assignment = CrewAssignment.objects.filter(_crew_scope(request.user), pk=assignment_id).first()
            except (ValueError, TypeError, OverflowError):
                return Response({"detail": "Choose a valid assignment."}, status=400)
            if not assignment:
                return Response({"detail": "That assignment is not available to your account."}, status=404)
        issue = TransportAssignmentIssue.objects.create(
            reported_by=request.user, assignment=assignment, message=message,
        )
        AuditLog.log(request.user, "other", f"Transport assignment issue #{issue.pk}", {
            "operation": "transport_issue_reported", "issue_id": issue.pk,
            "assignment_id": assignment.pk if assignment else None,
        }, request)
        return Response({"id": issue.pk, "status": issue.status}, status=201)

    if is_staff_manager(request.user):
        issues = TransportAssignmentIssue.objects.select_related("reported_by", "assignment").all()
    elif "clerk" in staff_roles_for_user(request.user):
        duties = _staff_duties(request.user, "transport_issue")
        if duties is None:
            return Response({"detail": "Scoped staff duties are unavailable until the staff-access migration is applied."}, status=503)
        issue_ids = duties.values_list("transport_issue_id", flat=True)
        issues = TransportAssignmentIssue.objects.select_related("reported_by", "assignment").filter(pk__in=issue_ids)
    elif TransportRole.objects.filter(user=request.user, role__in=("driver", "conductor"), active=True).exists():
        issues = TransportAssignmentIssue.objects.select_related("reported_by", "assignment").filter(reported_by=request.user)
    else:
        return Response({"detail": "No transport issue workspace is assigned to your account."}, status=403)
    return Response([{
        "id": issue.pk, "assignment_id": issue.assignment_id,
        "vehicle": issue.assignment.vehicle_label if issue.assignment else None,
        "route": issue.assignment.route_label if issue.assignment else None,
        "reported_by": issue.reported_by.get_full_name() or issue.reported_by.username,
        "message": issue.message, "status": issue.status,
        "resolution_reason": issue.resolution_reason,
        "created_at": issue.created_at, "resolved_at": issue.resolved_at,
    } for issue in issues.order_by("-created_at")[:200]])


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def transport_assignment_issue_resolve(request, issue_id):
    if not is_staff_manager(request.user) and not has_sacco_permission(request.user, "transport.issues.review_assigned"):
        return Response({"detail": "An assigned clerk duty is required to resolve an assignment issue."}, status=403)
    reason = str(request.data.get("reason", "")).strip()
    if len(reason) < 10 or len(reason) > 500:
        return Response({"detail": "Provide a resolution reason of 10–500 characters."}, status=400)
    with transaction.atomic():
        issue = TransportAssignmentIssue.objects.select_for_update().filter(pk=issue_id).first()
        if not issue:
            return Response({"detail": "Assignment issue not found."}, status=404)
        if not is_staff_manager(request.user):
            duties = _staff_duties(request.user, "transport_issue")
            if duties is None:
                return Response({"detail": "Scoped staff duties are unavailable until the staff-access migration is applied."}, status=503)
            if not duties.filter(transport_issue_id=issue.pk).exists():
                return Response({"detail": "This issue is not assigned to your account."}, status=403)
        if issue.status != "pending":
            return Response({"detail": "This assignment issue has already been resolved."}, status=409)
        issue.status = "resolved"
        issue.resolution_reason = reason
        issue.resolved_by = request.user
        issue.resolved_at = timezone.now()
        issue.save(update_fields=("status", "resolution_reason", "resolved_by", "resolved_at"))
        AuditLog.log(request.user, "other", f"Transport assignment issue #{issue.pk}", {
            "operation": "transport_issue_resolved", "issue_id": issue.pk, "reason": reason,
        }, request)
    return Response({"id": issue.pk, "status": issue.status})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def transport_expenses(request):
    serializer = TransportExpenseInput(data=request.data)
    if not serializer.is_valid():
        return _invalid_input(serializer)
    data = serializer.validated_data
    if data.get("recorded_by", request.user.pk) != request.user.pk:
        return Response({"detail": "This expense belongs to a different signed-in user."}, status=403)

    def replay(previous):
        if (previous.assignment_id, previous.amount, previous.category, previous.notes) != (
            data["assignment"], data["amount"], data["category"], data["notes"],
        ):
            return Response({"detail": "client_key was already used with different expense data."}, status=409)
        return Response(_expense_data(previous) | {"duplicate": True})

    submitted = TransportExpense.objects.filter(reported_by=request.user, client_key=data["client_key"])
    try:
        with transaction.atomic():
            assignment = CrewAssignment.objects.select_for_update().filter(
                pk=data["assignment"],
            ).filter(_crew_scope(request.user)).first()
            if not assignment:
                return Response({"detail": "You are not assigned to this shift."}, status=403)
            previous = submitted.first()
            if previous:
                return replay(previous)
            shift = getattr(assignment, "shift", None)
            if (not shift or shift.status not in ("scheduled", "active") or not assignment.vehicle.active
                    or not assignment.route.active or _assignment_status(assignment, timezone.now()) != "active"):
                return Response({"detail": "This shift is not open for expense reports."}, status=409)
            expense = TransportExpense.objects.create(
                assignment=assignment, shift=shift, vehicle=assignment.vehicle, route=assignment.route,
                reported_by=request.user, client_key=data["client_key"], category=data["category"],
                amount=data["amount"], notes=data["notes"],
            )
            AuditLog.log(request.user, "other", f"Transport expense #{expense.pk}", {
                "operation": "reported", "category": expense.category, "amount": str(expense.amount),
                "shift_id": shift.pk,
            }, request)
    except IntegrityError:
        previous = submitted.first()
        if previous:
            return replay(previous)
        raise
    except OperationalError as exc:
        return _locked_database_response(exc)
    return Response(_expense_data(expense) | {"duplicate": False}, status=201)


def _expense_data(expense):
    return {"id": expense.id, "assignment": expense.assignment_id, "shift": expense.shift_id,
        "category": expense.category, "amount": _money(expense.amount), "notes": expense.notes,
        "status": expense.status, "review_reason": expense.review_reason, "created_at": expense.created_at}


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def transport_expense_queue(request):
    if not has_sacco_permission(request.user, "transport.expenses.review"):
        return Response({"detail": "Authorized expense review staff required."}, status=403)
    expenses = TransportExpense.objects.filter(status="reported").select_related("assignment", "vehicle", "route", "reported_by").order_by("created_at")[:250]
    return Response([_expense_data(expense) | {"vehicle_registration": expense.assignment.vehicle_label,
        "route_name": expense.assignment.route_label, "reported_by": expense.reported_by.get_full_name() or expense.reported_by.username} for expense in expenses])


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def transport_expense_review(request, expense_id):
    if not has_sacco_permission(request.user, "transport.expenses.review"):
        return Response({"detail": "Authorized expense review staff required."}, status=403)
    action = request.data.get("action")
    reason = str(request.data.get("reason", "")).strip()
    if action not in ("approve", "reject") or not reason:
        return Response({"detail": "Choose approve or reject and provide a reason."}, status=400)
    with transaction.atomic():
        assignment_id = TransportExpense.objects.filter(pk=expense_id).values_list("assignment_id", flat=True).first()
        if not assignment_id:
            return Response({"detail": "Expense not found."}, status=404)
        CrewAssignment.objects.select_for_update().get(pk=assignment_id)
        expense = TransportExpense.objects.select_for_update().get(pk=expense_id)
        if expense.reported_by_id == request.user.pk:
            return Response({"detail": "A reviewer cannot review their own expense."}, status=403)
        if expense.shift.status == "closed" and action == "approve":
            return Response({"detail": "A closed shift cannot gain a new approved expense."}, status=409)
        if expense.status != "reported":
            return Response({"detail": "This expense was already reviewed."}, status=409)
        expense.status = "approved" if action == "approve" else "rejected"
        expense.reviewed_by = request.user
        expense.reviewed_at = timezone.now()
        expense.review_reason = reason[:500]
        expense.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_reason"])
        AuditLog.log(request.user, "other", f"Transport expense #{expense.id}",
            {"operation": action, "reason": reason[:500], "amount": str(expense.amount)}, request)
    return Response(_expense_data(expense))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def transport_shift_close(request):
    try:
        assignment_id = int(request.data.get("assignment"))
    except (TypeError, ValueError):
        return Response({"detail": "A valid assignment is required."}, status=400)
    with transaction.atomic():
        assignment = CrewAssignment.objects.select_for_update().filter(pk=assignment_id).first()
        if not assignment:
            return Response({"detail": "Assignment not found."}, status=404)
        is_crew = CrewAssignment.objects.filter(pk=assignment_id).filter(_crew_scope(request.user)).exists()
        if not is_crew:
            allowed, scope_status = _clerk_has_duty(request.user, "transport_assignment", assignment=assignment)
            if scope_status == "schema":
                return Response({"detail": "Scoped staff duties are unavailable until the staff-access migration is applied."}, status=503)
            if not allowed:
                return Response({"detail": "Only assigned crew or a clerk assigned to this work may close this shift."}, status=403)
        shift = getattr(assignment, "shift", None)
        if not shift:
            return Response({"detail": "Shift record is unavailable; ask operations staff."}, status=409)
        existing = TransportShiftClosure.objects.filter(shift=shift).first()
        if existing:
            return Response(_closure_data(existing) | {"duplicate": True}, status=200)
        now = timezone.now()
        if assignment.starts_at > now:
            return Response({"detail": "This shift has not started yet."}, status=409)
        # Assignment periods are constrained to end strictly after start. If a
        # request lands on the exact start instant, advance the close timestamp
        # by the database's smallest practical precision rather than returning
        # an IntegrityError from the constraint.
        if assignment.starts_at == now:
            now = assignment.starts_at + timedelta(microseconds=1)
        if shift.status not in ("scheduled", "active"):
            return Response({"detail": "This shift is not open for closure."}, status=409)
        if shift.expenses.filter(status="reported").exists():
            return Response({"detail": "Staff must review all reported expenses before this shift can close."}, status=409)
        from core.services.transport_operations import calculate_shift_closure
        amounts = calculate_shift_closure(shift)
        closure = TransportShiftClosure.objects.create(shift=shift, closed_by=request.user,
            closed_at=now, reported_gross=amounts.reported_gross,
            approved_expenses=amounts.approved_expenses,
            deductible_expenses=amounts.deductible_expenses,
            expected_remittance=amounts.expected_remittance,
            deduction_rule_version=amounts.rule_version,
            calculation_status=amounts.status, calculation_note=amounts.note)
        shift.status = "closed"
        shift.ends_at = min(shift.ends_at, now) if shift.ends_at else now
        shift.save(update_fields=["status", "ends_at"])
        assignment.status = "ended"
        assignment.ends_at = min(assignment.ends_at, now) if assignment.ends_at else now
        assignment.save(update_fields=["status", "ends_at"])
        AuditLog.log(request.user, "other", f"Transport shift #{shift.id}",
            {"operation": "close", "reported_gross": str(amounts.reported_gross),
             "approved_expenses": str(amounts.approved_expenses),
             "expected_remittance": str(amounts.expected_remittance) if amounts.expected_remittance is not None else None,
             "calculation_status": amounts.status}, request)
    return Response(_closure_data(closure) | {"shift_id": shift.id, "duplicate": False}, status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def transport_shift_recalculate(request, assignment_id):
    if not has_sacco_permission(request.user, "transport.expenses.review"):
        return Response({"detail": "Authorized expense review staff required."}, status=403)
    serializer = TransportReasonInput(data=request.data)
    if not serializer.is_valid():
        return _invalid_input(serializer)
    try:
        with transaction.atomic():
            assignment = CrewAssignment.objects.select_for_update().filter(pk=assignment_id).first()
            if not assignment:
                return Response({"detail": "Assignment not found."}, status=404)
            closure = TransportShiftClosure.objects.select_for_update().filter(shift__assignment=assignment).first()
            if not closure:
                return Response({"detail": "Close the shift before recalculating its remittance."}, status=409)
            if closure.expected_remittance is not None or closure.shift.remittances.exists():
                return Response({"detail": "A calculated or requested remittance needs a separate review."}, status=409)
            if closure.shift.expenses.filter(status="reported").exists():
                return Response({"detail": "Review all reported expenses before recalculating this shift."}, status=409)
            from core.services.transport_operations import calculate_shift_closure
            amounts = calculate_shift_closure(closure.shift)
            if amounts.expected_remittance is None:
                return Response({"detail": amounts.note}, status=409)
            closure.deductible_expenses = amounts.deductible_expenses
            closure.expected_remittance = amounts.expected_remittance
            closure.deduction_rule_version = amounts.rule_version
            closure.calculation_status = amounts.status
            closure.calculation_note = amounts.note
            closure.save(update_fields=(
                "deductible_expenses", "expected_remittance", "deduction_rule_version",
                "calculation_status", "calculation_note",
            ))
            AuditLog.log(request.user, "other", f"Transport shift #{closure.shift_id}", {
                "operation": "recalculate", "reason": serializer.validated_data["reason"],
                "deduction_rule_version": amounts.rule_version,
                "expected_remittance": str(amounts.expected_remittance),
            }, request)
    except OperationalError as exc:
        return _locked_database_response(exc)
    return Response(_closure_data(closure) | {"shift_id": closure.shift_id})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def transport_remittance_create(request):
    from .services.transport_payments import payment_amount

    data=request.data
    try:
        key=uuid.UUID(str(data.get("client_key")))
        amount=payment_amount(data.get("amount"), allow_zero=True)
        assignment_id = int(str(data.get("assignment")))
        if not 0 < assignment_id <= 2**63 - 1:
            raise ValueError
        assignment=CrewAssignment.objects.select_related("vehicle","route").get(pk=assignment_id)
    except (ValueError, TypeError, CrewAssignment.DoesNotExist):
        return Response({"detail":"Valid assignment, amount, and UUID client_key are required."},status=400)
    if not CrewAssignment.objects.filter(pk=assignment.pk).filter(_crew_scope(request.user)).exists():
        return Response({"detail":"Only the assigned driver or conductor may create this remittance."},status=403)
    previous=TransportRemittance.objects.filter(requested_by=request.user,idempotency_key=key).first()
    if previous:
        if previous.assignment_id!=assignment.id or previous.amount!=amount:return Response({"detail":"client_key was used with different remittance data."},status=409)
        return Response(_remittance_data(previous) | {"duplicate": True})
    shift=getattr(assignment,"shift",None)
    if not shift:return Response({"detail":"Shift record is unavailable; ask operations staff."},status=409)
    closure=TransportShiftClosure.objects.filter(shift=shift).first()
    if not closure:
        return Response({"detail":"Close the shift before creating its remittance."},status=409)
    if closure.expected_remittance is None:
        return Response({"detail":closure.calculation_note or "An approved deduction rule is required before calculating the remittance."},status=409)
    if amount != closure.expected_remittance:
        return Response({"detail":"Remittance must match the calculated expected amount.","expected_remittance":str(closure.expected_remittance)},status=409)
    try:
        with transaction.atomic():
            closure=TransportShiftClosure.objects.select_for_update().get(pk=closure.pk)
            existing=TransportRemittance.objects.filter(shift=shift).first()
            if existing and existing.closure_id != closure.id:
                return Response({"detail":"An earlier remittance exists for this shift and needs staff review before linking the closure."},status=409)
            if existing:
                return Response(_remittance_data(existing)|{"duplicate":True},status=200)
            remittance=TransportRemittance.objects.create(closure=closure,requested_by=request.user,payer=request.user,assignment=assignment,shift=shift,
                vehicle=assignment.vehicle,route=assignment.route,amount=closure.expected_remittance,idempotency_key=key,
                status="pending" if amount else "confirmed")
            AuditLog.log(request.user,"other",f"Transport remittance {remittance.public_id}",{"operation":"request","amount":str(amount)},request)
    except IntegrityError:
        previous = TransportRemittance.objects.filter(requested_by=request.user, idempotency_key=key).first()
        if previous and (previous.assignment_id != assignment.pk or previous.amount != amount):
            return Response({"detail":"client_key was used with different remittance data."},status=409)
        remittance=TransportRemittance.objects.filter(closure=closure).first()
        if not remittance:return Response({"detail":"A remittance request already exists; refresh the shift."},status=409)
        return Response(_remittance_data(remittance)|{"duplicate":True},status=200)
    except OperationalError as exc:
        return _locked_database_response(exc)
    return Response(_remittance_data(remittance),status=201)


def _submit_transport_attempt(request, remittance_id, method):
    from .services.daraja_service import DarajaError, initiate_stk_push, to_safaricom_phone
    from .services.transport_payments import payment_amount, record_stk_initiation, refresh_remittance, remittance_balance, stk_callback_tag

    remittance = TransportRemittance.objects.filter(public_id=remittance_id).first()
    if not remittance:
        return Response({"detail": "Remittance not found."}, status=404)
    if not CrewAssignment.objects.filter(pk=remittance.assignment_id).filter(_crew_scope(request.user)).exists():
        return Response({"detail": "Only authorized assigned crew may submit a payment."}, status=403)
    phone = ""
    try:
        key = uuid.UUID(str(request.data.get("client_key")))
        amount = payment_amount(request.data.get("amount", remittance.amount))
        if method == "stk":
            if amount != amount.to_integral_value():
                return Response({"detail": "M-Pesa STK requests require a whole-KES amount."}, status=400)
            member = getattr(request.user, "member_profile", None)
            phone = to_safaricom_phone(str(request.data.get("phone") or (member.phone_number if member else "")))
    except (ValueError, DarajaError):
        return Response({"detail": "Provide a valid amount, payment UUID and M-Pesa phone where applicable."}, status=400)

    def replay(previous):
        if (previous.remittance_id, previous.method, previous.amount, previous.payer_phone) != (
            remittance.pk, method, amount, phone,
        ):
            return Response({"detail": "client_key was used for a different payment request."}, status=409)
        return Response(_attempt_data(previous, duplicate=True))

    try:
        with transaction.atomic():
            remittance = TransportRemittance.objects.select_for_update().get(pk=remittance.pk)
            previous = TransportPayment.objects.filter(requested_by=request.user, idempotency_key=key).first()
            if previous:
                return replay(previous)
            if method == "stk" and not all(getattr(settings, name, "") for name in (
                "MPESA_CONSUMER_KEY", "MPESA_CONSUMER_SECRET", "MPESA_PASSKEY", "MPESA_CALLBACK_BASE_URL",
            )):
                return Response({"detail": "Configure the Daraja credentials and callback URL to request M-Pesa payments."}, status=503)
            if amount > remittance_balance(remittance).available_to_pay:
                return Response({"detail": "This amount exceeds the balance available to pay. Review earlier attempts."}, status=409)
            payment = TransportPayment.objects.create(
                remittance=remittance, requested_by=request.user, payer=request.user, idempotency_key=key,
                method=method, status="pending", amount=amount, payer_phone=phone,
                requires_signed_callback=method == "stk",
            )
            refresh_remittance(remittance)
            AuditLog.log(request.user, "other", f"Transport payment #{payment.pk}", {
                "operation": "request", "method": method, "amount": str(amount),
            }, request)
    except IntegrityError:
        previous = TransportPayment.objects.filter(requested_by=request.user, idempotency_key=key).first()
        if previous:
            return replay(previous)
        raise
    except OperationalError as exc:
        return _locked_database_response(exc)

    if method == "cash":
        return Response(_attempt_data(payment), status=201)
    try:
        result = initiate_stk_push(
            phone=phone, amount=int(amount), account_ref=remittance.payment_reference,
            transaction_desc="Transport remit", callback_tag=stk_callback_tag(payment),
        )
    except (DarajaError, ValueError, TypeError):
        payment = record_stk_initiation(payment)
        return Response(_attempt_data(payment) | {
            "detail": "The payment attempt was saved. Check its status before requesting another payment.",
        }, status=202)
    payment = record_stk_initiation(payment, result)
    return Response(_attempt_data(payment), status=201)


def _attempt_data(payment, duplicate=False):
    return {"id": payment.pk, "payment_id": payment.pk, "status": payment.status,
            "reported_amount": _money(payment.amount),
            "received_amount": _money(payment.received_amount) if payment.received_amount is not None else None,
            "checkout_request_id": payment.provider_reference or None, "duplicate": duplicate}


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def transport_remittance_stk(request, remittance_id):
    return _submit_transport_attempt(request, remittance_id, "stk")


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def transport_cash_handover(request, remittance_id):
    return _submit_transport_attempt(request, remittance_id, "cash")


@api_view(["GET","POST"])
@permission_classes([IsAuthenticated])
def transport_payment_queue(request):
    from accounting.services import _authorized_accountant
    from .services.transport_accounting import record_transport_receipt
    from .services.transport_payments import payment_amount, refresh_remittance, remittance_balance, verified_amount

    is_treasurer = has_sacco_permission(request.user, "payments.reconcile")
    is_clerk = "clerk" in staff_roles_for_user(request.user)
    if not is_treasurer and not is_clerk:
        return Response({"detail":"Payment queue access requires treasury reconciliation or a clerk assignment."},status=403)
    if request.method=="GET":
        cash_duties = _staff_duties(request.user, "cash_handover") if is_clerk else None
        if is_clerk and cash_duties is None:
            return Response({"detail":"Scoped staff duties are unavailable until the staff-access migration is applied."},status=503)
        clerk_assignment_ids = set(cash_duties.values_list("crew_assignment_id", flat=True)) if cash_duties is not None else set()
        clerk_vehicle_ids = set(cash_duties.values_list("vehicle_id", flat=True)) if cash_duties is not None else set()
        threshold = timezone.now() - timedelta(hours=max(1, int(getattr(settings, "TRANSPORT_PAYMENT_LATE_AFTER_HOURS", 24))))
        qs=TransportPayment.objects.select_related("remittance").filter(
            Q(status__in=("pending","needs_review","unmatched"))|
            Q(remittance__status__in=("partial","needs_review"))|
            Q(status="confirmed", received_amount__isnull=True)
            | (Q(received_amount__gt=0) if is_treasurer else Q(pk__in=[]))
        ).order_by("-created_at", "-pk")
        if not is_treasurer:
            qs = qs.filter(method="cash").filter(
                Q(remittance__assignment_id__in=clerk_assignment_ids) | Q(remittance__vehicle_id__in=clerk_vehicle_ids),
            )
        qs = list(qs.prefetch_related("remittance__payments")[:250])
        journals = transport_journals(p.pk for p in qs) if is_treasurer else {}
        can_post = is_treasurer and _authorized_accountant(request.user)
        items=[]
        for p in qs:
            accounting = transport_accounting_data(p, journals) if is_treasurer else {}
            received = verified_amount(p)
            in_clerk_scope = p.remittance_id and (
                p.remittance.assignment_id in clerk_assignment_ids or p.remittance.vehicle_id in clerk_vehicle_ids
            )
            reasons=[]
            if p.status == "unmatched": reasons.append("unmatched")
            if p.remittance_id and p.remittance.status == "partial": reasons.append("partial")
            if p.remittance_id and p.remittance.status == "needs_review" and remittance_balance(p.remittance).received > p.remittance.amount:
                reasons.append("excess")
            if p.status == "needs_review" or (p.remittance_id and p.remittance.status == "needs_review"): reasons.append("uncertain_or_disputed")
            if p.status == "pending" and p.created_at <= threshold: reasons.append("late")
            if p.confirmed_at and p.received_amount is None: reasons.append("legacy_confirmed_amount_unavailable")
            if accounting.get("accounting_status") == "awaiting_journal": reasons.append("receipt_posting_required")
            items.append({"kind":"payment","id":p.id,"status":p.status,"method":p.method,
                "reported_amount":_money(p.amount),
                "received_amount":_money(received) if received is not None else None,
                "receipt":p.mpesa_receipt,"reference":p.remittance.payment_reference if p.remittance else p.provider_reference,
                "remittance":str(p.remittance.public_id) if p.remittance else None,
                "remittance_status":p.remittance.status if p.remittance else None,
                "expected_amount":_money(p.remittance.amount) if p.remittance else None,
                **accounting,
                "can_allocate": bool(can_post
                    and p.status == "confirmed" and p.remittance_id and p.remittance.status == "confirmed"
                    and accounting.get("accounting_status") == "posted" and not accounting.get("allocation_journal_id")),
                "can_match": bool(is_treasurer and not p.remittance_id and received is not None),
                "can_review": bool(is_treasurer and p.status in {"pending", "confirmed"}),
                "can_resolve": bool(is_treasurer and p.status == "needs_review" and received is not None and p.remittance_id),
                "can_post_receipt": bool(can_post and received is not None and accounting.get("accounting_status") == "awaiting_journal"),
                "can_release_attempt": bool(is_treasurer and p.status in {"pending", "needs_review"} and received is None),
                "review_reason":p.review_reason,"queue_reasons":reasons,"created_at":p.created_at,
                "can_confirm_cash":bool(is_clerk and in_clerk_scope and p.method=="cash" and p.status=="pending" and not p.confirmed_at and request.user.pk not in (p.requested_by_id, p.payer_id))})
        for event in (TransportPaymentReviewEvent.objects.filter(status="pending").order_by("created_at")[:250] if is_treasurer else []):
            items.append({"kind":"duplicate_callback","event_id":event.id,"status":"needs_review",
                "method":"M-Pesa callback","reported_amount":_money(event.observed_amount) if event.observed_amount is not None else None,
                "received_amount":None,"receipt":event.receipt,"reference":event.provider_reference,
                "remittance":None,"review_reason":event.reason,"queue_reasons":["duplicate_or_conflicting_callback"],
                "created_at":event.created_at,"can_confirm_cash":False})
        items.sort(key=lambda item: item["created_at"])
        return Response(items[:500])

    reason_input = TransportReasonInput(data=request.data)
    if not reason_input.is_valid():return _invalid_input(reason_input)
    reason = reason_input.validated_data["reason"]
    body = request.data
    commands = [name for name in ("confirm", "review", "resolve", "post_receipt") if body.get(name) is True]
    if body.get("event_id") is not None:
        commands.append("resolve_event")
    if body.get("remittance_id"):
        commands.append("match")
    if body.get("action") == "release_attempt":
        commands.append("release_attempt")
    if len(commands) != 1:
        return Response({"detail": "Choose one reconciliation action."}, status=400)
    command = commands[0]
    cash_confirmation = command == "confirm"
    if cash_confirmation and not is_clerk:
        return Response({"detail":"Only an assigned transport clerk may confirm a cash handover."},status=403)
    if not cash_confirmation and not is_treasurer:
        return Response({"detail":"Payment matching and exception review require treasury reconciliation permission."},status=403)
    if command == "post_receipt" and not _authorized_accountant(request.user):
        return Response({"detail": "Accounting posting permission is required."}, status=403)
    try:
        item_id = int(str(body.get("event_id" if command == "resolve_event" else "payment_id")))
        if not 0 < item_id <= 2**63 - 1:
            raise ValueError
    except (ValueError, TypeError):
        return Response({"detail": "Provide a valid payment or callback event identifier."}, status=400)
    if command == "resolve_event":
        with transaction.atomic():
            event=TransportPaymentReviewEvent.objects.select_for_update().filter(pk=item_id).first()
            if not event:return Response({"detail":"Payment review event not found."},status=404)
            if event.status != "pending":return Response({"detail":"This callback event was already reviewed."},status=409)
            event.status="resolved";event.resolution_reason=reason[:500];event.resolved_by=request.user;event.resolved_at=timezone.now()
            event.save(update_fields=["status","resolution_reason","resolved_by","resolved_at"])
            AuditLog.log(request.user,"other",f"Transport payment callback event #{event.id}",{"operation":"review_duplicate_callback","reason":reason[:500]},request)
        return Response({"event_id":event.id,"status":event.status})

    with transaction.atomic():
        original = TransportPayment.objects.filter(pk=item_id).first()
        if not original:return Response({"detail":"Payment not found."},status=404)
        target = None
        if command == "match":
            reference = str(body.get("remittance_id")).strip()
            try:
                target = TransportRemittance.objects.filter(public_id=uuid.UUID(reference)).first()
            except ValueError:
                target = TransportRemittance.objects.filter(payment_reference=reference.upper()).first()
            if not target:return Response({"detail":"Target remittance not found."},status=404)
        locked = {row.pk: row for row in TransportRemittance.objects.select_for_update().filter(
            pk__in=[pk for pk in (original.remittance_id, target.pk if target else None) if pk]
        ).order_by("pk")}
        payment=TransportPayment.objects.select_for_update().filter(pk=item_id).first()
        if not payment:return Response({"detail":"Payment not found."},status=404)
        if payment.remittance_id != original.remittance_id:
            return Response({"detail": "Another staff member matched this payment. Refresh and try again."}, status=409)
        if target:
            if payment.remittance_id and payment.remittance_id != target.id:
                return Response({"detail":"This receipt already has a remittance. Use the accounting correction workflow."},status=409)
            if verified_amount(payment) is None:
                return Response({"detail": "Only a verified receipt can be matched."}, status=409)
            payment.remittance=target
            if payment.status == "unmatched":
                payment.status = "confirmed"
        if cash_confirmation:
            if request.user.pk in (payment.requested_by_id, payment.payer_id):
                return Response({"detail": "A clerk cannot confirm their own cash handover."}, status=403)
            if payment.method != "cash":
                return Response({"detail":"Electronic payments can only be confirmed by the payment provider callback."},status=409)
            if not payment.remittance_id:
                return Response({"detail":"An unmatched cash handover must be matched by treasury before a clerk can confirm it."},status=409)
            assigned, scope_status = _clerk_has_duty(request.user, "cash_handover", assignment=payment.remittance.assignment)
            if scope_status == "schema":
                return Response({"detail":"Scoped staff duties are unavailable until the staff-access migration is applied."},status=503)
            if not assigned:
                return Response({"detail":"This handover is outside your assigned clerk duties."},status=403)
            if payment.status != "pending" or payment.confirmed_at:
                return Response({"detail":"Only a pending cash handover can be confirmed."},status=409)
            try:
                received_amount = payment_amount(body.get("received_amount"))
            except ValueError:
                return Response({"detail":"Enter the amount the clerk physically counted."},status=400)
            payment.confirmed_by=request.user
            payment.confirmed_at=timezone.now()
            payment.received_amount=received_amount
            payment.unallocated_amount=received_amount
            if received_amount != payment.amount:
                payment.status="needs_review"
                payment.review_reason=(f"Reported KES {payment.amount}; clerk counted KES {received_amount}. "
                    f"{reason[:400]}")
            else:
                payment.status="confirmed"
                payment.review_reason=reason[:500]
        elif command == "review":
            if payment.status not in {"pending", "confirmed", "needs_review"}:
                return Response({"detail": "This payment cannot be marked disputed."}, status=409)
            payment.status="needs_review"
        elif command == "resolve":
            if payment.status != "needs_review" or not payment.remittance_id or verified_amount(payment) is None:
                return Response({"detail": "Only a matched and verified receipt dispute can be resolved here."}, status=409)
            payment.status = "confirmed"
        elif command == "release_attempt":
            if verified_amount(payment) is not None or payment.status not in {"pending", "needs_review"}:
                return Response({"detail": "Only an unverified attempt can be released."}, status=409)
            payment.status = "failed"
        elif command == "post_receipt" and verified_amount(payment) is None:
            return Response({"detail": "Verify receipt of funds before posting."}, status=409)
        if not cash_confirmation and command != "post_receipt":
            payment.review_reason=reason
        payment.save(update_fields=["remittance","status","confirmed_by","confirmed_at","received_amount","unallocated_amount","review_reason"])
        if payment.remittance_id:
            refresh_remittance(locked[payment.remittance_id])
        if command in {"confirm", "match", "post_receipt"} and verified_amount(payment) is not None:
            accounting_status = record_transport_receipt(payment, actor=request.user)
        else:
            accounting_status = transport_accounting_data(payment, transport_journals([payment.pk]))["accounting_status"]
        AuditLog.log(request.user,"other",f"Transport payment #{payment.id}",{
            "operation":command,"status":payment.status,"reason":reason,"remittance_id":payment.remittance_id,
            "received_amount":str(payment.received_amount) if payment.received_amount is not None else None,
            "accounting_status":accounting_status,
        },request)
    if command == "post_receipt" and accounting_status not in {"posted", "reversed"}:
        return Response({"detail": "The verified receipt still needs accounting configuration or review.",
                         "accounting_status": accounting_status}, status=409)
    return Response({"id":payment.id,"status":payment.status,"remittance":str(payment.remittance.public_id) if payment.remittance else None,
        "received_amount":str(payment.received_amount) if payment.received_amount is not None else None,
        "accounting_status": accounting_status})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def record_collection(request):
    return _save_collection(request)


def _save_collection(request):
    serializer = TransportCollectionInput(data=request.data)
    if not serializer.is_valid():
        return _invalid_input(serializer)
    data = serializer.validated_data
    if data.get("recorded_by", request.user.pk) != request.user.pk:
        return Response({"detail": "This draft belongs to a different account."}, status=403)
    assignment_id = data["assignment"]
    collection_query = TransportCollection.objects.filter(recorded_by=request.user, client_key=data["client_key"])
    try:
        with transaction.atomic():
            # Lock only the assignment row. PostgreSQL rejects FOR UPDATE of
            # the nullable side of an outer join such as assignment -> shift.
            assignment = CrewAssignment.objects.select_for_update().filter(
                pk=assignment_id,
            ).filter(Q(driver=request.user) | Q(conductor=request.user)).first()
            if not assignment or not CrewAssignment.objects.filter(_crew_scope(request.user), pk=assignment_id).exists():
                return Response({"detail": "You are not assigned to this shift."}, status=403)
            # Resolve the same key before eligibility, so a saved collection
            # can be replayed even when the shift has since ended or closed.
            existing = collection_query.first()
            if existing:
                return _collection_replay(existing, data)
            if not CrewAssignment.objects.filter(_assignment_open(timezone.now()), pk=assignment_id).exists():
                return Response({"detail": "This shift is no longer open for collections."}, status=409)
            collection = TransportCollection.objects.create(
                assignment=assignment, recorded_by=request.user, client_key=data["client_key"],
                amount=data["amount"], notes=data["notes"],
            )
    except IntegrityError:
        existing = collection_query.first()
        if not existing:
            raise
        return _collection_replay(existing, data)
    except OperationalError as exc:
        return _locked_database_response(exc)
    return Response(_collection_data(collection, duplicate=False), status=201)


def _collection_replay(collection, data):
    if (collection.assignment_id, collection.amount, collection.notes) != (
        data["assignment"], data["amount"], data["notes"],
    ):
        return Response({"detail": "client_key was already used for a different collection."}, status=409)
    return Response(_collection_data(collection, duplicate=True))


def _collection_data(collection, duplicate):
    return {
        "id": collection.id, "assignment": collection.assignment_id,
        "amount": _money(collection.amount), "recorded_at": collection.recorded_at,
        "duplicate": duplicate, "payment_status": "not_settled",
    }
