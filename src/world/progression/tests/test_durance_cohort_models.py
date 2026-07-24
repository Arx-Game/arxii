"""Tests for DuranceCohort and CohortEnrollment models (#2479)."""

from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.progression.models.durance_cohort import CohortEnrollment, DuranceCohort
from world.societies.factories import OrganizationFactory


class DuranceCohortModelTests(TestCase):
    def test_create_cohort_and_enroll(self):
        sheet = CharacterSheetFactory()
        persona = sheet.primary_persona
        academy = OrganizationFactory(name="Shroudwatch Academy")

        cohort = DuranceCohort.objects.create(organization=academy, name="Test Cohort")
        enrollment = CohortEnrollment.objects.create(cohort=cohort, persona=persona)

        self.assertEqual(enrollment.cohort, cohort)
        self.assertEqual(enrollment.persona, persona)
        self.assertIsNotNone(enrollment.enrolled_at)
        self.assertEqual(cohort.enrollments.count(), 1)

    def test_enrollment_unique(self):
        sheet = CharacterSheetFactory()
        persona = sheet.primary_persona
        academy = OrganizationFactory(name="Shroudwatch Academy")
        cohort = DuranceCohort.objects.create(organization=academy)

        CohortEnrollment.objects.create(cohort=cohort, persona=persona)
        with self.assertRaises(IntegrityError):
            CohortEnrollment.objects.create(cohort=cohort, persona=persona)

    def test_sheet_durance_fields(self):
        sheet = CharacterSheetFactory()
        self.assertIsNone(sheet.durance_entered_at)
        self.assertIsNone(sheet.durance_cohort)
