from django.urls import path
from .views import deposit, apply_loan, approve_loan, dashboard

urlpatterns = [
    path("deposit/", deposit),
    path("loan/apply/", apply_loan),
    path("loan/<int:loan_id>/approve/", approve_loan),
    path("dashboard/", dashboard),
]
