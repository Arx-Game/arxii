"""A hold that runs out with nobody acting (#4091, task 10).

The one-minute ``lapsed_allegiance_sweep`` is the only remover of an
allegiance-bearing ``ConditionInstance`` once it expires -- no roll, no
consequence pool, and no encounter ever opens as a result (Decision 21: a
lapse never starts a fight). The hourly ``batch_condition_expiration_cleanup``
skips these rows so the sweep is the one that fires the removal event.
"""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.factories import CombatEncounterFactory
from world.combat.models import CombatEncounter
from world.conditions.constants import Allegiance, DurationType
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.game_clock.tasks import batch_condition_expiration_cleanup
from world.npc_services.allegiance_outcomes import lapsed_allegiance_sweep

_ROOM_TYPECLASS = "typeclasses.rooms.Room"


class LapseSweepTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from evennia import create_object

        break_check = CheckTypeFactory(name="Lapse Break 4091")
        cls.timed_charm = ConditionTemplateFactory(
            name="Timed Charm 4091",
            default_duration_type=DurationType.INGAME_TIME,
            is_visible_to_others=True,
            sets_allegiance=Allegiance.ALLY_OF_CASTER,
            allegiance_break_check_type=break_check,
        )
        cls.rounds_charm = ConditionTemplateFactory(
            name="Rounds Charm 4091",
            default_duration_type=DurationType.ROUNDS,
            sets_allegiance=Allegiance.ALLY_OF_CASTER,
            allegiance_break_check_type=break_check,
        )
        cls.room = create_object(_ROOM_TYPECLASS, key="Lapse Sweep Room 4091", nohome=True)
        cls.npc_sheet = CharacterSheetFactory(
            character__db_key="Sow Doubt Target 4091", character__location=cls.room
        )
        cls.npc_char = cls.npc_sheet.character
        cls.pc_sheet = CharacterSheetFactory(
            character__db_key="Lapse Witness 4091", character__location=cls.room
        )
        cls.pc_char = cls.pc_sheet.character

    def test_expired_charm_is_removed_with_no_roll(self) -> None:
        instance = ConditionInstanceFactory(
            target=self.npc_char,
            condition=self.timed_charm,
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        with mock.patch("world.checks.services.perform_check") as roll:
            lapsed_allegiance_sweep()
        roll.assert_not_called()
        self.assertFalse(ConditionInstance.objects.filter(pk=instance.pk).exists())

    def test_no_encounter_opens_whoever_started_the_old_fight(self) -> None:
        for initiated_by_pc_side in (True, False):
            CombatEncounterFactory(initiated_by_pc_side=initiated_by_pc_side)
            ConditionInstanceFactory(
                target=self.npc_char,
                condition=self.timed_charm,
                expires_at=timezone.now() - timedelta(minutes=1),
            )
            before = CombatEncounter.objects.count()
            lapsed_allegiance_sweep()
            self.assertEqual(CombatEncounter.objects.count(), before)

    def test_fade_line_reaches_the_room(self) -> None:
        ConditionInstanceFactory(
            target=self.npc_char,
            condition=self.timed_charm,
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        with mock.patch("world.scenes.narrator.narrate_room_outcome") as narrate:
            lapsed_allegiance_sweep()
        narrate.assert_called_once()
        room_arg, text_arg = narrate.call_args.args
        self.assertEqual(room_arg, self.room)
        self.assertIn(self.timed_charm.name, text_arg)
        self.assertIn("has run out", text_arg)

    def test_rounds_charm_after_the_fight_does_not_tick(self) -> None:
        # Decision 14 interim: a ROUNDS-based hold has no expires_at, so the
        # real-time sweep's filter never matches it -- this is the identity-
        # mapped instance the sweep never touches, so no refresh_from_db.
        instance = ConditionInstanceFactory(
            target=self.npc_char,
            condition=self.rounds_charm,
            rounds_remaining=3,
        )
        lapsed_allegiance_sweep()
        self.assertEqual(instance.rounds_remaining, 3)

    def test_vanished_target_is_skipped_safely(self) -> None:
        vanished = ObjectDBFactory(db_key="Vanished Target 4091")
        self.assertIsNone(vanished.location)
        instance = ConditionInstanceFactory(
            target=vanished,
            condition=self.timed_charm,
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        with mock.patch("world.scenes.narrator.narrate_room_outcome") as narrate:
            lapsed_allegiance_sweep()
        narrate.assert_not_called()
        self.assertFalse(ConditionInstance.objects.filter(pk=instance.pk).exists())

    def test_closed_bind_windows_are_released(self) -> None:
        with mock.patch("world.combat.won_over.release_closed_bind_windows") as release:
            lapsed_allegiance_sweep()
        release.assert_called_once()

    def test_hourly_cleanup_leaves_allegiance_rows_for_the_sweep(self) -> None:
        instance = ConditionInstanceFactory(
            target=self.npc_char,
            condition=self.timed_charm,
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        batch_condition_expiration_cleanup()
        self.assertTrue(ConditionInstance.objects.filter(pk=instance.pk).exists())
