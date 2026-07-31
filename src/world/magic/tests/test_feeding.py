"""Feeding transfer service (#2853). SQLite tier — Ravenous reconcile patched
(apply_condition is PG-only) and death finalization patched where noted."""

from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.models.anima import CharacterAnima
from world.magic.models.appetites import FeedingRecord
from world.magic.services.feeding import FeedMode, feed_anima


def _anima(sheet, *, current=10, maximum=10, glut=0):
    anima, _ = CharacterAnima.objects.update_or_create(
        character=sheet,
        defaults={"current": current, "maximum": maximum, "glut": glut},
    )
    return anima


def _quiet_reconcile():
    return patch("world.magic.services.feeding._reconcile_both")


class FeedAnimaTest(TestCase):
    def setUp(self):
        self.feeder = CharacterSheetFactory()
        self.victim = CharacterSheetFactory()

    def test_sip_is_nonfatal_by_construction(self):
        _anima(self.feeder, current=5)
        _anima(self.victim, current=3, maximum=3)
        with _quiet_reconcile():
            outcome = feed_anima(self.feeder, self.victim, amount_mode=FeedMode.SIP)
        self.assertEqual(outcome.taken, 1)
        self.assertEqual(CharacterAnima.objects.get(character=self.victim).current, 2)
        self.assertFalse(outcome.was_lethal)

    def test_sip_takes_nothing_at_the_reserve(self):
        _anima(self.feeder, current=5)
        _anima(self.victim, current=1, maximum=3)
        with _quiet_reconcile():
            outcome = feed_anima(self.feeder, self.victim, amount_mode=FeedMode.SIP)
        self.assertEqual(outcome.taken, 0)
        self.assertEqual(CharacterAnima.objects.get(character=self.victim).current, 1)

    def test_gorge_overfill_lands_in_glut(self):
        _anima(self.feeder, current=9, maximum=10)
        _anima(self.victim, current=5, maximum=5)
        with (
            _quiet_reconcile(),
            patch("world.magic.services.feeding._maybe_kill_npc_victim", return_value=False),
        ):
            outcome = feed_anima(self.feeder, self.victim, amount_mode=FeedMode.GORGE)
        feeder_anima = CharacterAnima.objects.get(character=self.feeder)
        self.assertEqual(outcome.taken, 5)
        self.assertEqual(feeder_anima.current, 10)
        self.assertEqual(feeder_anima.glut, 4)
        self.assertEqual(outcome.glut_gained, 4)

    def test_victim_fatigue_rides_the_cast_ratio(self):
        from world.fatigue.services import get_or_create_fatigue_pool

        _anima(self.feeder, current=0)
        _anima(self.victim, current=5, maximum=5)
        with (
            _quiet_reconcile(),
            patch("world.magic.services.feeding._restraint_holds", return_value=True),
        ):
            outcome = feed_anima(self.feeder, self.victim, amount_mode=FeedMode.DRINK)
        self.assertEqual(outcome.taken, 3)
        # (3 anima * 25%) // 100 -> 0; ratios floor small takes to 0 fatigue.
        pool = get_or_create_fatigue_pool(self.victim)
        self.assertEqual(pool.get_current("physical"), outcome.victim_fatigue)

    def test_ravenous_feeder_can_lose_control(self):
        _anima(self.feeder, current=0)  # empty = ravenous
        _anima(self.victim, current=4, maximum=4)
        with (
            _quiet_reconcile(),
            patch("world.magic.services.feeding._restraint_holds", return_value=False),
            patch("world.magic.services.feeding._maybe_kill_npc_victim", return_value=False),
        ):
            outcome = feed_anima(self.feeder, self.victim, amount_mode=FeedMode.SIP)
        self.assertTrue(outcome.lost_control)
        self.assertEqual(outcome.taken, 4)
        record = FeedingRecord.objects.get()
        self.assertEqual(record.amount_mode, FeedMode.GORGE)
        self.assertTrue(record.lost_control)

    def test_gorge_past_empty_kills_npc_and_mints_deed(self):
        _anima(self.feeder, current=10)
        _anima(self.victim, current=2, maximum=2)
        with (
            _quiet_reconcile(),
            patch(
                "world.stories.npc_protection.is_death_prevented_by_story",
                return_value=False,
            ),
            patch("world.vitals.services.mark_fed_to_death", return_value=True) as kill,
            patch("world.magic.services.feeding._mint_feeding_kill_deed") as deed,
        ):
            outcome = feed_anima(self.feeder, self.victim, amount_mode=FeedMode.GORGE)
        self.assertTrue(outcome.was_lethal)
        kill.assert_called_once_with(self.victim)
        deed.assert_called_once()
        self.assertTrue(FeedingRecord.objects.get().was_lethal)

    def test_story_protected_npc_survives_the_gorge(self):
        _anima(self.feeder, current=10)
        _anima(self.victim, current=2, maximum=2)
        with (
            _quiet_reconcile(),
            patch(
                "world.stories.npc_protection.is_death_prevented_by_story",
                return_value=True,
            ),
            patch("world.vitals.services.mark_fed_to_death") as kill,
        ):
            outcome = feed_anima(self.feeder, self.victim, amount_mode=FeedMode.GORGE)
        self.assertFalse(outcome.was_lethal)
        kill.assert_not_called()

    def test_pc_victim_never_dies_of_feeding(self):
        _anima(self.feeder, current=10)
        _anima(self.victim, current=2, maximum=2)
        with (
            _quiet_reconcile(),
            patch("world.magic.services.feeding._victim_is_npc", return_value=False),
            patch("world.vitals.services.mark_fed_to_death") as kill,
        ):
            outcome = feed_anima(self.feeder, self.victim, amount_mode=FeedMode.GORGE)
        self.assertFalse(outcome.was_lethal)
        kill.assert_not_called()


class MarkFedToDeathGuardTest(TestCase):
    def test_refuses_pc_victims(self):
        from world.vitals.services import mark_fed_to_death

        sheet = CharacterSheetFactory()
        with patch.object(type(sheet.character), "db_account", new=object(), create=True):
            self.assertFalse(mark_fed_to_death(sheet))

    def test_kills_sheeted_npc_via_death_finalization(self):
        from world.vitals.models import CharacterVitals
        from world.vitals.services import mark_fed_to_death

        sheet = CharacterSheetFactory()
        with patch("world.vitals.services._mark_dead") as finalize:
            self.assertTrue(mark_fed_to_death(sheet))
        finalize.assert_called_once_with(sheet)
        vitals = CharacterVitals.objects.get(character_sheet=sheet)
        self.assertEqual(vitals.health, 0)
