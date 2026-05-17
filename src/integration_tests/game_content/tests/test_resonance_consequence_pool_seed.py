"""TDD tests for _seed_resonance_environment_consequence_pools() — T12.

Asserts that:
1. ConsequencePool rows exist for AffinityInteraction pair #4 (Abyssal→Celestial)
   and pair #7 (Primal→Celestial).
2. Each pool has exactly 4 Consequence rows — one per CheckOutcome tier.
3. Each Consequence has the correct ConditionTemplate wired via a
   ConsequenceEffect(effect_type=APPLY_CONDITION).
4. The Critical Failure Consequence has BOTH Hallowed Burn AND Cast Disrupted
   ConsequenceEffects.
5. AffinityInteraction rows #4 and #7 have consequence_pool set to the right pool.
6. Idempotency: running the seed helper twice produces no duplicate rows.

Test pattern: call seed_starter_magic_story() (the master orchestrator), then
assert via real ORM rows. Inherits ResonanceCacheIsolationMixin so manager
caches are flushed before each test method.
"""

from __future__ import annotations

from django.test import TestCase

from integration_tests.game_content.magic import (
    _HALLOWED_REACTION_SPECS,
    CRIT_FAIL_CONDITION_NAMES,
    HALLOWED_REACTION_CONDITION_NAMES,
    _seed_resonance_environment_consequence_pools,
    seed_starter_magic_story,
)
from world.magic.tests._cache_isolation import ResonanceCacheIsolationMixin


class ResonanceConsequencePoolSeedTests(ResonanceCacheIsolationMixin, TestCase):
    """Core assertions: pools, consequences, effects, and FK wiring after seed."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_starter_magic_story()

    def setUp(self) -> None:
        # Cache isolation must happen before test-method body accesses the manager.
        super().setUp()

    # ------------------------------------------------------------------
    # Helper: fetch the two AffinityInteraction rows under test
    # ------------------------------------------------------------------

    def _get_pair4(self):
        from world.magic.models.affinity import Affinity
        from world.magic.models.resonance_environment import AffinityInteraction

        abyssal = Affinity.objects.get(name="Abyssal")
        celestial = Affinity.objects.get(name="Celestial")
        return AffinityInteraction.objects.get(
            source_affinity=abyssal,
            environment_affinity=celestial,
        )

    def _get_pair7(self):
        from world.magic.models.affinity import Affinity
        from world.magic.models.resonance_environment import AffinityInteraction

        primal = Affinity.objects.get(name="Primal")
        celestial = Affinity.objects.get(name="Celestial")
        return AffinityInteraction.objects.get(
            source_affinity=primal,
            environment_affinity=celestial,
        )

    # ------------------------------------------------------------------
    # Pool existence
    # ------------------------------------------------------------------

    def test_pair4_consequence_pool_is_set(self) -> None:
        """AffinityInteraction (Abyssal→Celestial) has consequence_pool populated."""
        pair4 = self._get_pair4()
        self.assertIsNotNone(pair4.consequence_pool_id)

    def test_pair7_consequence_pool_is_set(self) -> None:
        """AffinityInteraction (Primal→Celestial) has consequence_pool populated."""
        pair7 = self._get_pair7()
        self.assertIsNotNone(pair7.consequence_pool_id)

    def test_pair4_and_pair7_use_different_pools(self) -> None:
        """Each pairing gets its own distinct ConsequencePool."""
        pair4 = self._get_pair4()
        pair7 = self._get_pair7()
        self.assertNotEqual(pair4.consequence_pool_id, pair7.consequence_pool_id)

    # ------------------------------------------------------------------
    # Pool has 4 entries (one per CheckOutcome tier)
    # ------------------------------------------------------------------

    def test_pair4_pool_has_four_consequences(self) -> None:
        from actions.models import ConsequencePoolEntry

        pair4 = self._get_pair4()
        count = ConsequencePoolEntry.objects.filter(pool=pair4.consequence_pool).count()
        self.assertEqual(count, 4)

    def test_pair7_pool_has_four_consequences(self) -> None:
        from actions.models import ConsequencePoolEntry

        pair7 = self._get_pair7()
        count = ConsequencePoolEntry.objects.filter(pool=pair7.consequence_pool).count()
        self.assertEqual(count, 4)

    # ------------------------------------------------------------------
    # CheckOutcome tier → ConditionTemplate mapping
    # ------------------------------------------------------------------

    def _assert_outcome_condition(
        self,
        pool,
        outcome_name: str,
        expected_condition_name: str,
    ) -> None:
        """Assert that the pool's Consequence for outcome_name applies expected_condition."""
        from actions.models import ConsequencePoolEntry
        from world.checks.constants import EffectType

        entry = ConsequencePoolEntry.objects.select_related("consequence__outcome_tier").get(
            pool=pool,
            consequence__outcome_tier__name=outcome_name,
        )
        consequence = entry.consequence
        effects = list(
            consequence.effects.filter(
                effect_type=EffectType.APPLY_CONDITION,
                condition_template__name=expected_condition_name,
            )
        )
        self.assertEqual(
            len(effects),
            1,
            f"Expected exactly 1 APPLY_CONDITION effect for '{expected_condition_name}' "
            f"on '{outcome_name}' consequence; got {len(effects)}.",
        )

    def test_pair4_critical_success_applies_tempered_against_light(self) -> None:
        pair4 = self._get_pair4()
        self._assert_outcome_condition(
            pair4.consequence_pool,
            "Critical Success",
            HALLOWED_REACTION_CONDITION_NAMES["Critical Success"],
        )

    def test_pair4_success_applies_singed(self) -> None:
        pair4 = self._get_pair4()
        self._assert_outcome_condition(
            pair4.consequence_pool,
            "Success",
            HALLOWED_REACTION_CONDITION_NAMES["Success"],
        )

    def test_pair4_failure_applies_burning(self) -> None:
        pair4 = self._get_pair4()
        self._assert_outcome_condition(
            pair4.consequence_pool,
            "Failure",
            HALLOWED_REACTION_CONDITION_NAMES["Failure"],
        )

    def test_pair4_critical_failure_applies_hallowed_burn(self) -> None:
        from actions.models import ConsequencePoolEntry
        from world.checks.constants import EffectType

        pair4 = self._get_pair4()
        entry = ConsequencePoolEntry.objects.select_related("consequence__outcome_tier").get(
            pool=pair4.consequence_pool,
            consequence__outcome_tier__name="Critical Failure",
        )
        effects = list(
            entry.consequence.effects.filter(
                effect_type=EffectType.APPLY_CONDITION,
                condition_template__name="Hallowed Burn",
            )
        )
        self.assertEqual(len(effects), 1, "Expected APPLY_CONDITION for Hallowed Burn on crit-fail")

    def test_pair4_critical_failure_applies_cast_disrupted(self) -> None:
        from actions.models import ConsequencePoolEntry
        from world.checks.constants import EffectType

        pair4 = self._get_pair4()
        entry = ConsequencePoolEntry.objects.select_related("consequence__outcome_tier").get(
            pool=pair4.consequence_pool,
            consequence__outcome_tier__name="Critical Failure",
        )
        effects = list(
            entry.consequence.effects.filter(
                effect_type=EffectType.APPLY_CONDITION,
                condition_template__name="Cast Disrupted",
            )
        )
        self.assertEqual(
            len(effects), 1, "Expected APPLY_CONDITION for Cast Disrupted on crit-fail"
        )

    def test_pair4_critical_failure_has_exactly_two_effects(self) -> None:
        """Crit-fail Consequence must have exactly 2 APPLY_CONDITION effects."""
        from actions.models import ConsequencePoolEntry
        from world.checks.constants import EffectType

        pair4 = self._get_pair4()
        entry = ConsequencePoolEntry.objects.select_related("consequence__outcome_tier").get(
            pool=pair4.consequence_pool,
            consequence__outcome_tier__name="Critical Failure",
        )
        effect_count = entry.consequence.effects.filter(
            effect_type=EffectType.APPLY_CONDITION
        ).count()
        self.assertEqual(effect_count, 2, "Crit-fail must have exactly 2 APPLY_CONDITION effects")

    def test_crit_fail_condition_names_constant_covers_both(self) -> None:
        """CRIT_FAIL_CONDITION_NAMES constant includes both expected names."""
        self.assertIn("Hallowed Burn", CRIT_FAIL_CONDITION_NAMES)
        self.assertIn("Cast Disrupted", CRIT_FAIL_CONDITION_NAMES)

    # ------------------------------------------------------------------
    # Pair 7 has the same outcome mapping (spot-check)
    # ------------------------------------------------------------------

    def test_pair7_critical_success_applies_tempered_against_light(self) -> None:
        pair7 = self._get_pair7()
        self._assert_outcome_condition(
            pair7.consequence_pool,
            "Critical Success",
            HALLOWED_REACTION_CONDITION_NAMES["Critical Success"],
        )

    def test_pair7_critical_failure_has_exactly_two_effects(self) -> None:
        """Pair #7 crit-fail Consequence also has 2 APPLY_CONDITION effects."""
        from actions.models import ConsequencePoolEntry
        from world.checks.constants import EffectType

        pair7 = self._get_pair7()
        entry = ConsequencePoolEntry.objects.select_related("consequence__outcome_tier").get(
            pool=pair7.consequence_pool,
            consequence__outcome_tier__name="Critical Failure",
        )
        effect_count = entry.consequence.effects.filter(
            effect_type=EffectType.APPLY_CONDITION
        ).count()
        self.assertEqual(effect_count, 2)

    # ------------------------------------------------------------------
    # HALLOWED_REACTION_CONDITION_NAMES constant is complete
    # ------------------------------------------------------------------

    def test_hallowed_reaction_condition_names_has_all_four_tiers(self) -> None:
        for tier in ("Critical Success", "Success", "Failure", "Critical Failure"):
            self.assertIn(tier, HALLOWED_REACTION_CONDITION_NAMES)


class ResonanceConsequencePoolIdempotencyTests(ResonanceCacheIsolationMixin, TestCase):
    """Running _seed_resonance_environment_consequence_pools() twice does not create duplicates."""

    def setUp(self) -> None:
        super().setUp()

    def test_idempotent_double_run(self) -> None:
        """Calling the seed helper twice produces identical row counts."""
        from actions.models import ConsequencePool, ConsequencePoolEntry
        from world.checks.models import Consequence, ConsequenceEffect

        seed_starter_magic_story()
        pool_count_1 = ConsequencePool.objects.count()
        entry_count_1 = ConsequencePoolEntry.objects.count()
        consequence_count_1 = Consequence.objects.count()
        effect_count_1 = ConsequenceEffect.objects.count()

        # Run the specific helper a second time (simulates re-running the orchestrator)
        _seed_resonance_environment_consequence_pools()

        self.assertEqual(ConsequencePool.objects.count(), pool_count_1)
        self.assertEqual(ConsequencePoolEntry.objects.count(), entry_count_1)
        self.assertEqual(Consequence.objects.count(), consequence_count_1)
        self.assertEqual(ConsequenceEffect.objects.count(), effect_count_1)


class HallowedReactionSpecDerivationTests(TestCase):
    """Drift guard: derived name constants must stay consistent with the source.

    These assertions make it impossible to silently break the single source of
    truth (``_HALLOWED_REACTION_SPECS``): if anyone restates / drops / mistypes
    a condition name in a derived structure, one of these fails immediately.
    No DB access — pure constant consistency.
    """

    def _all_spec_names(self) -> set[str]:
        return {spec["name"] for spec in _HALLOWED_REACTION_SPECS}

    def test_single_effect_names_are_real_spec_names(self) -> None:
        """Every HALLOWED_REACTION_CONDITION_NAMES value is a real spec name."""
        spec_names = self._all_spec_names()
        for tier, condition_name in HALLOWED_REACTION_CONDITION_NAMES.items():
            self.assertIn(
                condition_name,
                spec_names,
                f"Tier {tier!r} maps to {condition_name!r}, not in _HALLOWED_REACTION_SPECS",
            )

    def test_crit_fail_names_are_real_spec_names(self) -> None:
        """Every CRIT_FAIL_CONDITION_NAMES entry is a real spec name."""
        spec_names = self._all_spec_names()
        for condition_name in CRIT_FAIL_CONDITION_NAMES:
            self.assertIn(condition_name, spec_names)

    def test_derived_union_equals_full_spec_name_set(self) -> None:
        """Single-effect names ∪ crit-fail names == the full spec name set.

        Proves nothing was dropped and no extra name was invented across the
        two derived structures.
        """
        union = set(HALLOWED_REACTION_CONDITION_NAMES.values()) | set(CRIT_FAIL_CONDITION_NAMES)
        self.assertEqual(union, self._all_spec_names())

    def test_crit_fail_names_match_specs_with_crit_fail_tier(self) -> None:
        """CRIT_FAIL_CONDITION_NAMES exactly equals specs whose tier is Critical Failure."""
        expected = [
            spec["name"]
            for spec in _HALLOWED_REACTION_SPECS
            if spec["outcome_tier"] == "Critical Failure"
        ]
        self.assertEqual(CRIT_FAIL_CONDITION_NAMES, expected)

    def test_crit_fail_tier_primary_is_first_crit_fail_spec(self) -> None:
        """The 'Critical Failure' tier in the dict maps to the FIRST crit-fail spec."""
        self.assertEqual(
            HALLOWED_REACTION_CONDITION_NAMES["Critical Failure"],
            CRIT_FAIL_CONDITION_NAMES[0],
        )
