"""Phase A tests for the Renown system (#676).

Covers fame-tier derivation, set_persona_fame's floor + tier-recompute
behavior, the per-tick decay math, and the org accumulated decay (which
intentionally leaves base_prestige and accumulated_legend untouched).

Phase A is schema + decay primitives only. Event firing, source-prestige
flow, and outflow services land in B+.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.societies.constants import (
    FAME_DECAY_FLAT,
    FAME_DECAY_PCT,
    FAME_TIER_MULTIPLIERS,
    FAME_TIER_THRESHOLDS,
    FameTier,
)
from world.societies.factories import OrganizationFactory
from world.societies.renown import (
    apply_org_accumulated_decay,
    apply_persona_fame_decay,
    decay_all_org_accumulated,
    decay_all_persona_fame,
    derive_fame_tier,
    fame_multiplier_for,
    set_persona_fame,
)


def _make_persona():
    """Build a Character + sheet + PRIMARY persona via the factory chain."""
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    return sheet.primary_persona


class DeriveFameTierTests(TestCase):
    """``derive_fame_tier`` returns the right tier name at + around each threshold."""

    def test_zero_returns_normal(self) -> None:
        self.assertEqual(derive_fame_tier(0), FameTier.NORMAL.value)

    def test_one_below_talked_about_threshold_returns_normal(self) -> None:
        self.assertEqual(derive_fame_tier(99), FameTier.NORMAL.value)

    def test_exactly_talked_about_threshold_returns_talked_about(self) -> None:
        self.assertEqual(derive_fame_tier(100), FameTier.TALKED_ABOUT.value)

    def test_exactly_celebrity_threshold_returns_celebrity(self) -> None:
        self.assertEqual(derive_fame_tier(1_000), FameTier.CELEBRITY.value)

    def test_exactly_household_name_threshold_returns_household_name(self) -> None:
        self.assertEqual(derive_fame_tier(10_000), FameTier.HOUSEHOLD_NAME.value)

    def test_exactly_world_famous_threshold_returns_world_famous(self) -> None:
        self.assertEqual(derive_fame_tier(100_000), FameTier.WORLD_FAMOUS.value)

    def test_far_above_world_famous_still_world_famous(self) -> None:
        # No tier above World Famous; sky-high values stay there.
        self.assertEqual(derive_fame_tier(50_000_000), FameTier.WORLD_FAMOUS.value)


class FameMultiplierLookupTests(TestCase):
    """Multiplier lookup mirrors the constants table."""

    def test_normal_multiplier_is_one(self) -> None:
        self.assertEqual(fame_multiplier_for(FameTier.NORMAL.value), 1.0)

    def test_world_famous_multiplier_is_ten(self) -> None:
        self.assertEqual(fame_multiplier_for(FameTier.WORLD_FAMOUS.value), 10.0)

    def test_all_tiers_have_multipliers(self) -> None:
        # Smoke test against the constants table — guards against tier additions
        # that forget to add a multiplier entry.
        for tier in FameTier.values:
            self.assertIn(tier, FAME_TIER_MULTIPLIERS)


class SetPersonaFameTests(TestCase):
    """``set_persona_fame`` writes fame + recomputes tier, floors at 0."""

    def setUp(self) -> None:
        self.persona = _make_persona()

    def test_negative_input_floors_at_zero(self) -> None:
        set_persona_fame(self.persona, -50)
        self.persona.refresh_from_db()
        self.assertEqual(self.persona.fame_points, 0)
        self.assertEqual(self.persona.fame_tier, FameTier.NORMAL.value)

    def test_crossing_threshold_upward_updates_tier(self) -> None:
        tier_changed = set_persona_fame(self.persona, 1_500)
        self.assertTrue(tier_changed)
        self.persona.refresh_from_db()
        self.assertEqual(self.persona.fame_tier, FameTier.CELEBRITY.value)

    def test_crossing_threshold_downward_updates_tier(self) -> None:
        set_persona_fame(self.persona, 15_000)  # Household Name
        tier_changed = set_persona_fame(self.persona, 500)  # → Talked About
        self.assertTrue(tier_changed)
        self.persona.refresh_from_db()
        self.assertEqual(self.persona.fame_tier, FameTier.TALKED_ABOUT.value)

    def test_no_tier_change_when_within_band(self) -> None:
        set_persona_fame(self.persona, 500)  # Talked About
        tier_changed = set_persona_fame(self.persona, 750)  # still Talked About
        self.assertFalse(tier_changed)
        self.persona.refresh_from_db()
        self.assertEqual(self.persona.fame_tier, FameTier.TALKED_ABOUT.value)


class ApplyPersonaFameDecayTests(TestCase):
    """Decay math: ``new = max(0, old - FLAT - PCT * old)``."""

    def setUp(self) -> None:
        self.persona = _make_persona()

    def test_zero_fame_is_no_op(self) -> None:
        # Direct write to bypass set_persona_fame for this baseline check.
        self.persona.fame_points = 0
        self.persona.fame_tier = FameTier.NORMAL.value
        self.persona.save(update_fields=["fame_points", "fame_tier"])
        tier_changed = apply_persona_fame_decay(self.persona)
        self.assertFalse(tier_changed)
        self.persona.refresh_from_db()
        self.assertEqual(self.persona.fame_points, 0)

    def test_low_fame_drained_by_flat(self) -> None:
        # At fame 50, decay = 5 + 2 = 7. 50 → 43, still Normal.
        set_persona_fame(self.persona, 50)
        apply_persona_fame_decay(self.persona)
        self.persona.refresh_from_db()
        self.assertEqual(self.persona.fame_points, 43)
        self.assertEqual(self.persona.fame_tier, FameTier.NORMAL.value)

    def test_high_fame_dominated_by_pct(self) -> None:
        # At fame 200_000, decay = 5 + 10000 = 10005. The pct term (10k)
        # dominates over the flat (5). Starting safely above the World Famous
        # threshold (100k) so one tick doesn't drop the tier.
        set_persona_fame(self.persona, 200_000)
        apply_persona_fame_decay(self.persona)
        self.persona.refresh_from_db()
        expected = 200_000 - FAME_DECAY_FLAT - int(200_000 * FAME_DECAY_PCT)
        self.assertEqual(self.persona.fame_points, expected)
        self.assertEqual(self.persona.fame_tier, FameTier.WORLD_FAMOUS.value)

    def test_decay_floors_at_zero(self) -> None:
        # Set fame to FLAT-1 so decay would overshoot — should floor at 0.
        set_persona_fame(self.persona, FAME_DECAY_FLAT - 1)
        apply_persona_fame_decay(self.persona)
        self.persona.refresh_from_db()
        self.assertEqual(self.persona.fame_points, 0)
        self.assertEqual(self.persona.fame_tier, FameTier.NORMAL.value)

    def test_decay_can_cross_threshold_downward(self) -> None:
        # Fame just above Talked About (100). One tick at FLAT=5 + ~5% drops below.
        set_persona_fame(self.persona, 102)
        tier_changed = apply_persona_fame_decay(self.persona)
        self.persona.refresh_from_db()
        # 102 - 5 - 5 = 92, below TALKED_ABOUT threshold → tier should drop.
        self.assertTrue(tier_changed)
        self.assertEqual(self.persona.fame_tier, FameTier.NORMAL.value)


class DecayAllPersonaFameTests(TestCase):
    """The sweep entrypoint only touches personas with fame_points > 0."""

    def test_sweep_returns_touched_count(self) -> None:
        p1 = _make_persona()
        p2 = _make_persona()
        _untouched = _make_persona()
        set_persona_fame(p1, 50)
        set_persona_fame(p2, 200)
        touched = decay_all_persona_fame()
        # Only p1 + p2 had positive fame at sweep time. Untouched stayed at 0.
        self.assertEqual(touched, 2)


class ApplyOrgAccumulatedDecayTests(TestCase):
    """Org decay touches accumulated_prestige + accumulated_fame only.

    base_prestige and accumulated_legend are permanent — the decay function
    must leave them alone.
    """

    def test_decay_reduces_accumulated_prestige(self) -> None:
        org = OrganizationFactory()
        org.accumulated_prestige = 1_000
        org.save(update_fields=["accumulated_prestige"])
        apply_org_accumulated_decay(org)
        org.refresh_from_db()
        # 1000 - 5 - 50 = 945
        self.assertEqual(org.accumulated_prestige, 945)

    def test_decay_reduces_accumulated_fame(self) -> None:
        org = OrganizationFactory()
        org.accumulated_fame = 500
        org.save(update_fields=["accumulated_fame"])
        apply_org_accumulated_decay(org)
        org.refresh_from_db()
        # 500 - 5 - 25 = 470
        self.assertEqual(org.accumulated_fame, 470)

    def test_decay_leaves_base_prestige_untouched(self) -> None:
        org = OrganizationFactory()
        org.base_prestige = 5_000
        org.accumulated_prestige = 100
        org.save(update_fields=["base_prestige", "accumulated_prestige"])
        apply_org_accumulated_decay(org)
        org.refresh_from_db()
        self.assertEqual(org.base_prestige, 5_000)

    def test_decay_leaves_accumulated_legend_untouched(self) -> None:
        # accumulated_legend is permanent — used as a covenant ritual gate
        # and never decays.
        org = OrganizationFactory()
        org.accumulated_legend = 800
        org.accumulated_prestige = 100
        org.save(update_fields=["accumulated_legend", "accumulated_prestige"])
        apply_org_accumulated_decay(org)
        org.refresh_from_db()
        self.assertEqual(org.accumulated_legend, 800)

    def test_zero_accumulated_is_no_op(self) -> None:
        org = OrganizationFactory()
        org.accumulated_prestige = 0
        org.accumulated_fame = 0
        org.save(update_fields=["accumulated_prestige", "accumulated_fame"])
        apply_org_accumulated_decay(org)
        org.refresh_from_db()
        self.assertEqual(org.accumulated_prestige, 0)
        self.assertEqual(org.accumulated_fame, 0)


class DecayAllOrgAccumulatedTests(TestCase):
    """The sweep entrypoint only touches orgs with positive accumulated values."""

    def test_sweep_returns_touched_count(self) -> None:
        org_with_prestige = OrganizationFactory()
        org_with_prestige.accumulated_prestige = 100
        org_with_prestige.save(update_fields=["accumulated_prestige"])

        org_with_fame = OrganizationFactory()
        org_with_fame.accumulated_fame = 50
        org_with_fame.save(update_fields=["accumulated_fame"])

        _org_idle = OrganizationFactory()

        touched = decay_all_org_accumulated()
        self.assertEqual(touched, 2)


class FieldDefaultsTests(TestCase):
    """All new Renown fields default to 0 / NORMAL on fresh persona/org rows."""

    def test_new_persona_has_zero_renown_fields(self) -> None:
        persona = _make_persona()
        self.assertEqual(persona.prestige_from_dwellings, 0)
        self.assertEqual(persona.prestige_from_items, 0)
        self.assertEqual(persona.prestige_from_orgs, 0)
        self.assertEqual(persona.prestige_from_deeds, 0)
        self.assertEqual(persona.total_prestige, 0)
        self.assertEqual(persona.fame_points, 0)
        self.assertEqual(persona.fame_tier, FameTier.NORMAL.value)

    def test_new_org_has_zero_renown_fields(self) -> None:
        org = OrganizationFactory()
        self.assertEqual(org.base_prestige, 0)
        self.assertEqual(org.accumulated_prestige, 0)
        self.assertEqual(org.accumulated_fame, 0)
        self.assertEqual(org.accumulated_legend, 0)


class FameTierThresholdsConsistencyTests(TestCase):
    """The constants tables are internally consistent."""

    def test_all_tiers_have_thresholds(self) -> None:
        for tier in FameTier.values:
            self.assertIn(tier, FAME_TIER_THRESHOLDS)

    def test_thresholds_are_monotonic_increasing(self) -> None:
        # From normal → world famous, the thresholds must climb.
        previous = -1
        for tier in (
            FameTier.NORMAL.value,
            FameTier.TALKED_ABOUT.value,
            FameTier.CELEBRITY.value,
            FameTier.HOUSEHOLD_NAME.value,
            FameTier.WORLD_FAMOUS.value,
        ):
            self.assertGreater(FAME_TIER_THRESHOLDS[tier], previous)
            previous = FAME_TIER_THRESHOLDS[tier]

    def test_multipliers_are_monotonic_increasing(self) -> None:
        previous = 0.0
        for tier in (
            FameTier.NORMAL.value,
            FameTier.TALKED_ABOUT.value,
            FameTier.CELEBRITY.value,
            FameTier.HOUSEHOLD_NAME.value,
            FameTier.WORLD_FAMOUS.value,
        ):
            self.assertGreater(FAME_TIER_MULTIPLIERS[tier], previous)
            previous = FAME_TIER_MULTIPLIERS[tier]
