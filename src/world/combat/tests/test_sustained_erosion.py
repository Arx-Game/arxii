"""Tests for the PC sustained-action erosion rider (#2705).

Covers ``_apply_sustained_erosion_rider`` directly — the PC-side sibling of
``_apply_windup_interception_rider`` (see ``WindupInterceptionRiderTests`` in
``test_windup_lifecycle.py``, whose structure this mirrors) — plus one
integration test proving ``apply_damage_to_participant`` actually calls it at
the point where the final applied damage is known.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from world.combat.constants import SUSTAINED_HIT_DOWNGRADE
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    SustainedActionFactory,
)
from world.combat.models import SustainedAction
from world.combat.services import _apply_sustained_erosion_rider, apply_damage_to_participant
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals


class SustainedErosionRiderTests(TestCase):
    """Direct tests of ``_apply_sustained_erosion_rider``."""

    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=1)
        self.participant = CombatParticipantFactory(encounter=self.encounter)

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_landing_hit_adds_one_downgrade_and_broadcasts(self, mock_broadcast) -> None:
        sustained = SustainedActionFactory(
            encounter=self.encounter,
            participant=self.participant,
            declared_round=1,
            resolves_round=2,
            downgrades=0,
        )

        _apply_sustained_erosion_rider(self.participant, 10)

        sustained.refresh_from_db()
        self.assertEqual(sustained.downgrades, SUSTAINED_HIT_DOWNGRADE)
        self.assertTrue(mock_broadcast.called)

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_zero_damage_hit_does_not_downgrade_or_broadcast(self, mock_broadcast) -> None:
        sustained = SustainedActionFactory(
            encounter=self.encounter,
            participant=self.participant,
            declared_round=1,
            resolves_round=2,
            downgrades=0,
        )

        _apply_sustained_erosion_rider(self.participant, 0)

        sustained.refresh_from_db()
        self.assertEqual(sustained.downgrades, 0)
        self.assertFalse(mock_broadcast.called)

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_no_sustained_action_is_a_clean_noop(self, mock_broadcast) -> None:
        self.assertFalse(SustainedAction.objects.filter(participant=self.participant).exists())

        # Must not raise and must not broadcast.
        _apply_sustained_erosion_rider(self.participant, 10)

        self.assertFalse(mock_broadcast.called)

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_two_hits_in_a_round_add_two_downgrades(self, mock_broadcast) -> None:  # noqa: ARG002
        sustained = SustainedActionFactory(
            encounter=self.encounter,
            participant=self.participant,
            declared_round=1,
            resolves_round=2,
            downgrades=0,
        )

        _apply_sustained_erosion_rider(self.participant, 10)
        _apply_sustained_erosion_rider(self.participant, 5)

        sustained.refresh_from_db()
        self.assertEqual(sustained.downgrades, 2 * SUSTAINED_HIT_DOWNGRADE)

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_hit_on_already_matured_row_is_a_noop(self, mock_broadcast) -> None:
        """A row whose resolves_round is strictly before the current round has
        already matured (and would normally be deleted by maturation) — the
        ``resolves_round__gte`` guard mirrors the windup rider's."""
        self.encounter.round_number = 5
        self.encounter.save(update_fields=["round_number"])
        sustained = SustainedActionFactory(
            encounter=self.encounter,
            participant=self.participant,
            declared_round=1,
            resolves_round=2,
            downgrades=0,
        )

        _apply_sustained_erosion_rider(self.participant, 10)

        sustained.refresh_from_db()
        self.assertEqual(sustained.downgrades, 0)
        self.assertFalse(mock_broadcast.called)


class SustainedErosionWiringTests(TestCase):
    """Integration: ``apply_damage_to_participant`` calls the rider with the
    FINAL applied damage, after reductions/interceptors have run (#2705)."""

    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=1)
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        self.vitals, _ = CharacterVitals.objects.get_or_create(
            character_sheet=self.participant.character_sheet,
            defaults={"health": 100, "max_health": 100},
        )
        self.vitals.health = 100
        self.vitals.max_health = 100
        self.vitals.save()

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_landing_damage_erodes_the_sustained_action(
        self,
        mock_broadcast,  # noqa: ARG002
    ) -> None:
        sustained = SustainedActionFactory(
            encounter=self.encounter,
            participant=self.participant,
            declared_round=1,
            resolves_round=2,
            downgrades=0,
        )

        result = apply_damage_to_participant(self.participant, 30)

        sustained.refresh_from_db()
        self.assertEqual(result.damage_dealt, 30)
        self.assertEqual(sustained.downgrades, SUSTAINED_HIT_DOWNGRADE)

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_no_sustained_action_leaves_damage_path_unchanged(
        self,
        mock_broadcast,  # noqa: ARG002
    ) -> None:
        result = apply_damage_to_participant(self.participant, 30)

        self.vitals.refresh_from_db()
        self.assertEqual(result.damage_dealt, 30)
        self.assertEqual(self.vitals.health, 70)
