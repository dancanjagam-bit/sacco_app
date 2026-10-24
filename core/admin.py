from django.contrib import admin
from .models import Savings, Loan, Transaction, LoanGuarantor, AssetCollateral, SACCOSettings, SASRAReport, SavingsDividend, ExitRequest


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
