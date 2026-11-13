from django.urls import path
from .payments_views import initiate_payment, payment_status, mpesa_callback, c2b_confirmation, c2b_validation

urlpatterns = [
    # Member initiates an STK push
    path("payments/mpesa/stk/",                    initiate_payment, name="mpesa-stk"),

    # Member polls for result
    path("payments/mpesa/status/<str:checkout_request_id>/", payment_status, name="mpesa-status"),

    # Daraja posts STK callback here
    path("payments/mpesa/<str:payment_type>/",     mpesa_callback,   name="mpesa-callback"),
    path("payments/mpesa/callback/",               mpesa_callback,   name="mpesa-callback-default",
         kwargs={"payment_type": ""}),

    # C2B Paybill — Safaricom registers these URLs via API
    # Validation: called before money moves (we always accept)
    path("payments/mpesa/c2b/validation/",         c2b_validation,   name="mpesa-c2b-validation"),
    # Confirmation: called after money is received — credit member's account
    path("payments/mpesa/c2b/confirmation/",       c2b_confirmation, name="mpesa-c2b-confirmation"),
]
