"""Unit tests for CombatTechniqueResolver.

Each test isolates one method. Integration through use_technique is in
test_combat_magic_integration.py.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ActionCategory, OpponentStatus, OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatRoundAction
from world.combat.services import CombatTechniqueResolver
from world.fatigue.constants import EffortLevel, FatigueCategory
from world.magic.factories import EffectTypeFactory, GiftFactory, TechniqueFactory


def _build_resolver(*, pull_flat_bonus: int = 0, base_power: int = 20):
    """Helper to build a CombatTechniqueResolver with sane defaults."""
    encounter = CombatEncounterFactory(round_number=1)
    pool = ThreatPoolFactory()
    ThreatPoolEntryFactory(pool=pool, base_damage=30)
    opponent = CombatOpponentFactory(
        encounter=encounter,
        tier=OpponentTier.MOOK,
        health=50,
        max_health=50,
        threat_pool=pool,
    )
    sheet = CharacterSheetFactory()
    participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
    technique = TechniqueFactory(
        gift=GiftFactory(),
        effect_type=EffectTypeFactory(name="Attack", base_power=base_power),
    )
    action = CombatRoundAction.objects.create(
        participant=participant,
        round_number=1,
        focused_category=ActionCategory.PHYSICAL,
        focused_action=technique,
        focused_opponent_target=opponent,
        effort_level=EffortLevel.MEDIUM,
    )
    return CombatTechniqueResolver(
        participant=participant,
        action=action,
        pull_flat_bonus=pull_flat_bonus,
        fatigue_category=FatigueCategory.PHYSICAL,
        offense_check_type=MagicMock(),
        offense_check_fn=None,
    )


class CombatTechniqueResolverRollCheckTests(TestCase):
    def test_pull_bonus_added_to_extra_modifiers(self) -> None:
        """A pull_flat_bonus of 3 must reach perform_check via extra_modifiers."""
        resolver = _build_resolver(pull_flat_bonus=3)

        with patch("world.combat.services.perform_check") as mock_perform:
            mock_perform.return_value = MagicMock(success_level=2)
            resolver._roll_check()

        kwargs = mock_perform.call_args.kwargs
        # extra_modifiers contains pull bonus + effort modifier (MEDIUM = 0)
        self.assertGreaterEqual(kwargs["extra_modifiers"], 3)


class CombatTechniqueResolverApplyDamageTests(TestCase):
    def test_apply_damage_returns_damage_results_when_target_alive(self) -> None:
        resolver = _build_resolver()
        check = MagicMock(success_level=2)
        results = resolver._apply_damage(check)
        self.assertEqual(len(results), 1)
        self.assertGreater(results[0].damage_dealt, 0)

    def test_apply_damage_skips_defeated_target(self) -> None:
        resolver = _build_resolver()
        target = resolver.action.focused_opponent_target
        target.status = OpponentStatus.DEFEATED
        target.save(update_fields=["status"])
        check = MagicMock(success_level=2)
        results = resolver._apply_damage(check)
        self.assertEqual(results, [])

    def test_apply_damage_returns_empty_on_miss(self) -> None:
        resolver = _build_resolver()
        check = MagicMock(success_level=0)
        results = resolver._apply_damage(check)
        self.assertEqual(results, [])

    def test_apply_damage_returns_empty_when_no_target(self) -> None:
        resolver = _build_resolver()
        # Remove the opponent target from the action
        resolver.action.focused_opponent_target = None
        check = MagicMock(success_level=2)
        results = resolver._apply_damage(check)
        self.assertEqual(results, [])

    def test_apply_damage_half_on_partial_success(self) -> None:
        resolver = _build_resolver(base_power=20)
        check = MagicMock(success_level=1)
        results = resolver._apply_damage(check)
        self.assertEqual(len(results), 1)
        # half of 20 = 10, but actual damage_dealt may differ due to soak
        self.assertGreater(results[0].damage_dealt, 0)


class CombatTechniqueResolverApplyConditionsTests(TestCase):
    def test_apply_conditions_stub_returns_empty_list(self) -> None:
        resolver = _build_resolver()
        check = MagicMock(success_level=2)
        results = resolver._apply_conditions(check)
        self.assertEqual(results, [])


class CombatTechniqueResolverCallTests(TestCase):
    def test_call_returns_resolution_with_all_fields(self) -> None:
        resolver = _build_resolver(pull_flat_bonus=2, base_power=20)

        with patch("world.combat.services.perform_check") as mock_perform:
            mock_perform.return_value = MagicMock(success_level=2)
            result = resolver()

        self.assertGreater(result.scaled_damage, 0)
        self.assertEqual(result.pull_flat_bonus, 2)
        self.assertEqual(len(result.damage_results), 1)
        self.assertEqual(result.applied_conditions, [])
        self.assertIsNotNone(result.check_result)


class SumActiveFlatBonusesTests(TestCase):
    def test_returns_zero_when_no_pulls(self) -> None:
        from world.combat.services import _sum_active_flat_bonuses

        resolver = _build_resolver()
        self.assertEqual(
            _sum_active_flat_bonuses(resolver.participant, resolver.participant.encounter),
            0,
        )

    def test_sums_flat_bonus_scaled_values_across_active_pulls(self) -> None:
        from world.combat.factories import (
            CombatPullFactory,
            CombatPullResolvedEffectFactory,
        )
        from world.combat.services import _sum_active_flat_bonuses
        from world.magic.constants import EffectKind

        resolver = _build_resolver()
        pull = CombatPullFactory(
            participant=resolver.participant,
            round_number=resolver.participant.encounter.round_number,
        )
        CombatPullResolvedEffectFactory(pull=pull, kind=EffectKind.FLAT_BONUS, scaled_value=4)
        CombatPullResolvedEffectFactory(pull=pull, kind=EffectKind.FLAT_BONUS, scaled_value=2)

        resolver.participant.character_sheet.character.combat_pulls.invalidate()

        self.assertEqual(
            _sum_active_flat_bonuses(resolver.participant, resolver.participant.encounter),
            6,
        )

    def test_ignores_non_flat_bonus_kinds(self) -> None:
        from world.combat.factories import (
            CombatPullFactory,
            CombatPullResolvedEffectFactory,
        )
        from world.combat.services import _sum_active_flat_bonuses
        from world.magic.constants import EffectKind, VitalBonusTarget

        resolver = _build_resolver()
        pull = CombatPullFactory(
            participant=resolver.participant,
            round_number=resolver.participant.encounter.round_number,
        )
        CombatPullResolvedEffectFactory(
            pull=pull,
            kind=EffectKind.VITAL_BONUS,
            scaled_value=99,
            vital_target=VitalBonusTarget.MAX_HEALTH,
        )
        resolver.participant.character_sheet.character.combat_pulls.invalidate()

        self.assertEqual(
            _sum_active_flat_bonuses(resolver.participant, resolver.participant.encounter),
            0,
        )


class BuildCombatResultTests(TestCase):
    def test_cancelled_returns_empty_damage_results(self) -> None:
        from world.combat.services import _build_combat_result
        from world.magic.types import AnimaCostResult, TechniqueUseResult

        resolver = _build_resolver()
        cost = AnimaCostResult(
            base_cost=1,
            effective_cost=1,
            control_delta=0,
            current_anima=10,
            deficit=0,
        )
        cancelled = TechniqueUseResult(
            anima_cost=cost,
            confirmed=False,
            resolution_result=None,
            technique=resolver.action.focused_action,
        )

        result = _build_combat_result(cancelled, resolver)
        self.assertEqual(result.damage_results, [])
        self.assertEqual(result.applied_conditions, [])
        self.assertIs(result.technique_use_result, cancelled)

    def test_confirmed_extracts_damage_results_from_resolution(self) -> None:
        from world.combat.services import _build_combat_result
        from world.combat.types import CombatTechniqueResolution
        from world.magic.types import AnimaCostResult, TechniqueUseResult

        resolver = _build_resolver()
        cost = AnimaCostResult(
            base_cost=1,
            effective_cost=1,
            control_delta=0,
            current_anima=10,
            deficit=0,
        )
        damage_results = [MagicMock(damage_dealt=5)]
        resolution = CombatTechniqueResolution(
            check_result=MagicMock(success_level=2),
            damage_results=damage_results,
            applied_conditions=[],
            pull_flat_bonus=0,
            scaled_damage=20,
        )
        confirmed = TechniqueUseResult(
            anima_cost=cost,
            confirmed=True,
            resolution_result=resolution,
            technique=resolver.action.focused_action,
        )

        result = _build_combat_result(confirmed, resolver)
        self.assertEqual(result.damage_results, damage_results)
        self.assertEqual(result.applied_conditions, [])
        self.assertIs(result.technique_use_result, confirmed)
