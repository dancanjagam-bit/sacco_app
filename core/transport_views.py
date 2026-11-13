from datetime import timedelta
from decimal import Decimal, InvalidOperation
import uuid

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import AuditLog
from .transport_models import (TransportRole, TransportRoute, Vehicle, VehicleOwnership, CrewAssignment,
    TransportCollection, TransportRoleGrant, TransportRemittance, TransportPayment)


def _staff(user, roles=None):
    if user.is_superuser or user.is_admin:
        return True
    if not user.is_staff:
        return False
    try:
        profile = user.staff_profile
        return profile.status == "active" and (roles is None or profile.role in roles)
    except Exception:
        return False


def _assignment_data(a, include_collections=True):
    collections = a.collections.all() if include_collections else []
    return {"id": a.id, "vehicle": a.vehicle_id, "vehicle_registration": a.vehicle_label,
            "route": a.route_id, "route_name": a.route_label, "driver": a.driver_id,
            "driver_name": a.driver_label, "conductor": a.conductor_id,
            "conductor_name": a.conductor_label, "starts_at": a.starts_at,
            "ends_at": a.ends_at, "status": a.status,
            "shift_id": getattr(getattr(a, "shift", None), "id", None),
            "collection_total": str(sum((c.amount for c in collections), Decimal("0.00"))),
            "collections": [{"id":c.id,"amount":str(c.amount),"notes":c.notes,"recorded_at":c.recorded_at} for c in collections]}


def _refresh_remittance_status(remittance):
    from django.db.models import Sum
    total=remittance.payments.filter(status="confirmed").aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    remittance.status="needs_review" if total>remittance.amount else "confirmed" if total==remittance.amount else "partial" if total>0 else "pending"
    remittance.save(update_fields=["status","updated_at"])


def _remittance_data(remittance):
    payments=remittance.payments.order_by("created_at")
    received=sum((payment.amount for payment in payments.filter(status="confirmed")),Decimal("0.00"))
    return {"id":str(remittance.public_id),"payment_reference":remittance.payment_reference,
        "assignment":remittance.assignment_id,"vehicle":remittance.vehicle.registration,"route":remittance.route.name,
        "amount":str(remittance.amount),"reported_amount":str(remittance.amount),"received_amount":str(received),"status":remittance.status,
        "payments":[{"id":p.id,"method":p.method,"status":p.status,"amount":str(p.amount),"receipt":p.mpesa_receipt,
            "provider_reference":p.provider_reference,"created_at":p.created_at} for p in payments]}


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def transport_role_assign(request):
    if not _staff(request.user, {"secretary", "accountant", "superadmin"}):
        return Response({"detail":"Authorized operations staff required."}, status=403)
    try:
        user=get_user_model().objects.get(pk=request.data.get("user"))
        role=request.data.get("role")
        if role not in {choice[0] for choice in TransportRole.ROLE_CHOICES}: raise ValueError("Select owner, driver, or conductor.")
        transport_role,created=TransportRole.objects.get_or_create(user=user,role=role,defaults={"active":True})
        if not transport_role.active: transport_role.active=True; transport_role.save(update_fields=["active"])
        grant,_=TransportRoleGrant.objects.get_or_create(user=user,role=role,defaults={"granted_by":request.user})
    except get_user_model().DoesNotExist: return Response({"detail":"Choose an existing user."},status=400)
    except ValueError as exc: return Response({"detail":str(exc)},status=400)
    AuditLog.log(request.user,"other",f"Transport role {role} for user #{user.id}",{"operation":"assign","grant_id":grant.id},request)
    return Response({"user":user.id,"username":user.username,"role":role,"created":created},status=201 if created else 200)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def transport_staff_users(request):
    if not _staff(request.user,{"secretary","accountant","superadmin"}): return Response({"detail":"Authorized operations staff required."},status=403)
    users=get_user_model().objects.filter(is_active=True).order_by("username")
    return Response([{"id":u.id,"username":u.username,"name":u.get_full_name() or u.username} for u in users])


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def transport_routes(request):
    if request.method == "GET":
        return Response([{"id":r.id,"name":r.name,"origin":r.origin,"destination":r.destination} for r in TransportRoute.objects.filter(active=True)])
    if not _staff(request.user, {"secretary", "accountant", "superadmin"}):
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
        if not _staff(request.user): qs=qs.filter(Q(owner=request.user)|Q(ownership_history__owner=request.user)).distinct()
        return Response([{"id":v.id,"registration":v.registration,"owner":v.owner_id,"owner_name":v.owner.get_full_name() or v.owner.username,"make_model":v.make_model,"active":v.active} for v in qs])
    if not _staff(request.user,{"secretary","accountant","superadmin"}): return Response({"detail":"Authorized operations staff required."},status=403)
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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def transport_vehicle_owner(request, vehicle_id):
    if not _staff(request.user,{"secretary","accountant","superadmin"}): return Response({"detail":"Authorized operations staff required."},status=403)
    vehicle=Vehicle.objects.filter(pk=vehicle_id).first()
    if not vehicle: return Response({"detail":"Vehicle not found."},status=404)
    try: owner=get_user_model().objects.get(pk=request.data.get("owner"))
    except (get_user_model().DoesNotExist,ValueError,TypeError): return Response({"detail":"Choose an existing owner."},status=400)
    if not TransportRole.objects.filter(user=owner,role="owner",active=True).exists(): return Response({"detail":"New owner must hold the transport owner role."},status=400)
    old_owner=vehicle.owner_id
    vehicle.owner=owner
    vehicle.save(update_fields=["owner"])
    VehicleOwnership.objects.filter(vehicle=vehicle,ends_at__isnull=True).update(recorded_by=request.user)
    AuditLog.log(request.user,"other",f"Vehicle #{vehicle.id} ownership changed",{"previous_owner_id":old_owner,"new_owner_id":owner.id},request)
    return Response({"vehicle":vehicle.id,"previous_owner":old_owner,"owner":owner.id})


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def transport_assignments(request):
    if request.method == "GET":
        qs=CrewAssignment.objects.select_related("vehicle","route","driver","conductor")
        if not _staff(request.user): qs=qs.filter(Q(driver=request.user)|Q(conductor=request.user)|Q(vehicle__owner=request.user)|Q(vehicle__ownership_history__owner=request.user)).distinct()
        return Response([_assignment_data(a) for a in qs[:100]])
    if not _staff(request.user,{"secretary","accountant","superadmin"}): return Response({"detail":"Authorized operations staff required."},status=403)
    d=request.data
    try:
        vehicle=Vehicle.objects.get(pk=d.get("vehicle"),active=True)
        route=TransportRoute.objects.get(pk=d.get("route"),active=True)
        driver=get_user_model().objects.get(pk=d.get("driver"))
        conductor=get_user_model().objects.get(pk=d["conductor"]) if d.get("conductor") else None
        starts=timezone.datetime.fromisoformat(str(d.get("starts_at")).replace("Z","+00:00"))
        ends=timezone.datetime.fromisoformat(str(d["ends_at"]).replace("Z","+00:00")) if d.get("ends_at") else None
        if timezone.is_naive(starts): starts=timezone.make_aware(starts)
        if ends and timezone.is_naive(ends): ends=timezone.make_aware(ends)
        if ends and ends<=starts: raise ValueError("End must be after start.")
        for person,role in ((driver,"driver"),(conductor,"conductor")):
            if person and not TransportRole.objects.filter(user=person,role=role,active=True).exists(): raise ValueError(f"Assigned {role} must have the transport {role} role.")
        if conductor and conductor == driver: raise ValueError("Driver and conductor must be different users.")
    except (Vehicle.DoesNotExist,TransportRoute.DoesNotExist): return Response({"detail":"Choose an active vehicle and route."},status=400)
    except Exception as exc: return Response({"detail":str(exc) or "Valid vehicle, route, crew, and start time are required."},status=400)
    overlapping=CrewAssignment.objects.filter(starts_at__lt=(ends or timezone.datetime.max.replace(tzinfo=timezone.get_current_timezone()))).filter(Q(ends_at__isnull=True)|Q(ends_at__gt=starts))
    conflict=overlapping.filter(Q(vehicle=vehicle)|Q(driver=driver)|Q(conductor=driver))
    if conductor: conflict=conflict|overlapping.filter(Q(vehicle=vehicle)|Q(driver=conductor)|Q(conductor=conductor))
    if conflict.exists():
        return Response({"detail":"Vehicle or crew already has an open assignment."},status=409)
    try:
        a=CrewAssignment.objects.create(vehicle=vehicle,route=route,driver=driver,conductor=conductor,starts_at=starts,ends_at=ends,status="active" if starts<=timezone.now() else "scheduled",created_by=request.user)
    except IntegrityError: return Response({"detail":"Vehicle or crew already has an open assignment."},status=409)
    AuditLog.log(request.user,"other",f"Transport assignment #{a.id}",{"vehicle":vehicle.registration,"route":route.name,"driver":driver.username,"conductor":conductor.username if conductor else None,"starts_at":starts.isoformat(),"ends_at":ends.isoformat() if ends else None},request)
    return Response(_assignment_data(a),status=201)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def crew_today(request):
    if request.method == "POST": return _save_collection(request)
    now=timezone.localtime()
    start=now.replace(hour=0,minute=0,second=0,microsecond=0)
    end=start+timedelta(days=1)
    assignment=CrewAssignment.objects.select_related("vehicle","route","driver","conductor").filter(Q(driver=request.user)|Q(conductor=request.user),starts_at__lte=now).filter(Q(ends_at__isnull=True)|Q(ends_at__gt=now)).order_by("-starts_at").first()
    if not assignment:
        return Response({"assignment":None,"message":"No transport assignment covers today. Contact operations staff to check your crew assignment."})
    assignment_data=_assignment_data(assignment)
    assignment_data["remittances"]=[_remittance_data(r) for r in TransportRemittance.objects.filter(assignment=assignment).order_by("-created_at")[:10]]
    return Response({"assignment":assignment_data,"message":"Collections are reported separately from confirmed remittances. No allocation rule is active; received payments remain unallocated."})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def transport_remittance_create(request):
    data=request.data
    try:
        key=uuid.UUID(str(data.get("client_key")))
        amount=Decimal(str(data.get("amount")))
        assignment=CrewAssignment.objects.select_related("vehicle","route").get(pk=data.get("assignment"))
    except (ValueError,TypeError,InvalidOperation,CrewAssignment.DoesNotExist):
        return Response({"detail":"Valid assignment, amount, and UUID client_key are required."},status=400)
    if not amount.is_finite() or amount<=0:return Response({"detail":"Amount must be greater than zero."},status=400)
    if assignment.status not in ("scheduled","active") or request.user.id not in (assignment.driver_id,assignment.conductor_id):
        return Response({"detail":"You are not assigned to this open shift."},status=403)
    previous=TransportRemittance.objects.filter(requested_by=request.user,idempotency_key=key).first()
    if previous:
        if previous.assignment_id!=assignment.id or previous.amount!=amount:return Response({"detail":"client_key was used with different remittance data."},status=409)
        return Response(_remittance_data(previous),status=200)
    shift=getattr(assignment,"shift",None)
    if not shift:return Response({"detail":"Shift record is unavailable; ask operations staff."},status=409)
    remittance=TransportRemittance.objects.create(requested_by=request.user,payer=request.user,assignment=assignment,shift=shift,
        vehicle=assignment.vehicle,route=assignment.route,amount=amount,idempotency_key=key)
    AuditLog.log(request.user,"other",f"Transport remittance {remittance.public_id}",{"operation":"request","amount":str(amount)},request)
    return Response(_remittance_data(remittance),status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def transport_remittance_stk(request, remittance_id):
    from core.models import MpesaTransaction
    from core.services.daraja_service import DarajaError, initiate_stk_push, to_safaricom_phone
    try: remittance=TransportRemittance.objects.select_related("assignment").get(public_id=remittance_id)
    except TransportRemittance.DoesNotExist:return Response({"detail":"Remittance not found."},status=404)
    if not (remittance.requested_by_id==request.user.id or _staff(request.user)):
        return Response({"detail":"You cannot pay this remittance."},status=403)
    try:
        amount=Decimal(str(request.data.get("amount",remittance.amount)))
        key=uuid.UUID(str(request.data.get("client_key")))
        if not amount.is_finite() or amount<=0 or amount!=amount.to_integral_value():raise ValueError
    except (ValueError,TypeError,InvalidOperation):return Response({"detail":"Provide a positive whole-KES amount and UUID client_key."},status=400)
    previous=TransportPayment.objects.filter(requested_by=request.user,idempotency_key=key).first()
    if previous:
        if previous.remittance_id!=remittance.id or previous.amount!=amount:return Response({"detail":"client_key was used for a different payment request."},status=409)
        return Response({"payment_id":previous.id,"status":previous.status,"checkout_request_id":previous.provider_reference or None,"duplicate":True})
    member=getattr(request.user,"member_profile",None)
    try: phone=to_safaricom_phone(str(request.data.get("phone") or (member.phone_number if member else "")))
    except DarajaError as exc:return Response({"detail":exc.message},status=400)
    payment=TransportPayment.objects.create(remittance=remittance,requested_by=request.user,payer=request.user,idempotency_key=key,
        method="stk",status="pending",amount=amount,payer_phone=phone,unallocated_amount=amount)
    try:
        response=initiate_stk_push(phone=phone,amount=int(amount),account_ref=remittance.payment_reference,
            transaction_desc="Transport remit",callback_tag="transport_remittance")
        mpesa=MpesaTransaction.objects.create(user=request.user,phone=phone,payment_type="transport_remittance",amount=amount,
            checkout_request_id=response["CheckoutRequestID"],merchant_request_id=response.get("MerchantRequestID",""),
            transport_remittance=remittance,status="pending")
        payment.mpesa_transaction=mpesa; payment.provider_reference=mpesa.checkout_request_id
        payment.save(update_fields=["mpesa_transaction","provider_reference"])
    except DarajaError as exc:
        payment.status="needs_review";payment.review_reason="Provider request failed or outcome is uncertain.";payment.save(update_fields=["status","review_reason"])
        return Response({"detail":exc.message,"payment_id":payment.id,"status":payment.status},status=502)
    except Exception:
        payment.status="needs_review";payment.review_reason="STK request could not be correlated; staff review is required.";payment.save(update_fields=["status","review_reason"])
        return Response({"detail":"Payment request needs staff review.","payment_id":payment.id},status=502)
    return Response({"payment_id":payment.id,"checkout_request_id":mpesa.checkout_request_id,"status":"pending","message":"STK request accepted; payment remains pending until callback confirmation."},status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def transport_cash_handover(request, remittance_id):
    try:remittance=TransportRemittance.objects.get(public_id=remittance_id)
    except TransportRemittance.DoesNotExist:return Response({"detail":"Remittance not found."},status=404)
    if not (remittance.requested_by_id==request.user.id or _staff(request.user)):return Response({"detail":"You cannot submit this handover."},status=403)
    try:amount=Decimal(str(request.data.get("amount")));key=uuid.UUID(str(request.data.get("client_key")))
    except (ValueError,TypeError,InvalidOperation):return Response({"detail":"Valid amount and UUID client_key are required."},status=400)
    if not amount.is_finite() or amount<=0:return Response({"detail":"Amount must be greater than zero."},status=400)
    existing=TransportPayment.objects.filter(requested_by=request.user,idempotency_key=key).first()
    if existing:
        if existing.remittance_id!=remittance.id or existing.amount!=amount:return Response({"detail":"client_key was used with different handover data."},status=409)
        return Response({"id":existing.id,"status":existing.status,"duplicate":True})
    payment=TransportPayment.objects.create(remittance=remittance,requested_by=request.user,payer=request.user,method="cash",status="pending",amount=amount,idempotency_key=key,unallocated_amount=amount)
    AuditLog.log(request.user,"other",f"Transport cash handover #{payment.id}",{"operation":"submitted","reported_amount":str(amount)},request)
    return Response({"id":payment.id,"status":"pending","message":"Cash handover is awaiting clerk confirmation."},status=201)


@api_view(["GET","POST"])
@permission_classes([IsAuthenticated])
def transport_payment_queue(request):
    if not _staff(request.user,{"accountant","secretary","superadmin"}):return Response({"detail":"Authorized reconciliation staff required."},status=403)
    if request.method=="GET":
        qs=TransportPayment.objects.select_related("remittance").filter(Q(status__in=("pending","needs_review","unmatched"))|Q(remittance__status__in=("partial","needs_review")))
        return Response([{"id":p.id,"status":p.status,"method":p.method,"reported_amount":str(p.amount),"received_amount":str(p.amount if p.status=="confirmed" else 0),"receipt":p.mpesa_receipt,"phone":p.payer_phone,"reference":p.remittance.payment_reference if p.remittance else p.provider_reference,"remittance":str(p.remittance.public_id) if p.remittance else None} for p in qs.order_by("created_at")[:250]])
    payment=TransportPayment.objects.filter(pk=request.data.get("payment_id")).first()
    if not payment:return Response({"detail":"Payment not found."},status=404)
    reason=str(request.data.get("reason","")).strip()
    if not reason:return Response({"detail":"A reason is required."},status=400)
    target=request.data.get("remittance_id")
    if target:
        remittance=TransportRemittance.objects.filter(public_id=target).first()
        if not remittance:return Response({"detail":"Target remittance not found."},status=404)
        payment.remittance=remittance
        if payment.amount>remittance.amount:payment.status="needs_review"
        payment.save(update_fields=["remittance","status"])
    if payment.method=="cash" and request.data.get("confirm") is True:
        payment.status="confirmed";payment.confirmed_by=request.user;payment.confirmed_at=timezone.now();payment.unallocated_amount=payment.amount
    payment.review_reason=reason
    payment.save(update_fields=["status","confirmed_by","confirmed_at","unallocated_amount","review_reason"])
    if payment.remittance:_refresh_remittance_status(payment.remittance)
    AuditLog.log(request.user,"other",f"Transport payment #{payment.id}",{"operation":"reconcile","status":payment.status,"reason":reason,"remittance_id":payment.remittance_id},request)
    return Response({"id":payment.id,"status":payment.status,"remittance":str(payment.remittance.public_id) if payment.remittance else None})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def record_collection(request):
    return _save_collection(request)


def _save_collection(request):
    d=request.data
    try: key=str(d.get("client_key")); amount=Decimal(str(d.get("amount")))
    except (InvalidOperation,TypeError): return Response({"detail":"Provide a valid amount and client_key."},status=400)
    import uuid
    try: key=uuid.UUID(key)
    except (ValueError,AttributeError): return Response({"detail":"client_key must be a UUID for safe retries."},status=400)
    if not amount.is_finite() or amount<=0: return Response({"detail":"Amount must be greater than zero."},status=400)
    if len(str(d.get("notes", "")))>300: return Response({"detail":"Notes must be 300 characters or fewer."},status=400)
    assignment=CrewAssignment.objects.filter(pk=d.get("assignment"),status__in=("scheduled","active")).filter(Q(driver=request.user)|Q(conductor=request.user)).first()
    if not assignment: return Response({"detail":"You are not assigned to this active shift."},status=403)
    existing=TransportCollection.objects.filter(recorded_by=request.user,client_key=key).first()
    if existing:
        if existing.assignment_id!=assignment.id or existing.amount!=amount or existing.notes!=str(d.get("notes", "")): return Response({"detail":"client_key was already used for a different collection."},status=409)
        return Response({"id":existing.id,"assignment":existing.assignment_id,"amount":str(existing.amount),"recorded_at":existing.recorded_at,"duplicate":True},status=200)
    try:
        with transaction.atomic():
            collection=TransportCollection.objects.create(assignment=assignment,recorded_by=request.user,client_key=key,amount=amount,notes=str(d.get("notes", "")))
    except IntegrityError:
        collection=TransportCollection.objects.get(recorded_by=request.user,client_key=key)
        if collection.assignment_id!=assignment.id or collection.amount!=amount or collection.notes!=str(d.get("notes", "")):
            return Response({"detail":"client_key was already used for a different collection."},status=409)
        return Response({"id":collection.id,"assignment":collection.assignment_id,"amount":str(collection.amount),"recorded_at":collection.recorded_at,"duplicate":True})
    return Response({"id":collection.id,"assignment":assignment.id,"amount":str(collection.amount),"recorded_at":collection.recorded_at,"duplicate":False,"payment_status":"not_settled"},status=201)
