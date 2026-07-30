"""Appetite anima economy (#2853): regen skip, upkeep drains, glut, Ravenous mapping.

SQLite tier — nothing here fires apply_condition (PG-only); Ravenous reconcile
control flow is covered with patched condition services.
"""

from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.models import CharacterDistinction
from world.magic.models.anima import CharacterAnima
from world.magic.models.appetites import AppetitePeriod, AppetiteUpkeepReceipt
from world.magic.services.anima import anima_regen_tick
from world.magic.services.appetites import (
    appetite_holder_sheet_ids,
    appetite_upkeep_tick,
    decay_glut_tick,
    hunger_severity,
    reconcile_ravenous,
)
from world.species.factories import (
    ensure_appetite_distinctions,
    ensure_appetite_upkeep,
    ensure_ravenous_condition,
)


def _anima(sheet, *, current=10, maximum=10, glut=0):
    anima, _ = CharacterAnima.objects.update_or_create(
        character=sheet,
        defaults={"current": current, "maximum": maximum, "glut": glut},
    )
    return anima


class AppetiteRegenSkipTest(TestCase):
    def test_appetite_holders_never_regen_naturally(self):
        from world.mechanics.factories import BlocksAnimaRegenPropertyFactory

        BlocksAnimaRegenPropertyFactory()
        blood, _essence = ensure_appetite_distinctions()
        vampire = CharacterSheetFactory()
        CharacterDistinction.objects.create(character=vampire, distinction=blood)
        mortal = CharacterSheetFactory()
        _anima(vampire, current=5)
        _anima(mortal, current=5)
        self.assertIn(vampire.pk, appetite_holder_sheet_ids())
        anima_regen_tick()
        self.assertEqual(CharacterAnima.objects.get(character=vampire).current, 5)
        self.assertGreater(CharacterAnima.objects.get(character=mortal).current, 5)


class AppetiteUpkeepTest(TestCase):
    def setUp(self):
        self.blood, _essence = ensure_appetite_distinctions()
        ensure_appetite_upkeep()
        self.vampire = CharacterSheetFactory()
        CharacterDistinction.objects.create(character=self.vampire, distinction=self.blood)

    def test_weekly_drain_with_receipt_idempotency(self):
        _anima(self.vampire, current=10)
        with patch("world.magic.services.appetites.reconcile_ravenous"):
            drained = appetite_upkeep_tick(AppetitePeriod.WEEKLY)
            self.assertEqual(drained, 1)
            self.assertEqual(CharacterAnima.objects.get(character=self.vampire).current, 9)
            again = appetite_upkeep_tick(AppetitePeriod.WEEKLY)
        self.assertEqual(again, 0)
        self.assertEqual(CharacterAnima.objects.get(character=self.vampire).current, 9)
        self.assertEqual(AppetiteUpkeepReceipt.objects.count(), 1)

    def test_floor_stops_the_drain(self):
        """Floor 10% of max 10 = 1: a starved vampire dims to the floor, never below."""
        _anima(self.vampire, current=1)
        with patch("world.magic.services.appetites.reconcile_ravenous"):
            drained = appetite_upkeep_tick(AppetitePeriod.WEEKLY)
        self.assertEqual(drained, 0)
        self.assertEqual(CharacterAnima.objects.get(character=self.vampire).current, 1)
        receipt = AppetiteUpkeepReceipt.objects.get()
        self.assertEqual(receipt.drained, 0)

    def test_glut_never_satisfies_the_floor(self):
        """A glutted-but-empty vampire still reads as at-floor: glut is not a tank."""
        _anima(self.vampire, current=1, glut=5)
        with patch("world.magic.services.appetites.reconcile_ravenous"):
            appetite_upkeep_tick(AppetitePeriod.WEEKLY)
        anima = CharacterAnima.objects.get(character=self.vampire)
        self.assertEqual(anima.current, 1)
        self.assertEqual(anima.glut, 5)


class GlutTest(TestCase):
    def test_glut_decays_daily(self):
        sheet = CharacterSheetFactory()
        _anima(sheet, glut=3)
        decay_glut_tick()
        self.assertEqual(CharacterAnima.objects.get(character=sheet).glut, 2)

    def test_effective_current_includes_glut(self):
        sheet = CharacterSheetFactory()
        anima = _anima(sheet, current=4, glut=2)
        self.assertEqual(anima.effective_current, 6)

    def test_clean_still_forbids_current_over_maximum(self):
        from django.core.exceptions import ValidationError

        sheet = CharacterSheetFactory()
        anima = _anima(sheet)
        anima.current = 11
        with self.assertRaises(ValidationError):
            anima.save()


class HungerSeverityTest(TestCase):
    def test_mapping(self):
        sheet = CharacterSheetFactory()
        anima = _anima(sheet, current=10, maximum=10)
        self.assertEqual(hunger_severity(anima), 0)
        anima.current = 2  # threshold is 25% of 10 = 2
        self.assertEqual(hunger_severity(anima), 1)
        anima.current = 0
        self.assertEqual(hunger_severity(anima), 5)

    def test_glut_never_quiets_ravenous(self):
        sheet = CharacterSheetFactory()
        anima = _anima(sheet, current=0, maximum=10, glut=8)
        self.assertEqual(hunger_severity(anima), 5)


class ReconcileRavenousTest(TestCase):
    def setUp(self):
        ensure_ravenous_condition()
        self.blood, _essence = ensure_appetite_distinctions()

    def test_hungry_holder_gets_ravenous(self):
        sheet = CharacterSheetFactory()
        CharacterDistinction.objects.create(character=sheet, distinction=self.blood)
        _anima(sheet, current=0)
        with patch("world.conditions.services.apply_condition") as ac:
            reconcile_ravenous(sheet)
        ac.assert_called_once()
        self.assertEqual(ac.call_args.kwargs.get("severity"), 5)

    def test_non_holder_never_ravenous(self):
        sheet = CharacterSheetFactory()
        _anima(sheet, current=0)
        with patch("world.conditions.services.apply_condition") as ac:
            reconcile_ravenous(sheet)
        ac.assert_not_called()


class GlutSunResistanceTest(TestCase):
    def test_glutted_vampire_subtracts_glut_from_sun_exposure(self):
        from evennia_extensions.factories import RoomProfileFactory
        from world.game_clock.constants import TimePhase
        from world.species.sun_exposure import felt_sun_exposure

        blood, _essence = ensure_appetite_distinctions()
        sheet = CharacterSheetFactory()
        CharacterDistinction.objects.create(character=sheet, distinction=blood)
        _anima(sheet, current=10, glut=4)
        room = RoomProfileFactory(is_outdoor=True).objectdb
        with patch("world.species.sun_exposure.get_ic_phase", return_value=TimePhase.DAY):
            exposure = felt_sun_exposure(sheet.character, room)
        self.assertEqual(exposure.magic, 4)
        self.assertEqual(exposure.residual, 6)

    def test_no_appetite_no_glut_bonus(self):
        from evennia_extensions.factories import RoomProfileFactory
        from world.game_clock.constants import TimePhase
        from world.species.sun_exposure import felt_sun_exposure

        sheet = CharacterSheetFactory()
        _anima(sheet, current=10, glut=4)
        room = RoomProfileFactory(is_outdoor=True).objectdb
        with patch("world.species.sun_exposure.get_ic_phase", return_value=TimePhase.DAY):
            exposure = felt_sun_exposure(sheet.character, room)
        self.assertEqual(exposure.magic, 0)
