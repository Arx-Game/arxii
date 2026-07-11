"""TDD test for Task 2 (#2206): declared cast positions are validated against the

encounter's own battlefield room.

``resolve_cast_position_params`` must reject a ``destination_position_id`` that
belongs to a Position in a different room than the participant's encounter —
the position is simply not part of this battlefield.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from actions.errors import ActionDispatchError
from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.models import PositionEdge
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.services import declare_action, resolve_cast_position_params, resolve_round
from world.conditions.constants import OBSTACLE_CONDITION_NAME
from world.conditions.models import ConditionInstance
from world.fatigue.constants import EffortLevel
from world.magic.effect_palette_content import OBSTACLE_TECHNIQUE_NAME, ensure_obstacle_content
from world.magic.factories import CharacterAnimaFactory, TechniqueFactory
from world.magic.models.techniques import Technique
from world.mechanics.factories import CharacterEngagementFactory
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals


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

    def test_identical_pair_endpoints_rejected(self):
        """A barrier needs two different endpoints — A==B must be rejected (#2206)."""
        pos = PositionFactory(room=self.encounter.room)
        with self.assertRaises(ActionDispatchError):
            resolve_cast_position_params(
                self.participant,
                self.technique,
                {"position_a_id": pos.pk, "position_b_id": pos.pk},
            )


class BarricadeCastPositionJourneyTests(TestCase):
    """Task 3 (#2206): a declared cast position pair reaches the applied condition.

    Full journey: declare a Barricade cast with a validated position_a/position_b
    pair, resolve the round, and assert the resulting ConditionInstance carries
    the declared ``cast_position_a`` FK and that the pair's PositionEdge was
    sealed impassable — proving ``CombatTechniqueResolver._apply_conditions``
    forwards ``position_params`` to ``apply_technique_conditions``.
    """

    @classmethod
    def setUpTestData(cls):
        ensure_obstacle_content()
        cls.technique = Technique.objects.get(name=OBSTACLE_TECHNIQUE_NAME)

        cls.encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        sheet = CharacterSheetFactory()
        cls.participant = CombatParticipantFactory(encounter=cls.encounter, character_sheet=sheet)
        CharacterVitals.objects.create(character_sheet=sheet, health=100, max_health=100)
        CharacterAnimaFactory(character=sheet.character, current=20, maximum=20)
        CharacterEngagementFactory(character=sheet.character)
        sheet.character.location = cls.encounter.room
        sheet.character.save()

        cls.pos_a = PositionFactory(room=cls.encounter.room, name="north wall")
        cls.pos_b = PositionFactory(room=cls.encounter.room, name="south wall")

    def test_declared_cast_positions_reach_condition_and_seal_edge(self):
        resolved = resolve_cast_position_params(
            self.participant,
            self.technique,
            {"position_a_id": self.pos_a.pk, "position_b_id": self.pos_b.pk},
        )
        declare_action(
            self.participant,
            focused_action=self.technique,
            effort_level=EffortLevel.MEDIUM,
            cast_position_a=resolved["cast_position_a"],
            cast_position_b=resolved["cast_position_b"],
        )

        def mock_check_fn(*args, **kwargs):
            return MagicMock(success_level=2)

        resolve_round(self.encounter, offense_check_fn=mock_check_fn)

        instance = ConditionInstance.objects.get(
            condition__name=OBSTACLE_CONDITION_NAME,
            target=self.participant.character_sheet.character,
        )
        self.assertEqual(instance.cast_position_a_id, self.pos_a.pk)

        edge = PositionEdge.objects.get(position_a=self.pos_a, position_b=self.pos_b)
        self.assertFalse(edge.is_passable)
