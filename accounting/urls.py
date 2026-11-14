from django.urls import path

from .views import (
    approve_share_policy,
    create_share_policy,
    journal_entries,
    journal_entry_detail,
    ledger_accounts,
    legacy_reconciliation_report,
    post_staff_adjustment,
    reverse_staff_entry,
    share_capital_movements,
    trial_balance,
    update_ledger_account,
)

urlpatterns = [
    path("reconciliation/legacy/", legacy_reconciliation_report, name="accounting-legacy-reconciliation"),
    path("accounts/", ledger_accounts, name="accounting-accounts"),
    path("accounts/<int:account_id>/", update_ledger_account, name="accounting-account-update"),
    path("trial-balance/", trial_balance, name="accounting-trial-balance"),
    path("journal-entries/", journal_entries, name="accounting-journal-entries"),
    path("journal-entries/<uuid:entry_id>/", journal_entry_detail, name="accounting-journal-entry-detail"),
    path("journal-entries/adjustments/", post_staff_adjustment, name="accounting-staff-adjustment"),
    path("journal-entries/<uuid:entry_id>/reverse/", reverse_staff_entry, name="accounting-entry-reversal"),
    path("share-capital/", share_capital_movements, name="accounting-share-capital"),
    path("share-capital/policies/", create_share_policy, name="accounting-share-policy-create"),
    path("share-capital/policies/<int:policy_id>/approve/", approve_share_policy, name="accounting-share-policy-approve"),
]
