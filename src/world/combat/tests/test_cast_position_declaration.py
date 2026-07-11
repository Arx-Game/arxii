"""TDD test for Task 2 (#2206): declared cast positions are validated against the

encounter's own battlefield room.

``resolve_cast_position_params`` must reject a ``destination_position_id`` that
belongs to a Position in a different room than the participant's encounter —
the position is simply not part of this battlefield.
"""

from __future__ import annotations

from django.test import TestCase

from actions.errors import ActionDispatchError
from world.areas.positioning.factories import PositionFactory
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.services import resolve_cast_position_params
from world.magic.factories import TechniqueFactory


class ResolveCastPositionParamsTests(TestCase):
    """resolve_cast_position_params rejects positions outside the encounter's room."""

    @classmethod
    def setUpTestData(cls):
        cls.encounter = CombatEncounterFactory()
        cls.participant = CombatParticipantFactory(encounter=cls.encounter)
        cls.technique = TechniqueFactory()
        # PositionFactory creates a fresh Room by default — this position lives
        # in a different room than the encounter's own battlefield room.
        cls.other_room_position = PositionFactory()

    def test_foreign_room_position_rejected(self):
        with self.assertRaises(ActionDispatchError):
            resolve_cast_position_params(
                self.participant,
                self.technique,
                {"destination_position_id": self.other_room_position.pk},
            )
