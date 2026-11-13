"""
accounts/management/commands/createsuperuser.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Override Django's built-in createsuperuser to require a secret token
passed as an environment variable SUPERUSER_SECRET.

Usage:
    # Windows PowerShell
    $env:SUPERUSER_SECRET="sacco-super-secret-2024"; python manage.py createsuperuser

    # Linux / macOS
    SUPERUSER_SECRET=sacco-super-secret-2024 python manage.py createsuperuser

Without the correct secret the command exits immediately with an error.
--noinput is also blocked so it cannot be scripted around.
"""
import os
import sys

from django.contrib.auth.management.commands.createsuperuser import (
    Command as BaseCommand,
)
from django.core.management.base import CommandError


class Command(BaseCommand):
    help = "Create a superuser — requires SUPERUSER_SECRET env variable."

    def add_arguments(self, parser):
        super().add_arguments(parser)

    def handle(self, *args, **options):
        # ── Block --noinput so this guard cannot be bypassed silently ──────
        if options.get("interactive") is False:
            raise CommandError(
                "createsuperuser --noinput is disabled on this server. "
                "Run the command interactively with the correct SUPERUSER_SECRET."
            )

        # ── Require secret in environment ───────────────────────────────────
        required = os.getenv("SUPERUSER_SECRET", "").strip()
        if not required:
            raise CommandError(
                "\n\n"
                "  ✖  SUPERUSER_SECRET is not set.\n\n"
                "  Set it in PowerShell before running:\n"
                "      $env:SUPERUSER_SECRET=\"your-secret-here\"\n"
                "      python manage.py createsuperuser\n\n"
                "  The secret is defined in your .env file.\n"
            )

        # ── Prompt for the secret ───────────────────────────────────────────
        try:
            provided = self.stderr._out.readline if hasattr(self.stderr, '_out') else None
            provided = input("\n  Enter SUPERUSER_SECRET: ").strip()
        except (EOFError, KeyboardInterrupt):
            raise CommandError("\nAborted.")

        if provided != required:
            # Small timing delay to blunt brute-force attempts
            import time; time.sleep(2)
            raise CommandError(
                "\n  ✖  Incorrect secret. Superuser NOT created.\n"
            )

        self.stdout.write(self.style.SUCCESS("\n  ✔  Secret verified. Proceeding...\n"))
        super().handle(*args, **options)
