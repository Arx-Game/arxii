"""Tests for compute_effective_intensity helper."""

from evennia.utils.test_resources import EvenniaTestCase


class ComputeEffectiveIntensityTests(EvenniaTestCase):
    def test_baseline_returns_technique_intensity(self) -> None:
        from world.combat.factories import (
            CombatParticipantFactory,
            CombatRoundActionFactory,
        )
        from world.combat.services import compute_effective_intensity
        from world.magic.factories import TechniqueFactory

        tech = TechniqueFactory(intensity=4)
        participant = CombatParticipantFactory()
        action = CombatRoundActionFactory(
            participant=participant,
            focused_action=tech,
        )
        self.assertEqual(compute_effective_intensity(participant, action), 4)

    def test_aggregates_intensity_bump_pulls(self) -> None:
        from world.combat.factories import (
            CombatParticipantFactory,
            CombatPullFactory,
            CombatPullResolvedEffectFactory,
            CombatRoundActionFactory,
        )
        from world.combat.services import compute_effective_intensity
        from world.magic.constants import EffectKind
        from world.magic.factories import TechniqueFactory

        tech = TechniqueFactory(intensity=3)
        participant = CombatParticipantFactory()
        encounter = participant.encounter
        action = CombatRoundActionFactory(
            participant=participant,
            focused_action=tech,
        )
        pull = CombatPullFactory(
            participant=participant,
            encounter=encounter,
            round_number=encounter.round_number,
        )
        CombatPullResolvedEffectFactory(
            pull=pull,
            kind=EffectKind.INTENSITY_BUMP,
            scaled_value=2,
        )
        # Invalidate handler cache so it picks up the new pull
        participant.character_sheet.character.combat_pulls.invalidate()
        self.assertEqual(compute_effective_intensity(participant, action), 5)

    def test_ignores_other_pull_kinds(self) -> None:
        from world.combat.factories import (
            CombatParticipantFactory,
            CombatPullFactory,
            CombatPullResolvedEffectFactory,
            CombatRoundActionFactory,
        )
        from world.combat.services import compute_effective_intensity
        from world.magic.constants import EffectKind
        from world.magic.factories import TechniqueFactory

        tech = TechniqueFactory(intensity=3)
        participant = CombatParticipantFactory()
        encounter = participant.encounter
        action = CombatRoundActionFactory(
            participant=participant,
            focused_action=tech,
        )
        pull = CombatPullFactory(
            participant=participant,
            encounter=encounter,
            round_number=encounter.round_number,
        )
        CombatPullResolvedEffectFactory(
            pull=pull,
            kind=EffectKind.FLAT_BONUS,
            scaled_value=10,
        )
        participant.character_sheet.character.combat_pulls.invalidate()
        self.assertEqual(compute_effective_intensity(participant, action), 3)
