from django.urls import path
from .views import (
    deposit,
    apply_loan,
    approve_loan,
    reject_loan,
    admin_loans,
    dashboard,
)

urlpatterns = [
    path("deposit/", deposit),
    path("loan/apply/", apply_loan),
    path("admin/loans/", admin_loans),
    path("admin/loan/<int:loan_id>/approve/", approve_loan),
    path("admin/loan/<int:loan_id>/reject/", reject_loan),
    path("dashboard/", dashboard),
]
