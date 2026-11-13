from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone


class Command(BaseCommand):
    help = "Purge expired KYC document files and OCR/provider payloads; dry-run unless --apply is supplied."
    def add_arguments(self, parser): parser.add_argument("--apply",action="store_true",help="Delete files and sensitive extracted/provider data.")
    def handle(self,*args,**options):
        from accounts.models import IDVerification, AuditLog
        cutoff=timezone.now()-timedelta(days=settings.KYC_DOCUMENT_RETENTION_DAYS)
        qs=IDVerification.objects.filter(Q(verified_at__lte=cutoff)|Q(submitted_at__lte=cutoff)).filter(status__in=("verified","needs_review","provider_unavailable","submitted"))
        count=qs.count()
        if not options["apply"]:
            self.stdout.write(f"Dry run: {count} verification record(s) have KYC documents older than {settings.KYC_DOCUMENT_RETENTION_DAYS} days.")
            self.stdout.write("Rerun with --apply to delete their document files, OCR suggestions, and provider payloads.")
            return
        deleted=0
        for verification in qs.iterator():
            for field in (verification.id_document,verification.id_document_front,verification.id_document_back,verification.selfie):
                if field and field.name:
                    field.delete(save=False); deleted+=1
            verification.id_document=""; verification.id_document_front=""; verification.id_document_back=""; verification.selfie=""
            verification.ocr_result={}; verification.provider_response={}
            verification.save(update_fields=["id_document","id_document_front","id_document_back","selfie","ocr_result","provider_response","updated_at"])
        AuditLog.log(None,"other","Expired KYC documents purged",{"verification_count":count,"file_count":deleted})
        self.stdout.write(f"Purged {deleted} file(s) from {count} verification record(s).")
