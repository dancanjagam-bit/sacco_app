"""
core/services/daraja_service.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Safaricom Daraja API client for the SACCO application.

Responsibilities
----------------
- Fetch and cache OAuth access tokens (expire every 3 600 s)
- Initiate Lipa Na M-Pesa Online (STK Push) payments
- Format Kenyan phone numbers to the E.164 format Daraja requires
- Parse and validate STK push callback payloads
- Provide human-readable payment-type descriptions for the Transaction note

Usage
-----
    from core.services.daraja_service import initiate_stk_push, DarajaError

    try:
        resp = initiate_stk_push(
            phone="0712345678",       # or +254712345678
            amount=500,
            account_ref="SACCO000001",
            transaction_desc="Registration fee",
            callback_tag="registration",   # appended to callback URL path
        )
        checkout_id = resp["CheckoutRequestID"]
    except DarajaError as exc:
        # surface exc.message to the user / log exc.raw
        ...
"""

import base64
import logging
import time
from datetime import datetime

import requests
from django.conf import settings

logger = logging.getLogger("sacco.daraja")

# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────

class DarajaError(Exception):
    """Raised when the Daraja API returns an error or the request fails."""

    def __init__(self, message: str, raw: dict | None = None):
        super().__init__(message)
        self.message = message
        self.raw = raw or {}


# ─────────────────────────────────────────────────────────────────────────────
# Simple in-process token cache (survives the request lifecycle; Django
# restarts flush it — that's fine, we just fetch a fresh one).
# ─────────────────────────────────────────────────────────────────────────────
_token_cache: dict = {"token": None, "expires_at": 0.0}


def _get_access_token() -> str:
    """
    Return a valid Daraja OAuth 2.0 access token.
    Fetches a new one only when the cached token has expired (or is absent).
    """
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        return _token_cache["token"]

    key    = settings.MPESA_CONSUMER_KEY
    secret = settings.MPESA_CONSUMER_SECRET

    if not key or not secret:
        raise DarajaError(
            "MPESA_CONSUMER_KEY and MPESA_CONSUMER_SECRET must be set in .env"
        )

    credentials = base64.b64encode(f"{key}:{secret}".encode()).decode()
    url = f"{settings.MPESA_BASE_URL}/oauth/v1/generate?grant_type=client_credentials"

    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Basic {credentials}"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise DarajaError(f"Token request failed: {exc}") from exc

    token = data.get("access_token")
    if not token:
        raise DarajaError("No access_token in Daraja OAuth response", raw=data)

    expires_in = int(data.get("expires_in", 3600))
    # Subtract 60 s as a safety buffer
    _token_cache["token"]      = token
    _token_cache["expires_at"] = now + expires_in - 60

    logger.debug("Daraja OAuth token refreshed (expires in %s s)", expires_in)
    return token


# ─────────────────────────────────────────────────────────────────────────────
# Phone-number helpers
# ─────────────────────────────────────────────────────────────────────────────

def to_safaricom_phone(phone: str) -> str:
    """
    Convert a Kenyan phone number to the 12-digit format Daraja requires.

    Accepts:
        07XXXXXXXX   (stored format in Member.phone_number)
        +254XXXXXXXX
        254XXXXXXXX
        01XXXXXXXX   (Airtel / Telkom)

    Returns:
        254XXXXXXXXX  (12 digits, no '+')

    Raises:
        DarajaError if the number cannot be normalised.
    """
    import re
    cleaned = re.sub(r"[\s\-]", "", phone)

    if re.match(r"^254[17]\d{8}$", cleaned):
        return cleaned                          # already in correct format

    if re.match(r"^\+254[17]\d{8}$", cleaned):
        return cleaned[1:]                      # strip leading '+'

    if re.match(r"^0[17]\d{8}$", cleaned):
        return "254" + cleaned[1:]              # 0XXXXXXXXX → 254XXXXXXXXX

    raise DarajaError(
        f"'{phone}' is not a valid Kenyan mobile number for M-Pesa. "
        "Expected format: 07XXXXXXXX or +254XXXXXXXX"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Timestamp & password helpers
# ─────────────────────────────────────────────────────────────────────────────

def _generate_password() -> tuple[str, str]:
    """
    Generate the Lipa Na M-Pesa Online password and timestamp.

    Returns:
        (password_b64, timestamp_str)
        timestamp is YYYYMMDDHHmmss
    """
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    raw = settings.MPESA_SHORTCODE + settings.MPESA_PASSKEY + timestamp
    # Length varies with shortcode + passkey length — Daraja accepts any valid b64
    password = base64.b64encode(raw.encode()).decode()
    return password, timestamp


# ─────────────────────────────────────────────────────────────────────────────
# STK Push
# ─────────────────────────────────────────────────────────────────────────────

def initiate_stk_push(
    phone: str,
    amount: int,
    account_ref: str,
    transaction_desc: str,
    callback_tag: str = "callback",
) -> dict:
    """
    Initiate a Lipa Na M-Pesa Online (STK Push) payment request.

    Parameters
    ----------
    phone           : Member's phone number (any normalised Kenyan format)
    amount          : Amount in KES — must be a whole number ≥ 1
    account_ref     : Reference shown on the member's M-Pesa receipt
                      (e.g. member number "SACCO000001")
    transaction_desc: Short description shown in the STK prompt
                      (max 13 chars — Daraja truncates silently)
    callback_tag    : Appended to MPESA_CALLBACK_BASE_URL to route different
                      payment types, e.g. "deposit", "registration", "repayment"

    Returns
    -------
    The raw Daraja JSON response dict on success, which contains:
        MerchantRequestID   : str
        CheckoutRequestID   : str  ← store this to match the callback
        ResponseCode        : "0" on success
        ResponseDescription : str
        CustomerMessage     : str

    Raises
    ------
    DarajaError on any failure (network, API error, bad phone number).
    """
    amount = max(1, int(amount))                # Daraja rejects decimals
    safari_phone = to_safaricom_phone(phone)
    password, timestamp = _generate_password()
    token = _get_access_token()

    callback_base = settings.MPESA_CALLBACK_BASE_URL.rstrip("/")
    callback_url  = f"{callback_base}/api/payments/mpesa/{callback_tag}/"

    payload = {
        "BusinessShortCode": settings.MPESA_SHORTCODE,
        "Password":          password,
        "Timestamp":         timestamp,
        "TransactionType":   "CustomerPayBillOnline",
        "Amount":            amount,
        "PartyA":            safari_phone,
        "PartyB":            settings.MPESA_SHORTCODE,
        "PhoneNumber":       safari_phone,
        "CallBackURL":       callback_url,
        "AccountReference":  account_ref[:12],   # Daraja max 12 chars
        "TransactionDesc":   transaction_desc[:13],
    }

    logger.info(
        "STK push to phone ending %s amount=%s ref=%s tag=%s",
        safari_phone[-4:], amount, account_ref, callback_tag.split("/")[0],
    )

    url = f"{settings.MPESA_BASE_URL}/mpesa/stkpush/v1/processrequest"
    try:
        resp = requests.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type":  "application/json",
            },
            timeout=30,
        )
        # If Daraja returns 401, our token expired — flush the cache and retry once
        if resp.status_code == 401:
            logger.warning("Daraja 401 on STK push — flushing token cache and retrying")
            _token_cache["token"]      = None
            _token_cache["expires_at"] = 0.0
            token = _get_access_token()
            resp = requests.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type":  "application/json",
                },
                timeout=30,
            )
        resp.raise_for_status()
        data = resp.json()
    except requests.HTTPError as exc:
        # Log the full Daraja error body for diagnosis
        try:
            err_body = exc.response.json()
        except Exception:
            err_body = exc.response.text if exc.response else str(exc)
        logger.error(
            "Daraja STK push HTTP error %s: %s",
            exc.response.status_code if exc.response else "?",
            err_body,
        )
        raise DarajaError(
            f"STK push rejected (HTTP {exc.response.status_code if exc.response else '?'}): "
            f"{err_body.get('errorMessage', err_body) if isinstance(err_body, dict) else err_body}",
            raw=err_body if isinstance(err_body, dict) else {},
        ) from exc
    except requests.RequestException as exc:
        raise DarajaError(f"STK push request failed: {exc}") from exc

    if data.get("ResponseCode") != "0":
        logger.warning("STK push rejected by Daraja: %s", data)
        raise DarajaError(
            data.get("ResponseDescription", "STK push rejected by Daraja"),
            raw=data,
        )

    logger.info(
        "STK push accepted — CheckoutRequestID=%s",
        data.get("CheckoutRequestID"),
    )
    return data


# ─────────────────────────────────────────────────────────────────────────────
# Callback payload parser
# ─────────────────────────────────────────────────────────────────────────────

def parse_stk_callback(body: dict) -> dict:
    """
    Extract the useful fields from a Daraja STK callback POST body.

    Returns a normalised dict:
    {
        "success":           bool,
        "checkout_request_id": str,
        "result_code":       int,
        "result_desc":       str,
        "mpesa_receipt":     str | None,   # M-Pesa transaction code e.g. "QJL7XXXXXX"
        "amount":            float | None,
        "phone":             str | None,   # 254XXXXXXXXX format
        "transaction_date":  str | None,   # raw Daraja timestamp string
    }

    Raises DarajaError if the body structure is unexpected.
    """
    try:
        stk = body["Body"]["stkCallback"]
        checkout_id  = stk["CheckoutRequestID"]
        result_code  = int(stk["ResultCode"])
        result_desc  = stk.get("ResultDesc", "")
        if not isinstance(checkout_id, str) or not checkout_id.strip():
            raise ValueError("CheckoutRequestID must be a nonempty string")
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise DarajaError(f"Malformed STK callback body: {exc}", raw=body) from exc

    result: dict = {
        "success":             result_code == 0,
        "checkout_request_id": checkout_id,
        "merchant_request_id": stk.get("MerchantRequestID", ""),
        "merchant_request_id": stk.get("MerchantRequestID"),
        "result_code":         result_code,
        "result_desc":         result_desc,
        "mpesa_receipt":       None,
        "amount":              None,
        "phone":               None,
        "transaction_date":    None,
    }

    if result_code == 0:
        # CallbackMetadata items — indexed by Name
        try:
            items = {
                item["Name"]: item.get("Value")
                for item in stk.get("CallbackMetadata", {}).get("Item", [])
            }
        except (AttributeError, KeyError, TypeError) as exc:
            raise DarajaError("Malformed STK callback metadata", raw=body) from exc
        result["mpesa_receipt"]    = items.get("MpesaReceiptNumber")
        result["amount"]           = items.get("Amount")
        result["phone"]            = str(items["PhoneNumber"]) if items.get("PhoneNumber") else None
        result["transaction_date"] = items.get("TransactionDate")

    logger.info(
        "STK callback parsed — success=%s receipt=%s checkout=%s",
        result["success"], result["mpesa_receipt"], checkout_id,
    )
    return result
