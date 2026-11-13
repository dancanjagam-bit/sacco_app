"""
accounts/management/commands/send_overdue_alerts.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Send SMS/email alerts to members with overdue loan installments.
Run daily via Railway's cron scheduler or a cron job:

    0 8 * * * python manage.py send_overdue_alerts

"""
from decimal import Decimal
from datetime import date
from dateutil.relativedelta import relativedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import Loan, Transaction
from sacco.notifications import _send_sms, _send_email
import logging

logger = logging.getLogger("sacco")


class Command(BaseCommand):
    help = "Send overdue loan repayment reminders to delinquent members."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show what would be sent without actually sending.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        today   = date.today()
        sent    = 0
        skipped = 0

        active_loans = Loan.objects.filter(status="approved").select_related("user")

        for loan in active_loans:
            if not loan.approved_at:
                continue

            total_payable   = loan.amount + (loan.amount * loan.interest / Decimal("100"))
            monthly_payment = total_payable / loan.repayment_months
            start_date      = loan.approved_at

            repayments = list(
                Transaction.objects.filter(
                    user=loan.user, type="repayment",
                    note__contains=f"Loan #{loan.id}",
                ).order_by("created_at")
            )

            overdue_installments = 0
            overdue_amount       = Decimal("0")
            oldest_days          = 0

            for i in range(1, loan.repayment_months + 1):
                due_date = (start_date + relativedelta(months=i)).date()
                if due_date > today:
                    break
                paid = repayments[i - 1].amount if i <= len(repayments) else Decimal("0")
                if paid < monthly_payment:
                    overdue_installments += 1
                    overdue_amount       += (monthly_payment - paid)
                    days = (today - due_date).days
                    if days > oldest_days:
                        oldest_days = days

            if overdue_installments == 0:
                skipped += 1
                continue

            user  = loan.user
            phone = getattr(getattr(user, "member_profile", None), "phone_number", "")
            name  = user.get_full_name() or user.username

            sms_msg = (
                f"SACCO NOTICE: Dear {name}, your Loan #{loan.id} has "
                f"{overdue_installments} overdue installment(s) totalling "
                f"KES {overdue_amount:,.0f}. Please pay immediately to avoid penalties. "
                f"Contact: {phone}"
            )

            email_body = (
                f"Dear {name},\n\n"
                f"This is a reminder that your SACCO Loan #{loan.id} has overdue installments.\n\n"
                f"Overdue installments: {overdue_installments}\n"
                f"Total overdue amount: KES {overdue_amount:,.2f}\n"
                f"Oldest overdue by: {oldest_days} days\n\n"
                f"Please log in to your SACCO portal and make a repayment as soon as possible.\n\n"
                f"SACCO Management"
            )

            if dry_run:
                self.stdout.write(f"[DRY RUN] Would notify {name} ({phone}) — Loan #{loan.id}, overdue KES {overdue_amount:,.0f}")
            else:
                if phone:
                    _send_sms(phone, sms_msg)
                _send_email(user.email, f"SACCO: Overdue Loan #{loan.id} — Action Required", email_body)
                logger.info("Overdue alert sent to %s for Loan #%s", user.username, loan.id)

            sent += 1

        self.stdout.write(self.style.SUCCESS(
            f"\n  Overdue alerts: {sent} sent, {skipped} current loans skipped."
        ))
