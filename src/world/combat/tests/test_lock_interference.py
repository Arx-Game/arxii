"""Tests for the duel-interference beat firing from the damage seam (#3447).

``trigger_interference_drama`` (#2020) had zero callers until #3447 wired it into
``apply_damage_to_opponent`` via ``_maybe_trigger_lock_interference``: a non-locked
PC landing damage on a locked opponent fires the beat for the locked duelist,
at most once per (duelist, interloper) per encounter once a surge record exists.
"""

from unittest.mock import patch

from django.test import TestCase

from world.combat.constants import SurgeTriggerKind
from world.combat.engagement_locks import create_engagement_lock
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import DramaticSurgeRecord
from world.combat.services import apply_damage_to_opponent


class LockInterferenceTests(TestCase):
    """The interference beat fires for interlopers, once, and never for the duelist."""

    def setUp(self) -> None:
        self.enc = CombatEncounterFactory()
        self.opp = CombatOpponentFactory(
            encounter=self.enc, health=100, max_health=100, soak_value=0
        )
        self.duelist = CombatParticipantFactory(encounter=self.enc)
        self.interloper = CombatParticipantFactory(encounter=self.enc)
        self.lock = create_engagement_lock(self.enc, self.opp, self.duelist)

    def test_interloper_hit_fires_the_beat(self) -> None:
        with patch("world.combat.engagement_locks.trigger_interference_drama") as fired:
            apply_damage_to_opponent(self.opp, 50, source_sheet=self.interloper.character_sheet)
        fired.assert_called_once()
        called_lock, called_interloper = fired.call_args.args
        self.assertEqual(called_lock.pk, self.lock.pk)
        self.assertEqual(called_interloper.pk, self.interloper.pk)

    def test_locked_duelists_own_hit_does_not_fire(self) -> None:
        with patch("world.combat.engagement_locks.trigger_interference_drama") as fired:
            apply_damage_to_opponent(self.opp, 50, source_sheet=self.duelist.character_sheet)
        fired.assert_not_called()

    def test_fully_soaked_hit_does_not_fire(self) -> None:
        self.opp.soak_value = 100
        self.opp.save(update_fields=["soak_value"])
        with patch("world.combat.engagement_locks.trigger_interference_drama") as fired:
            apply_damage_to_opponent(self.opp, 10, source_sheet=self.interloper.character_sheet)
        fired.assert_not_called()

    def test_surge_record_dedupes_the_whole_beat(self) -> None:
        DramaticSurgeRecord.objects.create(
            encounter=self.enc,
            participant=self.duelist,
            trigger_kind=SurgeTriggerKind.INTERFERENCE,
            subject_sheet=self.interloper.character_sheet,
            amount=5,
            round_number=1,
        )
        with patch("world.combat.engagement_locks.trigger_interference_drama") as fired:
            apply_damage_to_opponent(self.opp, 50, source_sheet=self.interloper.character_sheet)
        fired.assert_not_called()

    def test_unlocked_opponent_does_not_fire(self) -> None:
        other_opp = CombatOpponentFactory(
            encounter=self.enc, health=100, max_health=100, soak_value=0
        )
        with patch("world.combat.engagement_locks.trigger_interference_drama") as fired:
            apply_damage_to_opponent(other_opp, 50, source_sheet=self.interloper.character_sheet)
        fired.assert_not_called()
