"""Unit tests for CombatAttackResolver.

Each test isolates one method. Integration through use_technique is in
test_combat_magic_integration.py.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ActionCategory, OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatRoundAction
from world.combat.services import CombatAttackResolver
from world.fatigue.constants import EffortLevel, FatigueCategory
from world.magic.factories import EffectTypeFactory, GiftFactory, TechniqueFactory


def _build_resolver(*, pull_flat_bonus: int = 0, base_power: int = 20):
    """Helper to build a CombatAttackResolver with sane defaults."""
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
        focused_target=opponent,
        effort_level=EffortLevel.MEDIUM,
    )
    return CombatAttackResolver(
        participant=participant,
        action=action,
        target=opponent,
        pull_flat_bonus=pull_flat_bonus,
        fatigue_category=FatigueCategory.PHYSICAL,
        offense_check_type=MagicMock(),
        offense_check_fn=None,
    )


class CombatAttackResolverRollCheckTests(TestCase):
    def test_pull_bonus_added_to_extra_modifiers(self) -> None:
        """A pull_flat_bonus of 3 must reach perform_check via extra_modifiers."""
        resolver = _build_resolver(pull_flat_bonus=3)

        with patch("world.combat.services.perform_check") as mock_perform:
            mock_perform.return_value = MagicMock(success_level=2)
            resolver._roll_check()

        kwargs = mock_perform.call_args.kwargs
        # extra_modifiers contains pull bonus + effort modifier (MEDIUM = 0)
        self.assertGreaterEqual(kwargs["extra_modifiers"], 3)


class CombatAttackResolverScaleTests(TestCase):
    def test_full_success_returns_full_damage(self) -> None:
        resolver = _build_resolver(base_power=20)
        check = MagicMock(success_level=2)
        self.assertEqual(resolver._scale(check), 20)

    def test_partial_success_returns_half_damage(self) -> None:
        resolver = _build_resolver(base_power=20)
        check = MagicMock(success_level=1)
        self.assertEqual(resolver._scale(check), 10)

    def test_miss_returns_zero_damage(self) -> None:
        resolver = _build_resolver(base_power=20)
        check = MagicMock(success_level=0)
        self.assertEqual(resolver._scale(check), 0)


class CombatAttackResolverApplyTests(TestCase):
    def test_apply_returns_damage_results_when_target_alive(self) -> None:
        resolver = _build_resolver()
        results = resolver._apply(scaled_damage=10)
        self.assertEqual(len(results), 1)
        self.assertGreater(results[0].damage_dealt, 0)

    def test_apply_skips_defeated_target(self) -> None:
        from world.combat.constants import OpponentStatus

        resolver = _build_resolver()
        resolver.target.status = OpponentStatus.DEFEATED
        resolver.target.save(update_fields=["status"])
        results = resolver._apply(scaled_damage=10)
        self.assertEqual(results, [])

    def test_apply_returns_empty_on_zero_damage(self) -> None:
        resolver = _build_resolver()
        results = resolver._apply(scaled_damage=0)
        self.assertEqual(results, [])
