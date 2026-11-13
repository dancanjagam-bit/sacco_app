"""
accounts/management/commands/register_c2b_urls.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Register the SACCO's C2B Paybill callback URLs with Safaricom.
Run once after deployment or whenever the callback domain changes.

Usage:
    python manage.py register_c2b_urls
"""
import base64
import logging

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger("sacco.daraja")


class Command(BaseCommand):
    help = "Register C2B Paybill validation and confirmation URLs with Safaricom Daraja."

    def handle(self, *args, **options):
        key    = settings.MPESA_CONSUMER_KEY
        secret = settings.MPESA_CONSUMER_SECRET
        base   = settings.MPESA_BASE_URL
        cb     = settings.MPESA_CALLBACK_BASE_URL.rstrip("/")
        sc     = settings.MPESA_SHORTCODE

        if not key or not secret:
            self.stderr.write("MPESA_CONSUMER_KEY and MPESA_CONSUMER_SECRET must be set.")
            return
        if not cb:
            self.stderr.write("MPESA_CALLBACK_BASE_URL must be set.")
            return

        # 1. Get access token
        creds = base64.b64encode(f"{key}:{secret}".encode()).decode()
        token_url = f"{base}/oauth/v1/generate?grant_type=client_credentials"
        try:
            r = requests.get(token_url, headers={"Authorization": f"Basic {creds}"}, timeout=15)
            r.raise_for_status()
            token = r.json()["access_token"]
        except Exception as exc:
            self.stderr.write(f"Failed to get Daraja token: {exc}")
            return

        self.stdout.write(f"Token obtained. Registering URLs for shortcode {sc}...")

        # 2. Register C2B URLs
        payload = {
            "ShortCode":        sc,
            "ResponseType":     "Completed",   # always confirm even if validation is down
            "ConfirmationURL":  f"{cb}/api/payments/mpesa/c2b/confirmation/",
            "ValidationURL":    f"{cb}/api/payments/mpesa/c2b/validation/",
        }
        reg_url = f"{base}/mpesa/c2b/v1/registerurl"
        try:
            resp = requests.post(
                reg_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=20,
            )
            data = resp.json()
        except Exception as exc:
            self.stderr.write(f"Registration request failed: {exc}")
            return

        if data.get("ResponseCode") == "0" or "success" in str(data.get("ResponseDescription", "")).lower():
            self.stdout.write(self.style.SUCCESS(
                f"\n  ✔  C2B URLs registered successfully!\n"
                f"     Confirmation : {payload['ConfirmationURL']}\n"
                f"     Validation   : {payload['ValidationURL']}\n"
                f"     Shortcode    : {sc}\n\n"
                f"  Members can now deposit by:\n"
                f"    M-Pesa → Lipa na M-Pesa → Pay Bill\n"
                f"    Business No: {sc}\n"
                f"    Account No : Their member number (e.g. SACCO000001)\n"
                f"    For FOSA   : SACCO000001-FOSA\n"
            ))
        else:
            self.stderr.write(f"Registration may have failed: {data}")
