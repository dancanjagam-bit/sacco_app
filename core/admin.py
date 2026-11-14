from django.contrib import admin
from django import forms
from accounting.services import InvalidJournal
from accounts.models import AuditLog
from .services.transport_accounting import allocation_terms
from .transport_models import TransportAllocationRule
from django.utils import timezone
from .models import (Savings, Loan, Transaction, LoanGuarantor, AssetCollateral, SACCOSettings, SASRAReport, SavingsDividend, ExitRequest, AuditFinding, TransportDeductionRule)


@admin.register(Savings)
class SavingsAdmin(admin.ModelAdmin):
    list_display  = ("user", "amount", "created_at")
    list_filter   = ("created_at",)
    search_fields = ("user__username", "user__first_name", "user__last_name")
    date_hierarchy = "created_at"


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display  = ("id", "user", "amount", "collateral_type", "purpose", "interest", "repayment_months", "balance", "status", "created_at")
    list_filter   = ("status", "purpose", "collateral_type")
    search_fields = ("user__username", "user__first_name", "user__last_name")
    date_hierarchy = "created_at"
    readonly_fields = ("savings_months", "total_savings_at_application", "approved_at", "approved_by")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display  = ("user", "type", "amount", "note", "created_at")
    list_filter   = ("type",)
    search_fields = ("user__username", "note")
    date_hierarchy = "created_at"


@admin.register(LoanGuarantor)
class LoanGuarantorAdmin(admin.ModelAdmin):
    list_display  = ("loan", "guarantor", "pledged_amount", "locked_amount", "status", "responded_at", "created_at")
    list_filter   = ("status",)
    search_fields = ("loan__user__username", "guarantor__username")


@admin.register(AssetCollateral)
class AssetCollateralAdmin(admin.ModelAdmin):
    list_display  = ("user", "asset_type", "forced_sale_value", "max_loan_cap", "status", "loan", "created_at")
    list_filter   = ("asset_type", "status")
    search_fields = ("user__username", "description", "registration_ref")


@admin.register(SACCOSettings)
class SACCOSettingsAdmin(admin.ModelAdmin):
    list_display = ("name", "release_hierarchy", "default_ltv_ratio", "min_savings_retention", "sasra_enabled")


@admin.register(SASRAReport)
class SASRAReportAdmin(admin.ModelAdmin):
    list_display  = ("report_type", "period_start", "period_end", "status", "generated_by", "created_at")
    list_filter   = ("report_type", "status")
    readonly_fields = ("data_snapshot", "generated_by", "submitted_at")


@admin.register(SavingsDividend)
class SavingsDividendAdmin(admin.ModelAdmin):
    list_display  = ("user", "year", "rate", "savings_balance", "amount", "paid_at")
    list_filter   = ("year",)
    search_fields = ("user__username",)


@admin.register(ExitRequest)
class ExitRequestAdmin(admin.ModelAdmin):
    list_display  = ("user", "status", "bosa_balance", "has_active_loan", "has_guarantor_pledges", "release_date", "created_at")
    list_filter   = ("status",)
    search_fields = ("user__username", "user__first_name", "user__last_name")
    readonly_fields = ("bosa_balance", "has_active_loan", "has_guarantor_pledges", "created_at")


@admin.register(AuditFinding)
class AuditFindingAdmin(admin.ModelAdmin):
    list_display  = ("rule", "severity", "title", "user", "status", "created_at")
    list_filter   = ("severity", "status", "rule")
    search_fields = ("title", "description", "user")
    readonly_fields = ("audit_run_id", "created_at", "reviewed_by", "reviewed_at")


@admin.register(TransportDeductionRule)
class TransportDeductionRuleAdmin(admin.ModelAdmin):
    list_display = ("version", "active", "approval_reference", "approved_by", "approved_at")
    list_filter = ("active",)
    readonly_fields = ("approved_by", "approved_at", "created_at")
    fields = ("version", "deductible_categories", "approval_reference", "active", "approved_by", "approved_at", "created_at")

    def has_module_permission(self, request):
        return bool(request.user and request.user.is_superuser)

    def has_view_permission(self, request, obj=None):
        return bool(request.user and request.user.is_superuser)

    def has_add_permission(self, request):
        return bool(request.user and request.user.is_superuser)

    def has_change_permission(self, request, obj=None):
        return bool(request.user and request.user.is_superuser)

    def has_delete_permission(self, request, obj=None):
        return bool(request.user and request.user.is_superuser)

    def save_model(self, request, obj, form, change):
        if obj.active:
            obj.approved_by = request.user
            obj.approved_at = timezone.now()
        super().save_model(request, obj, form, change)


class TransportAllocationRuleForm(forms.ModelForm):
    def clean_allocations(self):
        definition = self.cleaned_data["allocations"]
        try:
            allocation_terms(definition)
        except InvalidJournal as exc:
            raise forms.ValidationError(str(exc)) from exc
        return definition

    def clean(self):
        data = super().clean()
        if data.get("active") and TransportAllocationRule.objects.filter(
            active=True,
        ).exclude(pk=self.instance.pk).exists():
            self.add_error("active", "Deactivate the current allocation version first.")
        return data


@admin.register(TransportAllocationRule)
class TransportAllocationRuleAdmin(TransportDeductionRuleAdmin):
    form = TransportAllocationRuleForm
    fields = ("version", "allocations", "active", "approved_by", "approved_at", "created_at")
    list_display = ("version", "active", "approved_by", "approved_at")

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        return (*fields, "version", "allocations") if obj and obj.approved_at else fields

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        AuditLog.log(request.user, "other", f"Transport allocation policy {obj.version}", {
            "operation": "allocation_policy_saved", "active": obj.active,
            "approval_reference": obj.allocations["approval_reference"],
        }, request)

