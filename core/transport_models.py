"""Transport operational records. Financial settlement remains in core.Transaction."""
from django.conf import settings
from django.db import models
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
import secrets
import string
import uuid


class TransportRole(models.Model):
    OWNER = "owner"
    DRIVER = "driver"
    CONDUCTOR = "conductor"
    ROLE_CHOICES = [(OWNER, "Owner"), (DRIVER, "Driver"), (CONDUCTOR, "Conductor")]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transport_roles")
    role = models.CharField(max_length=12, choices=ROLE_CHOICES)
    active = models.BooleanField(default=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=("user", "role"), name="unique_transport_user_role")]


class TransportRoute(models.Model):
    name = models.CharField(max_length=120, unique=True)
    origin = models.CharField(max_length=100, blank=True)
    destination = models.CharField(max_length=100, blank=True)
    active = models.BooleanField(default=True)
    def __str__(self): return self.name


class Vehicle(models.Model):
    registration = models.CharField(max_length=20, unique=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="transport_vehicles")
    make_model = models.CharField(max_length=100, blank=True)
    capacity = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.registration
    def save(self, *args, **kwargs):
        previous_owner_id = None
        if self.pk:
            previous_owner_id = type(self).objects.filter(pk=self.pk).values_list("owner_id", flat=True).first()
        with transaction.atomic():
            super().save(*args, **kwargs)
            if previous_owner_id is None:
                VehicleOwnership.objects.get_or_create(vehicle=self, owner=self.owner, ends_at__isnull=True,
                    defaults={"starts_at": self.created_at or timezone.now()})
            elif previous_owner_id != self.owner_id:
                VehicleOwnership.objects.filter(vehicle=self, ends_at__isnull=True).update(ends_at=timezone.now())
                VehicleOwnership.objects.create(vehicle=self, owner=self.owner, starts_at=timezone.now())


class VehicleOwnership(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="ownership_history")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="vehicle_ownership_history")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="recorded_vehicle_ownerships")
    class Meta:
        ordering = ["-starts_at"]
        constraints = [models.CheckConstraint(condition=Q(ends_at__isnull=True) | Q(ends_at__gt=models.F("starts_at")), name="ownership_valid_period")]


class CrewAssignment(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="assignments")
    route = models.ForeignKey(TransportRoute, on_delete=models.PROTECT, related_name="assignments")
    driver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="driver_assignments")
    conductor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="conductor_assignments")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=[("scheduled", "Scheduled"), ("active", "Active"), ("ended", "Ended")], default="scheduled")
    vehicle_label = models.CharField(max_length=20, blank=True)
    route_label = models.CharField(max_length=120, blank=True)
    driver_label = models.CharField(max_length=150, blank=True)
    conductor_label = models.CharField(max_length=150, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="created_transport_assignments")
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-starts_at"]
        constraints = [
            models.CheckConstraint(condition=Q(ends_at__isnull=True) | Q(ends_at__gt=models.F("starts_at")), name="transport_assignment_valid_period"),
        ]
    def save(self, *args, **kwargs):
        # These values describe the assignment at creation time. Do not refresh
        # them when a current vehicle, route, or user profile is later renamed.
        is_new = self._state.adding
        if is_new:
            self.vehicle_label = self.vehicle.registration
            self.route_label = self.route.name
            self.driver_label = self.driver.get_full_name() or self.driver.username
            self.conductor_label = (self.conductor.get_full_name() or self.conductor.username) if self.conductor else ""
        with transaction.atomic():
            super().save(*args, **kwargs)
            if is_new:
                shift_status = {"active": "active", "ended": "closed"}.get(self.status, "scheduled")
                TransportShift.objects.create(
                    assignment=self, starts_at=self.starts_at, ends_at=self.ends_at, status=shift_status,
                )


class TransportShift(models.Model):
    assignment = models.OneToOneField(CrewAssignment, on_delete=models.PROTECT, related_name="shift")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=[("scheduled", "Scheduled"), ("active", "Active"), ("closed", "Closed")], default="scheduled")
    created_at = models.DateTimeField(auto_now_add=True)


class TransportDeductionRule(models.Model):
    """Approved, versioned expense deduction policy for shift closure.

    No rule is created or activated by default. A rule is usable only after a
    superuser records the cooperative's approval reference and approver.
    """
    scope = models.CharField(max_length=30, default="shift_deduction", editable=False)
    version = models.CharField(max_length=60, unique=True)
    deductible_categories = models.JSONField(default=list, blank=True)
    approval_reference = models.CharField(max_length=120, blank=True, default="")
    active = models.BooleanField(default=False)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="approved_transport_deduction_rules")
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("scope",), condition=Q(active=True), name="unique_active_transport_deduction_rule"),
            models.CheckConstraint(condition=Q(active=False) | (Q(approved_by__isnull=False) & ~Q(approval_reference="") & Q(approved_at__isnull=False)), name="active_transport_rule_is_approved"),
        ]


class TransportExpense(models.Model):
    STATUS_CHOICES = [("reported", "Reported"), ("approved", "Approved"), ("rejected", "Rejected")]
    assignment = models.ForeignKey(CrewAssignment, on_delete=models.PROTECT, related_name="expenses")
    shift = models.ForeignKey(TransportShift, on_delete=models.PROTECT, related_name="expenses")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="transport_expenses")
    route = models.ForeignKey(TransportRoute, on_delete=models.PROTECT, related_name="transport_expenses")
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reported_transport_expenses")
    client_key = models.UUIDField()
    category = models.CharField(max_length=60)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="reported")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_transport_expenses")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=("reported_by", "client_key"), name="unique_transport_expense_submission"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="transport_expense_amount_positive"),
        ]


class TransportShiftClosure(models.Model):
    CALCULATION_CHOICES = [("calculated", "Calculated"), ("rule_required", "Rule required"), ("review_required", "Review required")]
    shift = models.OneToOneField(TransportShift, on_delete=models.PROTECT, related_name="closure")
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="closed_transport_shifts")
    closed_at = models.DateTimeField(default=timezone.now)
    reported_gross = models.DecimalField(max_digits=12, decimal_places=2)
    approved_expenses = models.DecimalField(max_digits=12, decimal_places=2)
    deductible_expenses = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    expected_remittance = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    deduction_rule_version = models.CharField(max_length=60, blank=True)
    calculation_status = models.CharField(max_length=16, choices=CALCULATION_CHOICES, default="rule_required")
    calculation_note = models.CharField(max_length=240, blank=True)



class TransportPaymentReviewEvent(models.Model):
    """Safe metadata for duplicate/conflicting provider callbacks; no raw PII."""
    STATUS_CHOICES = [("pending", "Pending review"), ("resolved", "Resolved")]
    event_key = models.CharField(max_length=64, unique=True)
    payment = models.ForeignKey(
        "core.TransportPayment",
        null=True, blank=True, on_delete=models.PROTECT, related_name="review_events",
    )
    receipt = models.CharField(max_length=20, blank=True)
    provider_reference = models.CharField(max_length=120, blank=True)
    observed_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    reason = models.CharField(max_length=240)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="pending")
    resolution_reason = models.CharField(max_length=500, blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="resolved_transport_payment_events")
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class TransportCollection(models.Model):
    assignment = models.ForeignKey(CrewAssignment, on_delete=models.PROTECT, related_name="collections")
    shift = models.ForeignKey(TransportShift, null=True, on_delete=models.PROTECT, related_name="collections")
    vehicle = models.ForeignKey(Vehicle, null=True, on_delete=models.PROTECT, related_name="collections")
    route = models.ForeignKey(TransportRoute, null=True, on_delete=models.PROTECT, related_name="collections")
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="transport_collections")
    client_key = models.UUIDField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.CharField(max_length=300, blank=True)
    recorded_at = models.DateTimeField(default=timezone.now)
    class Meta:
        ordering = ["-recorded_at"]
        constraints = [
            models.UniqueConstraint(fields=("recorded_by", "client_key"), name="unique_transport_collection_submission"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="transport_collection_amount_positive"),
        ]

    def save(self, *args, **kwargs):
        if self.assignment_id:
            self.vehicle_id = self.vehicle_id or self.assignment.vehicle_id
            self.route_id = self.route_id or self.assignment.route_id
            shift = getattr(self.assignment, "shift", None)
            self.shift_id = self.shift_id or (shift.pk if shift else None)
        super().save(*args, **kwargs)


def _transport_paybill_reference():
    return "TR" + "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(10))


class TransportRemittance(models.Model):
    STATUS_CHOICES=[("pending","Pending"),("partial","Partial"),("confirmed","Confirmed"),("needs_review","Needs review"),("failed","Failed")]
    public_id=models.UUIDField(default=uuid.uuid4,unique=True,editable=False)
    payment_reference=models.CharField(max_length=12,unique=True,default=_transport_paybill_reference)
    requested_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="requested_transport_remittances")
    payer=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name="transport_remittance_payments")
    assignment=models.ForeignKey(CrewAssignment,on_delete=models.PROTECT,related_name="remittances")
    shift=models.ForeignKey(TransportShift,on_delete=models.PROTECT,related_name="remittances")
    vehicle=models.ForeignKey(Vehicle,on_delete=models.PROTECT,related_name="remittances")
    route=models.ForeignKey(TransportRoute,on_delete=models.PROTECT,related_name="remittances")
    closure=models.OneToOneField(TransportShiftClosure,null=True,blank=True,on_delete=models.PROTECT,related_name="remittance")
    amount=models.DecimalField(max_digits=12,decimal_places=2)
    idempotency_key=models.UUIDField()
    status=models.CharField(max_length=16,choices=STATUS_CHOICES,default="pending")
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        ordering=["-created_at"]
        constraints=[models.UniqueConstraint(fields=("requested_by","idempotency_key"),name="unique_transport_remittance_submission")]


class TransportPayment(models.Model):
    METHOD_CHOICES=[("stk","M-Pesa STK"),("c2b","M-Pesa Paybill"),("cash","Cash handover")]
    STATUS_CHOICES=[("pending","Pending"),("confirmed","Confirmed"),("failed","Failed"),("needs_review","Needs review"),("unmatched","Unmatched")]
    remittance=models.ForeignKey(TransportRemittance,null=True,blank=True,on_delete=models.PROTECT,related_name="payments")
    requested_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name="initiated_transport_payments")
    idempotency_key=models.UUIDField(null=True,blank=True)
    payer=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name="transport_payments")
    method=models.CharField(max_length=8,choices=METHOD_CHOICES)
    status=models.CharField(max_length=16,choices=STATUS_CHOICES,default="pending")
    amount=models.DecimalField(max_digits=12,decimal_places=2)
    # The amount requested/reported is distinct from provider- or clerk-confirmed funds.
    received_amount=models.DecimalField(max_digits=12,decimal_places=2,null=True,blank=True)
    payer_phone=models.CharField(max_length=15,blank=True)
    mpesa_transaction=models.OneToOneField("core.MpesaTransaction",null=True,blank=True,on_delete=models.PROTECT,related_name="transport_payment")
    provider_reference=models.CharField(max_length=120,blank=True)
    requires_signed_callback=models.BooleanField(default=False)
    mpesa_receipt=models.CharField(max_length=20,null=True,blank=True,unique=True)
    unallocated_amount=models.DecimalField(max_digits=12,decimal_places=2,default=0)
    confirmed_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name="confirmed_transport_payments")
    confirmed_at=models.DateTimeField(null=True,blank=True)
    review_reason=models.TextField(blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=["-created_at"]
        constraints=[models.UniqueConstraint(fields=("requested_by","idempotency_key"),condition=Q(idempotency_key__isnull=False),name="unique_transport_payment_submission")]


class TransportAllocationRule(models.Model):
    version=models.CharField(max_length=60,unique=True)
    allocations=models.JSONField(default=dict,help_text="Approved allocation definitions; no default policy is active.")
    active=models.BooleanField(default=False)
    approved_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name="approved_transport_allocation_rules")
    approved_at=models.DateTimeField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)


class TransportPaymentAllocation(models.Model):
    payment=models.ForeignKey(TransportPayment,on_delete=models.PROTECT,related_name="allocations")
    category=models.CharField(max_length=30)
    amount=models.DecimalField(max_digits=12,decimal_places=2)
    rule_version=models.CharField(max_length=60,blank=True)
    transaction=models.OneToOneField("core.Transaction",null=True,blank=True,on_delete=models.PROTECT,related_name="transport_allocation")
    reviewed_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name="reviewed_transport_allocations")
    reviewed_at=models.DateTimeField(null=True,blank=True)
    reason=models.TextField(blank=True)


class TransportRoleGrant(models.Model):
    """Auditable staff action assigning one transport role to an existing user."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transport_role_grants")
    role = models.CharField(max_length=12, choices=TransportRole.ROLE_CHOICES)
    granted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="granted_transport_roles")
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=("user", "role"), name="unique_transport_role_grant")]


class TransportAssignmentIssue(models.Model):
    """Crew reports a missing or incorrect assignment for operations review."""
    STATUS_CHOICES = [("pending", "Pending"), ("resolved", "Resolved")]
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="transport_assignment_issues")
    assignment = models.ForeignKey(CrewAssignment, null=True, blank=True, on_delete=models.PROTECT, related_name="issues")
    message = models.CharField(max_length=500)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="pending")
    resolution_reason = models.CharField(max_length=500, blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="resolved_transport_assignment_issues")
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
