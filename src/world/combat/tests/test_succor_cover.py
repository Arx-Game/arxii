"""Tests for CombatRoundContext.get_cover_for resolving + caching Succor (#1744)."""

from django.test import TestCase

from world.combat.constants import CombatManeuver, ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.models import CombatRoundAction
from world.combat.round_context import CombatRoundContext
from world.scenes.constants import RoundStatus


class CombatGetCoverForTests(TestCase):
    def test_no_succor_declared_returns_no_cover(self) -> None:
        encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING)
        target = CombatParticipantFactory(encounter=encounter, status=ParticipantStatus.ACTIVE)
        ctx = CombatRoundContext(target)
        result = ctx.get_cover_for(target.character_sheet, damage_type=None)
        self.assertEqual(result, 1.0)

    def test_succor_resolution_is_cached_across_calls(self) -> None:
        encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING)
        succorer = CombatParticipantFactory(encounter=encounter, status=ParticipantStatus.ACTIVE)
        target = CombatParticipantFactory(encounter=encounter, status=ParticipantStatus.ACTIVE)
        # Declared while DECLARING in a real flow; test writes the row directly at RESOLVING
        # since declare_succor requires DECLARING status — mirrors how interpose tests
        # construct their fixture.
        action = CombatRoundAction.objects.create(
            participant=succorer,
            round_number=encounter.round_number,
            maneuver=CombatManeuver.SUCCOR,
            focused_ally_target=target,
            is_ready=True,
        )
        ctx = CombatRoundContext(target)
        first = ctx.get_cover_for(target.character_sheet, damage_type=None)

        # The multiplier must now be cached on the CombatRoundAction row (#1744) —
        # this is what actually distinguishes the override from the base's
        # unconditional 1.0 default (a bare equality check on two calls would
        # pass trivially even without a real cache).
        action.refresh_from_db()
        self.assertIsNotNone(action.succor_resolution)
        self.assertEqual(action.succor_resolution, first)

        second = ctx.get_cover_for(target.character_sheet, damage_type=None)
        self.assertEqual(first, second)
