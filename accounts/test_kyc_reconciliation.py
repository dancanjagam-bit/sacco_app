from importlib import import_module
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import (
    IDVerification,
    KYCConsentRecord,
    KYCRiskScore,
    LivenessChallenge,
)
from accounts.services.kyc_risk import AutomatedKycAssessmentDisabled, compute_risk_score


User = get_user_model()


class KycSchemaAdoptionTests(TestCase):
    def test_incompatible_existing_index_fails_with_specific_schema_error(self):
        migration = import_module(
            "accounts.migrations.0013_alter_auditlog_action_alter_otprequest_purpose_and_more"
        )
        model = apps.get_model("accounts", "DeviceFingerprint")
        original_get_constraints = connection.introspection.get_constraints
        expected_index = model._meta.indexes[0].name

        def without_expected_index(cursor, table_name):
            result = original_get_constraints(cursor, table_name)
            if table_name == model._meta.db_table:
                result.pop(expected_index, None)
            return result

        with patch.object(
            connection.introspection,
            "get_constraints",
            side_effect=without_expected_index,
        ):
            with self.assertRaisesRegex(RuntimeError, "indexes differ"):
                migration._validate_existing_table(model, connection)


class KycReconciledEndpointTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="kyc_schema_member",
            password="NotARealPassword123!",
            email="kyc-schema@example.test",
        )
        self.client.force_authenticate(user=self.user)

    def test_workflow_and_consent_use_reconciled_tables_without_scoring(self):
        status_response = self.client.get(reverse("kyc-workflow-status"))

        self.assertEqual(status_response.status_code, 200)
        self.assertIsNone(status_response.data["risk_score"])
        self.assertEqual(status_response.data["risk_assessment"]["status"], "disabled")
        self.assertEqual(status_response.data["liveness_status"], "provider_unavailable")
        self.assertFalse(KYCRiskScore.objects.exists())

        consent_response = self.client.post(
            reverse("kyc-consent"),
            {"purpose": "id_verification", "consent_given": True},
            format="json",
        )
        self.assertEqual(consent_response.status_code, 201)
        self.assertEqual(KYCConsentRecord.objects.filter(user=self.user).count(), 1)
        verification = IDVerification.objects.get(user=self.user)
        self.assertTrue(verification.member_consent)

    def test_liveness_and_risk_actions_remain_unavailable_and_do_not_write(self):
        start_response = self.client.post(reverse("kyc-liveness-start"), {}, format="json")
        complete_response = self.client.post(
            reverse("kyc-liveness-complete", kwargs={"challenge_id": 999999}),
            {"status": "passed"},
            format="json",
        )
        risk_response = self.client.get(reverse("kyc-risk-score"))

        self.assertEqual(start_response.status_code, 503)
        self.assertEqual(complete_response.status_code, 503)
        self.assertEqual(risk_response.status_code, 503)
        self.assertFalse(LivenessChallenge.objects.exists())
        self.assertFalse(KYCRiskScore.objects.exists())

    def test_non_staff_cannot_read_member_approval_queue(self):
        response = self.client.get(reverse("kyc-admin-pending-approvals"))

        self.assertEqual(response.status_code, 403)

    def test_automated_assessment_service_cannot_be_called_directly(self):
        verification = IDVerification.objects.create(
            user=self.user,
            national_id="",
            status="draft",
        )

        with self.assertRaises(AutomatedKycAssessmentDisabled):
            compute_risk_score(verification)

        self.assertFalse(KYCRiskScore.objects.exists())
