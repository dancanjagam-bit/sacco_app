"""
Notification delivery service.
Handles Email (Django SMTP) and SMS (Africa's Talking).
Falls back to console printing in development.
"""
import logging
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

logger = logging.getLogger("sacco")


def _send_email(to_email: str, subject: str, body: str, html_body: str = None):
    if not to_email:
        return
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email],
            html_message=html_body,
            fail_silently=False,
        )
        logger.info(f"Email sent to {to_email}: {subject}")
    except Exception as e:
        logger.error(f"Email failed to {to_email}: {e}")


def _send_sms(to_phone: str, message: str):
    """Send SMS via Africa's Talking."""
    at_username = getattr(settings, "AT_USERNAME", "")
    at_api_key  = getattr(settings, "AT_API_KEY", "")

    if not at_username or not at_api_key:
        # Dev fallback — just log it
        logger.info(f"[SMS → {to_phone}] {message}")
        print(f"\n📱 SMS → {to_phone}\n{message}\n")
        return

    try:
        import africastalking
        africastalking.initialize(at_username, at_api_key)
        sms = africastalking.SMS
        # Kenya numbers need +254 prefix
        phone = to_phone
        if phone.startswith("0"):
            phone = "+254" + phone[1:]
        response = sms.send(message, [phone])
        logger.info(f"SMS sent to {phone}: {response}")
    except Exception as e:
        logger.error(f"SMS failed to {to_phone}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Public API — call these from views
# ─────────────────────────────────────────────────────────────────────────────

def send_otp(user, otp_code: str, method: str):
    """Deliver OTP via the chosen method."""
    msg = f"Your SACCO OTP is: {otp_code}. Valid for 10 minutes. Do not share this code."

    if method == "email":
        _send_email(user.email, "SACCO — Your OTP Code", msg)

    elif method == "recovery_email":
        _send_email(user.recovery_email, "SACCO — Your OTP Code", msg)

    elif method == "phone":
        phone = getattr(getattr(user, "member_profile", None), "phone_number", "")
        _send_sms(phone, msg)

    elif method == "recovery_phone":
        _send_sms(user.recovery_phone, msg)

    else:
        logger.warning(f"Unknown OTP method: {method}")


def send_welcome(user, member_number: str):
    subject = "Welcome to SACCO — Your Account is Ready"
    body = (
        f"Dear {user.get_full_name() or user.username},\n\n"
        f"Welcome to SACCO Management System!\n\n"
        f"Your member number is: {member_number}\n"
        f"Username: {user.username}\n\n"
        f"You can log in at your SACCO portal.\n\n"
        f"Best regards,\nSACCO Management"
    )
    _send_email(user.email, subject, body)


def send_loan_approved(user, loan):
    subject = "Your Loan Has Been Approved! 🎉"
    body = (
        f"Dear {user.get_full_name() or user.username},\n\n"
        f"Great news! Your loan application has been approved.\n\n"
        f"Loan Amount: KES {loan.amount:,.2f}\n"
        f"Interest Rate: {loan.interest}%\n"
        f"Repayment Period: {loan.repayment_months} months\n"
        f"Total Payable: KES {loan.balance:,.2f}\n\n"
        f"Log in to your account to view the repayment schedule.\n\n"
        f"Best regards,\nSACCO Management"
    )
    phone = getattr(getattr(user, "member_profile", None), "phone_number", "")
    sms   = f"SACCO: Loan KES {loan.amount:,.0f} approved! Total payable: KES {loan.balance:,.0f} over {loan.repayment_months} months."

    _send_email(user.email, subject, body)
    if phone:
        _send_sms(phone, sms)


def send_loan_rejected(user, loan):
    subject = "SACCO Loan Application Update"
    body = (
        f"Dear {user.get_full_name() or user.username},\n\n"
        f"We regret to inform you that your loan application of KES {loan.amount:,.2f} was not approved at this time.\n\n"
        f"Reason: {loan.remarks or 'Please contact SACCO office for details.'}\n\n"
        f"You are welcome to apply again after addressing the above.\n\n"
        f"Best regards,\nSACCO Management"
    )
    phone = getattr(getattr(user, "member_profile", None), "phone_number", "")
    sms   = f"SACCO: Your loan application of KES {loan.amount:,.0f} was not approved. Reason: {(loan.remarks or 'Contact SACCO')[:80]}"

    _send_email(user.email, subject, body)
    if phone:
        _send_sms(phone, sms)


def send_deposit_confirmation(user, amount: float, balance: float):
    phone = getattr(getattr(user, "member_profile", None), "phone_number", "")
    sms   = f"SACCO: KES {amount:,.0f} deposited. New balance: KES {balance:,.0f}."
    if phone:
        _send_sms(phone, sms)


def send_repayment_confirmation(user, loan_id: int, amount: float, remaining: float):
    phone = getattr(getattr(user, "member_profile", None), "phone_number", "")
    if remaining == 0:
        sms = f"SACCO: KES {amount:,.0f} received. Loan #{loan_id} FULLY REPAID! Congratulations."
    else:
        sms = f"SACCO: KES {amount:,.0f} received for Loan #{loan_id}. Remaining: KES {remaining:,.0f}."
    if phone:
        _send_sms(phone, sms)
