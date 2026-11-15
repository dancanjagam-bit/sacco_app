from contextlib import nullcontext

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor


PROFILE_PHOTO_MIGRATION = ("members", "0005_memberprofilephoto")


class Command(BaseCommand):
    help = "Apply only the additive member profile photo migration before serving traffic."

    def handle(self, *args, **options):
        postgres = connection.vendor == "postgresql"
        with transaction.atomic() if postgres else nullcontext():
            if postgres:
                # Two Render instances can start during the same rollout.
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", [53219, 5005])
            executor = MigrationExecutor(connection)
            if PROFILE_PHOTO_MIGRATION in executor.loader.applied_migrations:
                return
            plan = executor.migration_plan([PROFILE_PHOTO_MIGRATION])
            if [(migration.app_label, migration.name, backwards) for migration, backwards in plan] != [
                (*PROFILE_PHOTO_MIGRATION, False)
            ]:
                raise CommandError("Profile photo migration requires existing member migrations to be applied first.")
            executor.migrate([PROFILE_PHOTO_MIGRATION], plan=plan)
        self.stdout.write(self.style.SUCCESS("Member profile photo schema is ready."))
