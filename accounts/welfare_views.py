from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.http import FileResponse
from django.urls import reverse
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounting.models import JournalEntry, JournalLine
from accounting.permissions import IsActiveAccountant
from accounting.services import _authorized_accountant
from core.services.fosa_payouts import PayoutUnavailable
from members.models import Member
from .access import has_sacco_permission
from .models import AuditLog
from .services.file_validator import validate_id_document
from .services.welfare_payouts import (
    WelfarePayoutConflict, get_welfare_provider, refresh_welfare_payout, start_welfare_payout,
)
from .welfare_models import WelfareContribution, WelfareDocument, WelfarePayout, WelfarePolicy, WelfareRequest


class WelfareRequestInput(serializers.Serializer):
    category = serializers.CharField(max_length=60)
    description = serializers.CharField(max_length=2000)
    requested_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))


class WelfareDecisionInput(serializers.Serializer):
    action = serializers.ChoiceField(choices=("approve", "reject"))
    reason = serializers.CharField(max_length=500)


def _documents(row):
    return [{"id": doc.pk, "name": doc.name, "url": reverse("welfare-document", args=[doc.pk])}
            for doc in row.documents.all()]


def _request_data(row, staff=False):
    payout = getattr(row, "payout", None)
    data = {
        "id": row.pk, "category": row.category, "description": row.description, "status": row.status,
        "requested_amount": str(row.requested_amount),
        "approved_amount": str(row.approved_amount) if row.approved_amount is not None else None,
        "decision_reason": row.decision_reason, "policy_version": row.policy.version if row.policy else None,
        "created_at": row.created_at, "updated_at": row.updated_at,
        "review_notes": row.review_notes,
        "reviewed_by": (row.reviewed_by.get_full_name() or row.reviewed_by.username) if row.reviewed_by else None,
        "reviewed_at": row.reviewed_at,
        "documents": _documents(row),
        "payout_status": (
            "reversed" if payout and payout.confirmed_entry_id and getattr(payout.confirmed_entry, "reversal_entry", None)
            else payout.status if payout else None
        ),
        "payout_reference": payout.provider_reference if payout else "",
    }
    if staff:
        user = row.member.user
        data["member_name"] = user.get_full_name() or user.username
        data["member_number"] = row.member.member_number
    return data


def _member(user):
    if has_sacco_permission(user, "welfare.read_own"):
        return Member.objects.filter(user=user, status="active").first()
    return None


def _contributions(member):
    return WelfareContribution.objects.filter(
        member=member, journal_line__entry__status="posted", journal_line__entry__reversal_entry__isnull=True,
    )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def welfare_requests(request):
    staff = request.query_params.get("scope") == "committee"
    if staff and not has_sacco_permission(request.user, "welfare.review"):
        return Response({"detail": "Welfare review permission is required."}, status=403)
    member = _member(request.user)
    if not staff and not member:
        return Response({"detail": "An active membership is required."}, status=403)
    if request.method == "GET":
        rows = WelfareRequest.objects.select_related(
            "member__user", "policy", "payout__confirmed_entry__reversal_entry", "reviewed_by",
        ).prefetch_related("documents")
        if not staff:
            rows = rows.filter(member=member)
        status_filter = request.query_params.get("status")
        if status_filter:
            rows = rows.filter(status=status_filter)
        return Response([_request_data(row, staff) for row in rows.order_by("-created_at")[:100]])
    if not member or staff:
        return Response({"detail": "Submit requests from the member workspace."}, status=403)
    serializer = WelfareRequestInput(data=request.data)
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        row = WelfareRequest.objects.create(member=member, **serializer.validated_data)
        AuditLog.log(request.user, "other", f"Welfare request #{row.pk}", {"operation": "welfare_submitted"}, request)
    return Response(_request_data(row), status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def welfare_upload(request, request_id):
    member = _member(request.user)
    if not member:
        return Response({"detail": "An active membership is required."}, status=403)
    upload = request.FILES.get("document")
    if not upload:
        return Response({"detail": "Choose a supporting document."}, status=400)
    try:
        validate_id_document(upload)
    except ValidationError as exc:
        return Response({"detail": exc.messages[0]}, status=400)
    with transaction.atomic():
        row = WelfareRequest.objects.select_for_update().filter(pk=request_id, member=member).first()
        if not row:
            return Response({"detail": "Welfare request not found."}, status=404)
        if row.status != "submitted" or row.documents.count() >= 5:
            return Response({"detail": "Uploads require a submitted request with fewer than five documents."}, status=409)
        name = Path(upload.name).name[:150]
        upload.name = uuid4().hex
        doc = WelfareDocument.objects.create(request=row, file=upload, name=name)
        AuditLog.log(request.user, "other", f"Welfare request #{row.pk}", {
            "operation": "welfare_document_uploaded", "document_id": doc.pk,
        }, request)
    return Response({"id": doc.pk, "name": doc.name, "url": reverse("welfare-document", args=[doc.pk])}, status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def welfare_document(request, document_id):
    docs = WelfareDocument.objects.select_related("request__member")
    if not has_sacco_permission(request.user, "welfare.review"):
        docs = docs.filter(request__member=_member(request.user))
    document = docs.filter(pk=document_id).first()
    if not document:
        return Response({"detail": "Document not found."}, status=404)
    try:
        response = FileResponse(document.file.open("rb"), as_attachment=True,
                                filename=document.name, content_type="application/octet-stream")
    except FileNotFoundError:
        return Response({"detail": "Document not found."}, status=404)
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    AuditLog.log(request.user, "other", f"Welfare document #{document.pk}", {
        "operation": "welfare_document_viewed",
    }, request)
    return response


def welfare_policy_terms(benefits):
    if not isinstance(benefits, dict) or not benefits:
        raise ValueError("Configure at least one benefit category.")
    terms = {}
    for category, rule in benefits.items():
        try:
            maximum = Decimal(str(rule["maximum_benefit"]))
            minimum = Decimal(str(rule["minimum_contributions"]))
            if (not category.strip() or len(category) > 60 or not Decimal("0.01") <= maximum <= Decimal("9999999999.99")
                    or not Decimal("0") <= minimum <= Decimal("9999999999.99")
                    or any(amount != amount.quantize(Decimal("0.01")) for amount in (minimum, maximum))):
                raise ValueError
        except (TypeError, KeyError, InvalidOperation, ValueError):
            raise ValueError("Each category needs a positive maximum_benefit and nonnegative minimum_contributions in KES.") from None
        terms[category] = (maximum, minimum)
    return terms


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def welfare_decide(request, request_id):
    if not has_sacco_permission(request.user, "welfare.review"):
        return Response({"detail": "Welfare review permission is required."}, status=403)
    serializer = WelfareDecisionInput(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    with transaction.atomic():
        row = WelfareRequest.objects.select_for_update().filter(pk=request_id).first()
        if not row:
            return Response({"detail": "Welfare request not found."}, status=404)
        if row.member.user_id == request.user.pk:
            return Response({"detail": "You cannot decide your own request."}, status=403)
        if row.status not in ("submitted", "needs_information"):
            return Response({"detail": "This request has already been decided or is under review."}, status=409)
        if data["action"] == "approve":
            policy = WelfarePolicy.objects.filter(active=True).first()
            try:
                terms = welfare_policy_terms(policy.benefits) if policy else {}
            except ValueError:
                terms = {}
            if row.category not in terms:
                return Response({"detail": "An approved welfare policy for this category is required."}, status=409)
            maximum, minimum = terms[row.category]
            contributed = _contributions(row.member).aggregate(total=Sum("journal_line__credit"))["total"] or Decimal("0")
            if contributed < minimum or row.requested_amount > maximum:
                return Response({"detail": "This request exceeds the benefit cap or falls below the contribution requirement."}, status=409)
            row.policy = policy
            row.status = "approved"
            row.approved_amount = row.requested_amount
            WelfarePayout.objects.create(request=row)
        else:
            row.status = "rejected"
        row.decided_by = request.user
        row.decided_at = timezone.now()
        row.decision_reason = data["reason"]
        row.save()
        AuditLog.log(request.user, "other", f"Welfare request #{row.pk}", {
            "operation": "welfare_decided", "decision": row.status, "reason": row.decision_reason,
            "policy_version": row.policy.version if row.policy else None,
        }, request)
    return Response(_request_data(row, staff=True))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def welfare_contributions(request):
    member = _member(request.user)
    if not member:
        return Response({"detail": "An active membership is required."}, status=403)
    rows = _contributions(member).select_related("journal_line__entry").order_by("-journal_line__entry__posted_at")[:100]
    return Response([{"id": row.pk, "amount": str(row.journal_line.credit),
                      "posted_at": row.journal_line.entry.posted_at,
                      "source_reference": row.journal_line.entry.source_reference} for row in rows])


def _posted_contribution_credits():
    return JournalLine.objects.filter(
        credit__gt=0, entry__status="posted", entry__reversal_entry__isnull=True,
        account__system_key="welfare_contributions", account__currency="KES",
    ).exclude(entry__source_type="reversal")


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsActiveAccountant])
def welfare_attribution_candidates(request):
    query = request.query_params.get("q", "").strip()[:100]
    members = Member.objects.select_related("user").filter(status="active")
    if query:
        members = members.filter(
            Q(member_number__icontains=query) | Q(user__username__icontains=query)
            | Q(user__first_name__icontains=query) | Q(user__last_name__icontains=query)
        )
    credits = _posted_contribution_credits().filter(welfarecontribution__isnull=True).select_related(
        "entry",
    ).order_by("-entry__posted_at", "-pk")[:100]
    return Response({
        "members": [{"id": row.pk, "member_number": row.member_number,
                     "name": row.user.get_full_name() or row.user.username}
                    for row in members.order_by("member_number")[:25]],
        "credits": [{"id": line.pk, "amount": str(line.credit), "posted_at": line.entry.posted_at,
                     "source_reference": line.entry.source_reference} for line in credits],
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsActiveAccountant])
def welfare_attribute_contribution(request):
    class AttributionInput(serializers.Serializer):
        member = serializers.IntegerField(min_value=1, max_value=2**63 - 1)
        journal_line = serializers.IntegerField(min_value=1, max_value=2**63 - 1)
        reason = serializers.CharField(max_length=500)

    serializer = AttributionInput(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    with transaction.atomic():
        line = _posted_contribution_credits().filter(pk=data["journal_line"]).first()
        if not line or not Member.objects.filter(pk=data["member"], status="active").exists():
            return Response({"detail": "Choose a member and a posted welfare contribution credit."}, status=400)
        link, created = WelfareContribution.objects.get_or_create(
            journal_line=line, defaults={"member_id": data["member"], "recorded_by": request.user},
        )
        if link.member_id != data["member"]:
            return Response({"detail": "This credit already belongs to a different member."}, status=409)
        if created:
            AuditLog.log(request.user, "other", f"Welfare contribution #{link.pk}", {
                "operation": "welfare_contribution_attributed", "journal_line": line.pk, "reason": data["reason"],
            }, request)
    return Response({"id": link.pk}, status=201 if created else 200)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsActiveAccountant])
def welfare_link_payout(request, request_id):
    """Link an already verified, posted payout. This endpoint never sends funds."""
    class PayoutInput(serializers.Serializer):
        journal_entry = serializers.UUIDField()
        reason = serializers.CharField(max_length=500)

    serializer = PayoutInput(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    with transaction.atomic():
        payout = WelfarePayout.objects.select_for_update().filter(request_id=request_id).first()
        if not payout:
            return Response({"detail": "An approved welfare request is required."}, status=404)
        if payout.confirmed_entry_id:
            if payout.confirmed_entry_id == data["journal_entry"]:
                return Response({"status": payout.status, "provider_reference": payout.provider_reference})
            return Response({"detail": "A payout journal is already linked."}, status=409)
        if payout.status in {"pending", "uncertain"}:
            return Response({"detail": "Refresh the existing provider attempt through the payout queue."}, status=409)
        entry = JournalEntry.objects.select_for_update().filter(
            pk=data["journal_entry"], source_type="welfare_payout", status="posted", currency="KES",
        ).first()
        if not entry or getattr(entry, "reversal_entry", None):
            return Response({"detail": "A posted, unreversed welfare payout entry is required."}, status=409)
        # The trusted settlement producer uses request ID plus verified provider reference.
        prefix = f"{request_id}:"
        reference = entry.source_reference.removeprefix(prefix)
        debited = entry.lines.filter(account__system_key="welfare_benefits").aggregate(total=Sum("debit"))["total"]
        if (reference == entry.source_reference or not reference or len(reference) > 100
                or debited != payout.request.approved_amount
                or entry.lines.aggregate(total=Sum("credit"))["total"] != payout.request.approved_amount):
            return Response({"detail": "The posted payout must match this request and approved amount."}, status=409)
        payout.status = "confirmed"
        payout.provider_reference = reference
        payout.confirmed_entry = entry
        payout.save(update_fields=("status", "provider_reference", "confirmed_entry"))
        AuditLog.log(request.user, "other", f"Welfare payout #{payout.pk}", {
            "operation": "welfare_payout_linked", "journal_entry": str(entry.pk), "reason": data["reason"],
        }, request)
    return Response({"status": payout.status, "provider_reference": payout.provider_reference})


def _payout_command(request, request_id, start):
    if not has_sacco_permission(request.user, "payments.reconcile"):
        return Response({"detail": "Payment reconciliation permission is required."}, status=403)
    provider = get_welfare_provider()
    try:
        if start:
            payout, created = start_welfare_payout(request_id, request.user, provider)
        else:
            payout = refresh_welfare_payout(request_id, request.user, provider)
            created = False
    except WelfarePayout.DoesNotExist:
        return Response({"detail": "An approved welfare request is required."}, status=404)
    except PayoutUnavailable as exc:
        return Response({"detail": str(exc)}, status=503)
    except WelfarePayoutConflict as exc:
        return Response({"detail": str(exc)}, status=409)
    return Response({"status": payout.status, "provider_reference": payout.provider_reference},
                    status=202 if created and payout.status != "failed" else 200)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def welfare_start_payout(request, request_id):
    return _payout_command(request, request_id, start=True)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def welfare_refresh_payout(request, request_id):
    return _payout_command(request, request_id, start=False)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def welfare_request_info(request, request_id):
    """Officer requests additional information from the member."""
    if not has_sacco_permission(request.user, "welfare.review"):
        return Response({"detail": "Welfare review permission is required."}, status=403)
    class InfoInput(serializers.Serializer):
        notes = serializers.CharField(max_length=2000)
    serializer = InfoInput(data=request.data)
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        row = WelfareRequest.objects.select_for_update().filter(pk=request_id).first()
        if not row:
            return Response({"detail": "Welfare request not found."}, status=404)
        if row.member.user_id == request.user.pk:
            return Response({"detail": "You cannot review your own request."}, status=403)
        if row.status not in ("submitted", "under_review"):
            return Response({"detail": "This request is no longer open for information requests."}, status=409)
        row.status = "needs_information"
        row.review_notes = serializer.validated_data["notes"]
        row.reviewed_by = request.user
        row.reviewed_at = timezone.now()
        row.save(update_fields=("status", "review_notes", "reviewed_by", "reviewed_at", "updated_at"))
        AuditLog.log(request.user, "other", f"Welfare request #{row.pk}", {
            "operation": "welfare_info_requested", "notes_preview": row.review_notes[:80],
        }, request)
    return Response(_request_data(row, staff=True))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def welfare_resubmit(request, request_id):
    """Member provides additional information and resubmits."""
    member = _member(request.user)
    if not member:
        return Response({"detail": "An active membership is required."}, status=403)
    with transaction.atomic():
        row = WelfareRequest.objects.select_for_update().filter(pk=request_id, member=member).first()
        if not row:
            return Response({"detail": "Welfare request not found."}, status=404)
        if row.status != "needs_information":
            return Response({"detail": "This request is not awaiting additional information."}, status=409)
        row.status = "submitted"
        row.save(update_fields=("status", "updated_at"))
        AuditLog.log(request.user, "other", f"Welfare request #{row.pk}", {
            "operation": "welfare_resubmitted",
        }, request)
    return Response(_request_data(row))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def welfare_member_dashboard(request):
    """Member's own welfare overview: contributions total, case counts by status."""
    member = _member(request.user)
    if not member:
        return Response({"detail": "An active membership is required."}, status=403)
    contributions_qs = _contributions(member)
    total_contributed = contributions_qs.aggregate(
        total=Sum("journal_line__credit")
    )["total"] or Decimal("0")
    requests_qs = WelfareRequest.objects.filter(member=member)
    cases = {
        "submitted": requests_qs.filter(status="submitted").count(),
        "needs_information": requests_qs.filter(status="needs_information").count(),
        "under_review": requests_qs.filter(status="under_review").count(),
        "approved": requests_qs.filter(status="approved").count(),
        "rejected": requests_qs.filter(status="rejected").count(),
    }
    policy = WelfarePolicy.objects.filter(active=True).first()
    categories = []
    if policy and isinstance(policy.benefits, dict):
        for cat, rule in policy.benefits.items():
            categories.append({
                "category": cat,
                "maximum_benefit": str(rule.get("maximum_benefit", "0")),
                "minimum_contributions": str(rule.get("minimum_contributions", "0")),
            })
    return Response({
        "total_contributions": str(total_contributed),
        "case_counts": cases,
        "categories": categories,
        "active_policy_version": policy.version if policy else None,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def welfare_officer_dashboard(request):
    """Welfare officer review queue summary."""
    if not has_sacco_permission(request.user, "welfare.review"):
        return Response({"detail": "Welfare review permission is required."}, status=403)
    base = WelfareRequest.objects.all()
    counts = {
        "submitted": base.filter(status="submitted").count(),
        "needs_information": base.filter(status="needs_information").count(),
        "under_review": base.filter(status="under_review").count(),
        "approved": base.filter(status="approved").count(),
        "rejected": base.filter(status="rejected").count(),
    }
    # Pooled fund balance: total welfare contributions credited minus total approved payouts debited.
    from accounting.models import LedgerAccount
    fund_account = LedgerAccount.objects.filter(system_key="welfare_contributions", currency="KES").first()
    benefits_account = LedgerAccount.objects.filter(system_key="welfare_benefits", currency="KES").first()
    fund_balance = Decimal("0")
    if fund_account:
        credits = JournalLine.objects.filter(
            account=fund_account, entry__status="posted", entry__reversal_entry__isnull=True,
        ).aggregate(total=Sum("credit"))["total"] or Decimal("0")
        debits = JournalLine.objects.filter(
            account=fund_account, entry__status="posted", entry__reversal_entry__isnull=True,
        ).aggregate(total=Sum("debit"))["total"] or Decimal("0")
        fund_balance = credits - debits
    approved_payouts = WelfarePayout.objects.filter(
        request__status="approved"
    ).count()
    confirmed_payouts = WelfarePayout.objects.filter(
        status="confirmed"
    ).count()
    pending_payouts = WelfarePayout.objects.filter(
        status__in=("awaiting_provider", "pending")
    ).count()
    policy = WelfarePolicy.objects.filter(active=True).first()
    return Response({
        "case_counts": counts,
        "pooled_fund_balance": str(fund_balance),
        "approved_payouts": approved_payouts,
        "confirmed_payouts": confirmed_payouts,
        "pending_payouts": pending_payouts,
        "active_policy_version": policy.version if policy else None,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Item 2: Treasurer welfare payout queue
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def welfare_treasurer_queue(request):
    """Approved welfare requests that have a pending or awaiting payout."""
    if not has_sacco_permission(request.user, "payments.reconcile"):
        return Response({"detail": "Payment reconciliation permission is required."}, status=403)
    provider_available = get_welfare_provider() is not None
    rows = (
        WelfarePayout.objects.select_related(
            "request__member__user",
            "request__policy",
            "confirmed_entry__reversal_entry",
        )
        .order_by("-created_at")[:200]
    )
    result = []
    for payout in rows:
        req = payout.request
        member = req.member
        user = member.user
        result.append({
            "id": req.pk,
            "member_name": user.get_full_name() or user.username,
            "member_number": member.member_number,
            "category": req.category,
            "requested_amount": str(req.requested_amount),
            "approved_amount": str(req.approved_amount) if req.approved_amount is not None else None,
            "payout_status": "reversed" if payout.confirmed_entry_id and getattr(
                payout.confirmed_entry, "reversal_entry", None,
            ) else payout.status,
            "payout_reference": payout.provider_reference,
            "created_at": req.created_at,
            "decided_at": req.decided_at,
            "can_start_payout": provider_available and payout.status == "awaiting_provider" and user.pk != request.user.pk,
            "can_refresh_payout": provider_available and payout.status in {"pending", "uncertain"}
                and bool(payout.destination_phone) and user.pk != request.user.pk,
        })
    total_pending = WelfarePayout.objects.filter(status__in=(
        "awaiting_provider", "pending", "uncertain",
    )).aggregate(total=Sum("request__approved_amount", default=Decimal("0.00")))["total"]
    return Response({
        "payouts": result, "total_pending_amount": str(total_pending),
        "provider_available": provider_available, "can_attribute": _authorized_accountant(request.user),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Item 4: Welfare policy CRUD
# ─────────────────────────────────────────────────────────────────────────────

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def welfare_policy(request):
    if request.method == "GET":
        if not (has_sacco_permission(request.user, "welfare.review") or
                has_sacco_permission(request.user, "staff.manage")):
            return Response({"detail": "Welfare review or administration permission required."}, status=403)
        active = WelfarePolicy.objects.filter(active=True).first()
        all_policies = list(WelfarePolicy.objects.order_by("-approved_at").values(
            "id", "version", "approval_reference", "benefits", "active", "approved_at"
        )[:50])
        return Response({
            "active_policy": {
                "id": active.pk,
                "version": active.version,
                "approval_reference": active.approval_reference,
                "benefits": active.benefits,
                "active": active.active,
                "approved_at": active.approved_at,
            } if active else None,
            "policies": all_policies,
        })

    # POST — requires staff.manage
    if not has_sacco_permission(request.user, "staff.manage"):
        return Response({"detail": "System administration permission required."}, status=403)
    class PolicyInput(serializers.Serializer):
        version = serializers.CharField(max_length=60)
        approval_reference = serializers.CharField(max_length=120)
        benefits = serializers.DictField(allow_empty=False)
        activate = serializers.BooleanField(required=False, default=False)

    serializer = PolicyInput(data=request.data)
    serializer.is_valid(raise_exception=True)
    version, approval_reference, benefits, activate = (
        serializer.validated_data[key] for key in ("version", "approval_reference", "benefits", "activate")
    )
    try:
        welfare_policy_terms(benefits)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=400)
    if WelfarePolicy.objects.filter(version=version).exists():
        return Response({"detail": "A policy with this version already exists."}, status=409)
    try:
        with transaction.atomic():
            if activate:
                WelfarePolicy.objects.filter(active=True).update(active=False)
            policy = WelfarePolicy.objects.create(
                version=version, approval_reference=approval_reference, benefits=benefits,
                active=activate, approved_by=request.user,
            )
            AuditLog.log(request.user, "other", f"Welfare policy version {version}", {
                "operation": "welfare_policy_created", "activate": activate,
            }, request)
    except IntegrityError:
        return Response({"detail": "A conflicting policy change was saved. Refresh before retrying."}, status=409)
    return Response({
        "id": policy.pk,
        "version": policy.version,
        "approval_reference": policy.approval_reference,
        "benefits": policy.benefits,
        "active": policy.active,
        "approved_at": policy.approved_at,
    }, status=201)
