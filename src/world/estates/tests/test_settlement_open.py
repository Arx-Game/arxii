"""Death opens the settlement window; pacts dissolve (#1985, wiring T4)."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.estates.factories import WillFactory
from world.estates.models import EstateSettlement
from world.estates.services import open_settlement, will_is_frozen
from world.roster.factories import KinspersonFactory, UnionFactory
from world.societies.factories import OrganizationFactory
from world.societies.houses.models import MarriagePact
from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.services import _mark_dead


class OpenSettlementTests(TestCase):
    def test_open_settlement_sets_config_deadline(self):
        sheet = CharacterSheetFactory()
        before = timezone.now()
        settlement = open_settlement(sheet)
        self.assertGreaterEqual(settlement.deadline, before + timedelta(days=13))
        self.assertLessEqual(settlement.deadline, timezone.now() + timedelta(days=15))

    def test_open_settlement_is_idempotent(self):
        sheet = CharacterSheetFactory()
        first = open_settlement(sheet)
        second = open_settlement(sheet)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(EstateSettlement.objects.filter(character_sheet=sheet).count(), 1)

    def test_will_freezes_when_settlement_opens(self):
        will = WillFactory()
        self.assertFalse(will_is_frozen(will.character_sheet))
        open_settlement(will.character_sheet)
        self.assertTrue(will_is_frozen(will.character_sheet))


class MarkDeadWiringTests(TestCase):
    def _living_sheet(self):
        sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=sheet, life_state=CharacterLifeState.ALIVE)
        return sheet

    def test_mark_dead_opens_settlement(self):
        sheet = self._living_sheet()
        _mark_dead(sheet)
        self.assertEqual(sheet.vitals.life_state, CharacterLifeState.DEAD)
        self.assertTrue(EstateSettlement.objects.filter(character_sheet=sheet).exists())

    def test_mark_dead_without_kinsperson_is_safe(self):
        sheet = self._living_sheet()
        _mark_dead(sheet)  # no Kinsperson row exists — must not raise

    def test_mark_dead_dissolves_marriage_pacts(self):
        sheet = self._living_sheet()
        dead_spouse = KinspersonFactory(sheet=sheet)
        surviving_spouse = KinspersonFactory()
        union = UnionFactory(members=[dead_spouse, surviving_spouse])
        pact = MarriagePact.objects.create(
            union=union,
            senior_house=OrganizationFactory(),
            junior_house=OrganizationFactory(),
        )
        _mark_dead(sheet)
        pact.refresh_from_db()
        self.assertIsNotNone(pact.dissolved_at)

    def test_mark_dead_without_vitals_is_noop(self):
        sheet = CharacterSheetFactory()
        _mark_dead(sheet)
        self.assertFalse(EstateSettlement.objects.filter(character_sheet=sheet).exists())
