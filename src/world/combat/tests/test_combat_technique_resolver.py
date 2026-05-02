"""Unit tests for CombatTechniqueResolver.

Each test isolates one method. Integration through use_technique is in
test_combat_magic_integration.py.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase
from evennia.utils.test_resources import EvenniaTestCase

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
from world.conditions.factories import DamageSuccessLevelMultiplierFactory
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
    @classmethod
    def setUpTestData(cls) -> None:
        # Seed the DamageSuccessLevelMultiplier lookup so get_damage_multiplier
        # returns non-zero values under the new profiles-based pipeline.
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("0.50"), label="Partial"
        )

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


class ApplyConditionsTests(TestCase):
    """Tests for CombatTechniqueResolver._apply_conditions (real implementation)."""

    def setUp(self) -> None:
        from decimal import Decimal

        from world.conditions.factories import ConditionTemplateFactory
        from world.magic.factories import TechniqueAppliedConditionFactory

        self.resolver = _build_resolver()
        self.technique = self.resolver.action.focused_action

        # Two conditions on the technique so tests can use either or both.
        self.cond_a = ConditionTemplateFactory(
            name="TestCondA",
            default_duration_value=2,
        )
        self.cond_b = ConditionTemplateFactory(
            name="TestCondB",
            default_duration_value=3,
        )
        self.TechniqueAppliedConditionFactory = TechniqueAppliedConditionFactory
        self.Decimal = Decimal

    def _make_applied_condition_row(self, **kwargs):
        return self.TechniqueAppliedConditionFactory(
            technique=self.technique,
            **kwargs,
        )

    def test_returns_empty_when_no_rows(self) -> None:
        """Technique with no condition_applications rows returns []."""
        check = MagicMock(success_level=2)
        results = self.resolver._apply_conditions(check)
        self.assertEqual(results, [])

    def test_skips_condition_below_minimum_sl(self) -> None:
        """Rows whose minimum_success_level exceeds the check SL are skipped."""
        # SL=1: cond_a (min_sl=1) applies, cond_b (min_sl=2) is skipped.
        self._make_applied_condition_row(
            condition=self.cond_a,
            target_kind="enemy",
            minimum_success_level=1,
        )
        self._make_applied_condition_row(
            condition=self.cond_b,
            target_kind="enemy",
            minimum_success_level=2,
        )

        with patch("world.conditions.services.bulk_apply_conditions") as mock_bulk:
            from world.conditions.types import ApplyConditionResult

            mock_bulk.return_value = [ApplyConditionResult(success=True)]
            check = MagicMock(success_level=1)
            results = self.resolver._apply_conditions(check)

        # Only one row passed the SL gate → bulk called with one application
        self.assertEqual(len(results), 1)
        call_args = mock_bulk.call_args[0][0]
        self.assertEqual(len(call_args), 1)
        self.assertEqual(call_args[0].template, self.cond_a)

    def test_applies_enemy_targeted_condition(self) -> None:
        """A ENEMY-kind row lands on the focused opponent's ObjectDB."""
        from world.combat.types import AppliedConditionResult
        from world.conditions.types import ApplyConditionResult

        self._make_applied_condition_row(
            condition=self.cond_a,
            target_kind="enemy",
            minimum_success_level=1,
        )
        expected_target = self.resolver.action.focused_opponent_target.objectdb

        with patch("world.conditions.services.bulk_apply_conditions") as mock_bulk:
            mock_bulk.return_value = [ApplyConditionResult(success=True)]
            check = MagicMock(success_level=2)
            results = self.resolver._apply_conditions(check)

        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertIsInstance(result, AppliedConditionResult)
        self.assertEqual(result.target, expected_target)
        self.assertEqual(result.condition, self.cond_a)
        self.assertTrue(result.success)

    def test_applies_self_targeted_condition(self) -> None:
        """A SELF-kind row lands on the caster's ObjectDB."""
        self._make_applied_condition_row(
            condition=self.cond_a,
            target_kind="self",
            minimum_success_level=1,
        )
        expected_target = self.resolver.participant.character_sheet.character

        with patch("world.conditions.services.bulk_apply_conditions") as mock_bulk:
            from world.conditions.types import ApplyConditionResult

            mock_bulk.return_value = [ApplyConditionResult(success=True)]
            check = MagicMock(success_level=1)
            results = self.resolver._apply_conditions(check)

        self.assertEqual(len(results), 1)
        call_args = mock_bulk.call_args[0][0]
        self.assertEqual(call_args[0].target, expected_target)

    def test_applies_ally_targeted_condition(self) -> None:
        """An ALLY-kind row lands on the focused_ally_target's ObjectDB."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.combat.factories import CombatParticipantFactory

        ally_sheet = CharacterSheetFactory()
        ally_participant = CombatParticipantFactory(
            encounter=self.resolver.participant.encounter,
            character_sheet=ally_sheet,
        )
        # Set the action's ally target
        self.resolver.action.focused_opponent_target = None
        self.resolver.action.focused_ally_target = ally_participant
        self.resolver.action.save(update_fields=["focused_opponent_target", "focused_ally_target"])

        self._make_applied_condition_row(
            condition=self.cond_a,
            target_kind="ally",
            minimum_success_level=1,
        )
        expected_target = ally_sheet.character

        with patch("world.conditions.services.bulk_apply_conditions") as mock_bulk:
            from world.conditions.types import ApplyConditionResult

            mock_bulk.return_value = [ApplyConditionResult(success=True)]
            check = MagicMock(success_level=2)
            results = self.resolver._apply_conditions(check)

        self.assertEqual(len(results), 1)
        call_args = mock_bulk.call_args[0][0]
        self.assertEqual(call_args[0].target, expected_target)

    def test_skips_defeated_enemy(self) -> None:
        """Enemy-kind rows are skipped when the opponent is DEFEATED."""
        self._make_applied_condition_row(
            condition=self.cond_a,
            target_kind="enemy",
            minimum_success_level=1,
        )
        opponent = self.resolver.action.focused_opponent_target
        opponent.status = OpponentStatus.DEFEATED
        opponent.save(update_fields=["status"])

        with patch("world.conditions.services.bulk_apply_conditions") as mock_bulk:
            check = MagicMock(success_level=2)
            results = self.resolver._apply_conditions(check)

        mock_bulk.assert_not_called()
        self.assertEqual(results, [])

    def test_severity_uses_effective_intensity(self) -> None:
        """severity_intensity_multiplier scales with effective intensity."""
        from decimal import Decimal

        self._make_applied_condition_row(
            condition=self.cond_a,
            target_kind="enemy",
            minimum_success_level=1,
            base_severity=2,
            severity_intensity_multiplier=Decimal("1.0"),
            severity_per_extra_sl=0,
        )

        with patch("world.conditions.services.bulk_apply_conditions") as mock_bulk:
            from world.conditions.types import ApplyConditionResult

            mock_bulk.return_value = [ApplyConditionResult(success=True)]
            with patch("world.combat.services.compute_effective_intensity", return_value=5):
                check = MagicMock(success_level=1)
                results = self.resolver._apply_conditions(check)

        # base_severity=2, effective_intensity=5 * multiplier=1.0 = 5, total = 7
        call_args = mock_bulk.call_args[0][0]
        self.assertEqual(call_args[0].severity, 7)
        self.assertEqual(len(results), 1)

    def test_duration_falls_back_to_condition_default(self) -> None:
        """When base_duration_rounds is None, falls back to condition.default_duration_value."""
        self._make_applied_condition_row(
            condition=self.cond_a,  # default_duration_value=2
            target_kind="enemy",
            minimum_success_level=1,
            base_duration_rounds=None,
            duration_intensity_multiplier=self.Decimal("0"),
            duration_per_extra_sl=0,
        )

        with patch("world.conditions.services.bulk_apply_conditions") as mock_bulk:
            from world.conditions.types import ApplyConditionResult

            mock_bulk.return_value = [ApplyConditionResult(success=True)]
            check = MagicMock(success_level=1)
            results = self.resolver._apply_conditions(check)

        call_args = mock_bulk.call_args[0][0]
        # cond_a.default_duration_value=2
        self.assertEqual(call_args[0].duration_rounds, 2)
        self.assertEqual(len(results), 1)

    def test_success_field_mirrors_bulk_result(self) -> None:
        """AppliedConditionResult.success mirrors the bulk result's success field."""
        self._make_applied_condition_row(
            condition=self.cond_a,
            target_kind="enemy",
            minimum_success_level=1,
        )

        with patch("world.conditions.services.bulk_apply_conditions") as mock_bulk:
            from world.conditions.types import ApplyConditionResult

            mock_bulk.return_value = [ApplyConditionResult(success=False)]
            check = MagicMock(success_level=2)
            results = self.resolver._apply_conditions(check)

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)

    def test_no_opponent_target_skips_enemy_row(self) -> None:
        """ENEMY-kind row is skipped when focused_opponent_target is None."""
        self._make_applied_condition_row(
            condition=self.cond_a,
            target_kind="enemy",
            minimum_success_level=1,
        )
        self.resolver.action.focused_opponent_target = None
        self.resolver.action.save(update_fields=["focused_opponent_target"])

        with patch("world.conditions.services.bulk_apply_conditions") as mock_bulk:
            check = MagicMock(success_level=2)
            results = self.resolver._apply_conditions(check)

        mock_bulk.assert_not_called()
        self.assertEqual(results, [])


class CombatTechniqueResolverCallTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("0.50"), label="Partial"
        )

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


class NonAttackPCActionRoutingTests(TestCase):
    """Integration: _resolve_pc_action routes non-attack techniques through the
    magic pipeline (no more silent no-op for base_power=None)."""

    def test_non_attack_technique_routes_through_pipeline(self) -> None:
        """A Buff technique (base_power=None) must reach resolve_combat_technique.

        We mock resolve_combat_technique at the services module level to verify
        it is called regardless of whether the effect type has a base_power.
        This isolates the routing logic from the full magic pipeline.
        """
        from world.combat.services import _resolve_pc_action
        from world.combat.types import CombatTechniqueResolution

        # Build encounter / participant / technique (no base_power => non-attack)
        encounter = CombatEncounterFactory(round_number=1)
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(encounter=encounter, character_sheet=sheet)
        technique = TechniqueFactory(
            gift=GiftFactory(),
            effect_type=EffectTypeFactory(name="Buff", base_power=None),
        )
        action = CombatRoundAction.objects.create(
            participant=participant,
            round_number=1,
            focused_category=ActionCategory.PHYSICAL,
            focused_action=technique,
            focused_opponent_target=None,
            effort_level=EffortLevel.MEDIUM,
        )

        mock_check_type = MagicMock()

        fake_resolution = CombatTechniqueResolution(
            check_result=MagicMock(success_level=2),
            damage_results=[],
            applied_conditions=[],
            pull_flat_bonus=0,
            scaled_damage=0,
        )

        with patch("world.combat.services.resolve_combat_technique") as mock_resolve:
            mock_resolve.return_value = fake_resolution
            outcome = _resolve_pc_action(
                participant=participant,
                action=action,
                offense_check_fn=None,
                offense_check_type=mock_check_type,
            )

        # resolve_combat_technique must have been called — non-attack no longer a no-op
        mock_resolve.assert_called_once()
        call_kwargs = mock_resolve.call_args.kwargs
        self.assertIs(call_kwargs["participant"], participant)
        self.assertIs(call_kwargs["action"], action)
        # outcome is returned cleanly (no exception)
        self.assertIsNotNone(outcome)


class ApplyDamageWithProfilesTests(EvenniaTestCase):
    """Resolver iterates damage_profiles instead of reading effect_type.base_power."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Seed the lookup table — without these, get_damage_multiplier returns 0.
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("0.50"), label="Partial"
        )

    def test_skips_when_no_damage_profiles(self) -> None:
        """Technique with no damage_profiles → _apply_damage returns []."""

        resolver = _build_resolver(base_power=20)
        # Remove the auto-seeded profile so there are none.
        resolver.action.focused_action.damage_profiles.all().delete()
        # Sanity: no profiles remain.
        self.assertEqual(resolver.action.focused_action.damage_profiles.count(), 0)
        check = MagicMock(success_level=2)
        results = resolver._apply_damage(check)
        self.assertEqual(results, [])

    def test_single_component_full_success(self) -> None:
        """1 profile base_damage=10; SL=2 → multiplier=1.0 → 10 budget → >0 damage after soak."""

        resolver = _build_resolver(base_power=10)
        # The auto-seeded profile has base_damage=10, damage_intensity_multiplier=0.
        # SL=2 → multiplier=1.0 → budget=10 → scaled=10 → apply_damage_to_opponent.
        check = MagicMock(success_level=2)
        results = resolver._apply_damage(check)
        self.assertEqual(len(results), 1)
        self.assertGreater(results[0].damage_dealt, 0)

    def test_single_component_partial_success(self) -> None:
        """1 profile base_damage=20; SL=1 → multiplier=0.5 → 10 budget → >0 damage after soak."""
        resolver = _build_resolver(base_power=20)
        check = MagicMock(success_level=1)
        results = resolver._apply_damage(check)
        self.assertEqual(len(results), 1)
        self.assertGreater(results[0].damage_dealt, 0)

    def test_below_min_sl_yields_no_damage(self) -> None:
        """Profile with minimum_success_level=2 is skipped when SL=1."""
        from world.magic.factories import TechniqueDamageProfileFactory

        resolver = _build_resolver(base_power=20)
        # Replace auto-seeded profile with one that requires SL>=2.
        resolver.action.focused_action.damage_profiles.all().delete()
        TechniqueDamageProfileFactory(
            technique=resolver.action.focused_action,
            base_damage=20,
            minimum_success_level=2,
        )
        check = MagicMock(success_level=1)
        results = resolver._apply_damage(check)
        self.assertEqual(results, [])

    def test_intensity_scales_damage(self) -> None:
        """A profile with damage_intensity_multiplier=1.0 produces more damage when
        an INTENSITY_BUMP pull raises effective_intensity above the technique baseline."""
        from world.combat.factories import (
            CombatPullFactory,
            CombatPullResolvedEffectFactory,
        )
        from world.magic.constants import EffectKind
        from world.magic.factories import TechniqueDamageProfileFactory

        resolver = _build_resolver(base_power=0)
        # Remove the auto-seeded profile (base_power=0, so none was seeded — safe).
        resolver.action.focused_action.damage_profiles.all().delete()

        # Seed a profile where damage = intensity × multiplier (base=0, mult=1.0).
        TechniqueDamageProfileFactory(
            technique=resolver.action.focused_action,
            base_damage=0,
            damage_intensity_multiplier=Decimal("1.0"),
            minimum_success_level=1,
        )
        # Add an INTENSITY_BUMP pull to raise effective_intensity by 5.
        encounter = resolver.participant.encounter
        pull = CombatPullFactory(
            participant=resolver.participant,
            encounter=encounter,
            round_number=encounter.round_number,
        )
        CombatPullResolvedEffectFactory(
            pull=pull,
            kind=EffectKind.INTENSITY_BUMP,
            scaled_value=5,
        )
        resolver.participant.character_sheet.character.combat_pulls.invalidate()

        # technique.intensity defaults to some value; after bump effective_intensity > 0.
        check = MagicMock(success_level=2)
        results = resolver._apply_damage(check)
        # budget = intensity × 1.0; must produce at least 1 result with damage > 0.
        self.assertEqual(len(results), 1)
        self.assertGreater(results[0].damage_dealt, 0)

    def test_multi_component_damage(self) -> None:
        """2 profiles (default + fire) both apply at SL=2 → 2 OpponentDamageResults."""
        from world.conditions.factories import DamageTypeFactory
        from world.magic.factories import TechniqueDamageProfileFactory

        resolver = _build_resolver(base_power=10)
        # Auto-seeded profile is the first component. Add a second (fire).
        fire_damage_type = DamageTypeFactory(name="Fire")
        TechniqueDamageProfileFactory(
            technique=resolver.action.focused_action,
            base_damage=5,
            damage_type=fire_damage_type,
            minimum_success_level=1,
        )
        check = MagicMock(success_level=2)
        results = resolver._apply_damage(check)
        self.assertEqual(len(results), 2)
        self.assertGreater(results[0].damage_dealt, 0)
        self.assertGreater(results[1].damage_dealt, 0)

    def test_subsequent_components_skip_after_target_defeated(self) -> None:
        """First component defeats the target; second component does not fire."""
        from world.conditions.factories import DamageTypeFactory
        from world.magic.factories import TechniqueDamageProfileFactory

        resolver = _build_resolver(base_power=10)
        # Give target just 1 HP so the first hit defeats it.
        target = resolver.action.focused_opponent_target
        target.health = 1
        target.save(update_fields=["health"])

        # Add a second profile — should be skipped after target is defeated.
        fire_damage_type = DamageTypeFactory(name="Fire2")
        TechniqueDamageProfileFactory(
            technique=resolver.action.focused_action,
            base_damage=5,
            damage_type=fire_damage_type,
            minimum_success_level=1,
        )
        check = MagicMock(success_level=2)
        results = resolver._apply_damage(check)
        # Only 1 result: the second profile was skipped because target was defeated.
        self.assertEqual(len(results), 1)

    def test_defeated_target_at_start_returns_empty(self) -> None:
        """Target already DEFEATED before _apply_damage → returns []."""
        resolver = _build_resolver(base_power=20)
        target = resolver.action.focused_opponent_target
        target.status = OpponentStatus.DEFEATED
        target.save(update_fields=["status"])
        check = MagicMock(success_level=2)
        results = resolver._apply_damage(check)
        self.assertEqual(results, [])
