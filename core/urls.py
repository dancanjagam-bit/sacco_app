from django.urls import path
from .views import (
    deposit,
    withdraw,
    apply_loan,
    approve_loan,
    reject_loan,
    repay_loan,
    repayment_schedule,
    savings_statement,
    admin_loans,
    admin_dashboard,
    dashboard,
    loan_eligibility,
    loan_guarantors,
    guarantor_respond,
    guarantor_pending,
    my_dividends,
    pay_dividends,
    export_transactions_excel,
    export_statement_pdf,
    admin_reports,
    collateral_status,
    asset_registry,
    asset_detail,
    sacco_settings,
    sasra_reports,
    sasra_submit,
    exit_request,
    cancel_exit_request,
    admin_exit_requests,
    admin_review_exit,
    run_audit,
    audit_findings,
    review_finding,
    audit_report,
)

urlpatterns = [
    # Savings
    path("deposit/",                         deposit),
    path("withdraw/",                        withdraw),
    path("savings/statement/",               savings_statement),
    path("collateral/status/",               collateral_status),

    # Exit request (BOSA withdrawal)
    path("exit-request/",                    exit_request),
    path("exit-request/<int:exit_id>/cancel/", cancel_exit_request),

    # Loans
    path("loan/eligibility/",                loan_eligibility),
    path("loan/apply/",                      apply_loan),
    path("loan/<int:loan_id>/repay/",        repay_loan),
    path("loan/<int:loan_id>/schedule/",     repayment_schedule),
    path("loan/<int:loan_id>/guarantors/",   loan_guarantors),
    path("guarantor/<int:guarantor_id>/respond/", guarantor_respond),
    path("guarantor/pending/",               guarantor_pending),

    # Dividends
    path("dividends/",                       my_dividends),
    path("admin/dividends/pay/",             pay_dividends),

    # Admin loans
    path("admin/loans/",                     admin_loans),
    path("admin/loan/<int:loan_id>/approve/",approve_loan),
    path("admin/loan/<int:loan_id>/reject/", reject_loan),

    # Admin exit requests
    path("admin/exit-requests/",              admin_exit_requests),
    path("admin/exit-requests/<int:exit_id>/review/", admin_review_exit),

    # Dashboards & reports
    path("admin/dashboard/",                 admin_dashboard),
    path("admin/reports/",                   admin_reports),
    path("dashboard/",                       dashboard),

    # Asset collateral registry
    path("admin/assets/",                    asset_registry),
    path("admin/assets/<int:asset_id>/",    asset_detail),

    # SACCO settings
    path("admin/settings/",                  sacco_settings),

    # SASRA compliance
    path("admin/sasra/",                     sasra_reports),
    path("admin/sasra/<int:report_id>/submit/", sasra_submit),

    # Exports
    path("transactions/excel/",              export_transactions_excel),
    path("statement/pdf/",                   export_statement_pdf),

    # Financial audit engine
    path("admin/audit/run/",                 run_audit),
    path("admin/audit/findings/",            audit_findings),
    path("admin/audit/findings/<int:finding_id>/review/", review_finding),
    path("admin/audit/report/",              audit_report),
]
