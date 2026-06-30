"""Tests for Covenant of the Court model validation (Task 1)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import CovenantFactory


class CourtModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.master = CharacterSheetFactory()

    def test_court_requires_leader(self):
        cov = CovenantFactory.build(covenant_type=CovenantType.COURT)
        cov.leader = None
        with self.assertRaises(ValidationError):
            cov.clean()

    def test_court_accepts_leader(self):
        cov = CovenantFactory.build(covenant_type=CovenantType.COURT)
        cov.leader = self.master
        cov.clean()  # no raise

    def test_non_court_forbids_leader(self):
        cov = CovenantFactory.build(covenant_type=CovenantType.DURANCE)
        cov.leader = self.master
        with self.assertRaises(ValidationError):
            cov.clean()
