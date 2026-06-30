"""Tests for CourtPact model + swear/release services (Task 3, #1589)."""

from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType
from world.covenants.exceptions import CourtPactExistsError
from world.covenants.factories import CovenantFactory
from world.covenants.models import CourtPact
from world.covenants.services import active_court_pact_for, release_court_pact, swear_court_pact


class SwearCourtPactTests(TestCase):
    """Tests for swear_court_pact service."""

    @classmethod
    def setUpTestData(cls):
        cls.covenant = CovenantFactory(covenant_type=CovenantType.COURT)
        cls.servant = CharacterSheetFactory()
        cls.other_servant = CharacterSheetFactory()

    def test_creates_active_pact(self):
        pact = swear_court_pact(
            covenant=self.covenant,
            servant_sheet=self.servant,
            granted_pull_cap=3,
        )
        self.assertIsInstance(pact, CourtPact)
        self.assertEqual(pact.covenant, self.covenant)
        self.assertEqual(pact.servant_sheet, self.servant)
        self.assertEqual(pact.granted_pull_cap, 3)
        self.assertIsNone(pact.released_at)
        self.assertIsNotNone(pact.sworn_at)

    def test_granted_pull_cap_persists(self):
        pact = swear_court_pact(
            covenant=self.covenant,
            servant_sheet=self.other_servant,
            granted_pull_cap=5,
        )
        pact.refresh_from_db()
        self.assertEqual(pact.granted_pull_cap, 5)

    def test_default_pull_cap_is_zero(self):
        covenant = CovenantFactory(covenant_type=CovenantType.COURT)
        servant = CharacterSheetFactory()
        pact = swear_court_pact(covenant=covenant, servant_sheet=servant, granted_pull_cap=0)
        self.assertEqual(pact.granted_pull_cap, 0)

    def test_duplicate_active_pact_raises(self):
        covenant = CovenantFactory(covenant_type=CovenantType.COURT)
        servant = CharacterSheetFactory()
        swear_court_pact(covenant=covenant, servant_sheet=servant, granted_pull_cap=0)
        with self.assertRaises(CourtPactExistsError):
            swear_court_pact(covenant=covenant, servant_sheet=servant, granted_pull_cap=1)

    def test_different_servants_in_same_covenant_allowed(self):
        covenant = CovenantFactory(covenant_type=CovenantType.COURT)
        servant_a = CharacterSheetFactory()
        servant_b = CharacterSheetFactory()
        pact_a = swear_court_pact(covenant=covenant, servant_sheet=servant_a, granted_pull_cap=0)
        pact_b = swear_court_pact(covenant=covenant, servant_sheet=servant_b, granted_pull_cap=0)
        self.assertNotEqual(pact_a.pk, pact_b.pk)

    def test_same_servant_in_different_covenants_allowed(self):
        covenant_a = CovenantFactory(covenant_type=CovenantType.COURT)
        covenant_b = CovenantFactory(covenant_type=CovenantType.COURT)
        servant = CharacterSheetFactory()
        pact_a = swear_court_pact(covenant=covenant_a, servant_sheet=servant, granted_pull_cap=0)
        pact_b = swear_court_pact(covenant=covenant_b, servant_sheet=servant, granted_pull_cap=0)
        self.assertNotEqual(pact_a.pk, pact_b.pk)


class ReleaseCourtPactTests(TestCase):
    """Tests for release_court_pact service."""

    @classmethod
    def setUpTestData(cls):
        cls.covenant = CovenantFactory(covenant_type=CovenantType.COURT)
        cls.servant = CharacterSheetFactory()

    def test_release_sets_released_at(self):
        pact = swear_court_pact(
            covenant=self.covenant,
            servant_sheet=self.servant,
            granted_pull_cap=0,
        )
        before = timezone.now()
        release_court_pact(pact=pact)
        pact.refresh_from_db()
        self.assertIsNotNone(pact.released_at)
        self.assertGreaterEqual(pact.released_at, before)

    def test_release_returns_none(self):
        covenant = CovenantFactory(covenant_type=CovenantType.COURT)
        servant = CharacterSheetFactory()
        pact = swear_court_pact(covenant=covenant, servant_sheet=servant, granted_pull_cap=0)
        result = release_court_pact(pact=pact)
        self.assertIsNone(result)

    def test_new_pact_can_be_sworn_after_release(self):
        covenant = CovenantFactory(covenant_type=CovenantType.COURT)
        servant = CharacterSheetFactory()
        pact1 = swear_court_pact(covenant=covenant, servant_sheet=servant, granted_pull_cap=0)
        release_court_pact(pact=pact1)
        pact2 = swear_court_pact(covenant=covenant, servant_sheet=servant, granted_pull_cap=2)
        self.assertNotEqual(pact1.pk, pact2.pk)
        self.assertIsNone(pact2.released_at)
        self.assertEqual(pact2.granted_pull_cap, 2)

    def test_historical_pact_preserved_after_release(self):
        covenant = CovenantFactory(covenant_type=CovenantType.COURT)
        servant = CharacterSheetFactory()
        pact = swear_court_pact(covenant=covenant, servant_sheet=servant, granted_pull_cap=0)
        release_court_pact(pact=pact)
        # Row must still exist — soft-delete only
        self.assertTrue(CourtPact.objects.filter(pk=pact.pk).exists())


class ActiveCourtPactForTests(TestCase):
    """Tests for active_court_pact_for selector."""

    @classmethod
    def setUpTestData(cls):
        cls.covenant = CovenantFactory(covenant_type=CovenantType.COURT)
        cls.servant = CharacterSheetFactory()

    def test_returns_active_pact(self):
        pact = swear_court_pact(
            covenant=self.covenant,
            servant_sheet=self.servant,
            granted_pull_cap=1,
        )
        found = active_court_pact_for(covenant=self.covenant, servant_sheet=self.servant)
        self.assertEqual(found, pact)

    def test_returns_none_when_no_pact(self):
        covenant = CovenantFactory(covenant_type=CovenantType.COURT)
        servant = CharacterSheetFactory()
        result = active_court_pact_for(covenant=covenant, servant_sheet=servant)
        self.assertIsNone(result)

    def test_returns_none_after_release(self):
        covenant = CovenantFactory(covenant_type=CovenantType.COURT)
        servant = CharacterSheetFactory()
        pact = swear_court_pact(covenant=covenant, servant_sheet=servant, granted_pull_cap=0)
        release_court_pact(pact=pact)
        result = active_court_pact_for(covenant=covenant, servant_sheet=servant)
        self.assertIsNone(result)

    def test_returns_new_pact_after_reswear(self):
        covenant = CovenantFactory(covenant_type=CovenantType.COURT)
        servant = CharacterSheetFactory()
        pact1 = swear_court_pact(covenant=covenant, servant_sheet=servant, granted_pull_cap=0)
        release_court_pact(pact=pact1)
        pact2 = swear_court_pact(covenant=covenant, servant_sheet=servant, granted_pull_cap=3)
        found = active_court_pact_for(covenant=covenant, servant_sheet=servant)
        self.assertEqual(found, pact2)
