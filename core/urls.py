from django.urls import path
from .loan_calculator_views import loan_estimate, loan_products
from .transport_accounting_views import transport_allocate_receipt
from .transport_views import (
    transport_role_assign,
    transport_staff_users,
    transport_routes,
    transport_vehicles,
    transport_vehicle_owner,
    transport_assignments,
    transport_assignment_end,
    crew_today,
    crew_assignment_detail,
    crew_assignment_history,
    transport_remittance_create,
    transport_remittance_stk,
    transport_cash_handover,
    transport_payment_queue,
    transport_assignment_issues,
    transport_assignment_issue_resolve,
    record_collection,
    transport_expenses,
    transport_expense_queue,
    transport_expense_review,
    transport_shift_close,
    transport_shift_recalculate,
    transport_owner_dashboard,
    transport_owner_vehicle,
    transport_remittance_receipt,
)
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
    staff_loan_guarantors,
    admin_dashboard,
    dashboard,
    my_transactions,
    my_fosa_withdrawals,
    decide_withdrawal_correction,
    withdrawal_correction_proposals,
    withdrawal_reconciliation_report,
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
    admin_crb_checks,
    admin_crb_check_detail,
    admin_crb_override,
    admin_arrears,
    chairman_summary,
    loan_appraise,
    loan_assessments,
)

urlpatterns = [
    # Transport operations: staff setup, crew shift, remittance, and review.
    path("transport/roles/", transport_role_assign, name="transport-role-assign"),
    path("transport/staff/users/", transport_staff_users, name="transport-staff-users"),
    path("transport/routes/", transport_routes, name="transport-routes"),
    path("transport/vehicles/", transport_vehicles, name="transport-vehicles"),
    path("transport/vehicles/<int:vehicle_id>/owner/", transport_vehicle_owner, name="transport-vehicle-owner"),
    path("transport/assignments/", transport_assignments, name="transport-assignments"),
    path("transport/assignments/<int:assignment_id>/end/", transport_assignment_end, name="transport-assignment-end"),
    path("transport/crew/today/", crew_today, name="transport-crew-today"),
    path("transport/crew/assignments/<int:assignment_id>/", crew_assignment_detail, name="transport-crew-assignment-detail"),
    path("transport/crew/history/", crew_assignment_history, name="transport-crew-history"),
    path("transport/collections/", record_collection, name="transport-collection"),
    path("transport/expenses/", transport_expenses, name="transport-expenses"),
    path("transport/expenses/review-queue/", transport_expense_queue, name="transport-expense-queue"),
    path("transport/expenses/<int:expense_id>/review/", transport_expense_review, name="transport-expense-review"),
    path("transport/shifts/close/", transport_shift_close, name="transport-shift-close"),
    path("transport/shifts/<int:assignment_id>/recalculate/", transport_shift_recalculate, name="transport-shift-recalculate"),
    path("transport/owner/", transport_owner_dashboard, name="transport-owner-dashboard"),
    path("transport/owner/vehicles/<int:vehicle_id>/", transport_owner_vehicle, name="transport-owner-vehicle"),
    path("transport/remittances/", transport_remittance_create, name="transport-remittance-create"),
    path("transport/remittances/<uuid:remittance_id>/receipt/", transport_remittance_receipt, name="transport-remittance-receipt"),
    path("transport/remittances/<uuid:remittance_id>/stk/", transport_remittance_stk, name="transport-remittance-stk"),
    path("transport/remittances/<uuid:remittance_id>/cash/", transport_cash_handover, name="transport-cash-handover"),
    path("transport/payment-queue/", transport_payment_queue, name="transport-payment-queue"),
    path("transport/accounting/payments/<int:payment_id>/allocate/", transport_allocate_receipt, name="transport-allocate-receipt"),
    path("transport/issues/", transport_assignment_issues, name="transport-assignment-issues"),
    path("transport/issues/<int:issue_id>/resolve/", transport_assignment_issue_resolve, name="transport-assignment-issue-resolve"),
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
    path("loan/products/",                   loan_products, name="loan-products"),
    path("loan/estimate/",                   loan_estimate, name="loan-estimate"),
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
    path("admin/loan/<int:loan_id>/guarantors/", staff_loan_guarantors),
    path("admin/loan/<int:loan_id>/approve/",approve_loan),
    path("admin/loan/<int:loan_id>/reject/", reject_loan),

    # Admin exit requests
    path("admin/exit-requests/",              admin_exit_requests),
    path("admin/exit-requests/<int:exit_id>/review/", admin_review_exit),

    # Dashboards & reports
    path("admin/dashboard/",                 admin_dashboard),
    path("admin/reports/",                   admin_reports),
    path("dashboard/",                       dashboard),
    path("transactions/",                    my_transactions, name="member-transactions"),
    path("withdrawals/",                     my_fosa_withdrawals, name="my-fosa-withdrawals"),
    path("admin/withdrawal-reconciliation/", withdrawal_reconciliation_report, name="withdrawal-reconciliation-report"),
    path("admin/withdrawal-corrections/", withdrawal_correction_proposals, name="withdrawal-correction-proposals"),
    path("admin/withdrawal-corrections/<int:proposal_id>/decision/", decide_withdrawal_correction, name="withdrawal-correction-decision"),

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

    # CRB checks
    path("admin/crb-checks/",                        admin_crb_checks,       name="admin-crb-checks"),
    path("admin/crb-checks/<int:check_id>/",         admin_crb_check_detail, name="admin-crb-check-detail"),
    path("admin/crb-checks/<int:check_id>/override/",admin_crb_override,     name="admin-crb-override"),
    # Arrears report (credit officer / treasurer)
    path("admin/arrears/",                            admin_arrears,          name="admin-arrears"),
    # Chairman cooperative summary
    path("admin/chairman/summary/",                   chairman_summary,       name="chairman-summary"),
    # Loan appraisal write-back (Item 3)
    path("admin/loan/<int:loan_id>/appraise/",        loan_appraise,          name="loan-appraise"),
    path("admin/loan/<int:loan_id>/assessments/",     loan_assessments,       name="loan-assessments"),
]
