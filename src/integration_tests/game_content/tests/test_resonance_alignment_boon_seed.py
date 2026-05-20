"""TDD tests for _seed_resonance_alignment_boons() — T13.

Asserts that:
1. ≥2 named buff ConditionTemplate rows exist in the "Magical Boon" category after seed.
2. Each template has non-empty authored descriptions and distinct names.
3. ≥2 ResonanceAlignmentBoonTier rows exist for the Abyssal/Abyssal ALIGNED pair (#5).
4. Tiers ascend by min_magnitude: LOW band → lesser buff, HIGH band → greater buff.
5. The pair's affinity_interaction is verified by source/environment affinity (not pk).
6. Band-selection mirrors the service logic: max(t for t if t.min_magnitude <= magnitude).
7. Idempotency: running the helper twice produces no duplicate rows.
8. full_clean() guard: constructing a tier against a non-ALIGNED interaction raises ValidationError.
9. Boon templates are in a POSITIVE ConditionCategory (is_negative=False).
10. Injury/reaction templates remain in the NEGATIVE "Magical" category (is_negative=True).

Test pattern: call seed_starter_magic_story() (master orchestrator), then assert via
real ORM rows. Inherits ResonanceCacheIsolationMixin so manager caches are flushed
before each test method.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import TestCase

from integration_tests.game_content.magic import (
    _seed_resonance_alignment_boons,
    seed_starter_magic_story,
)
from world.magic.constants import AffinityInteractionKind, ResonanceValence
from world.magic.tests._cache_isolation import ResonanceCacheIsolationMixin


class ResonanceAlignmentBoonConditionTemplateTests(ResonanceCacheIsolationMixin, TestCase):
    """After master seed: boon ConditionTemplate rows exist in the positive Magical Boon
    category."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_starter_magic_story()

    def setUp(self) -> None:
        # Cache isolation must happen before each test method accesses managers.
        super().setUp()

    def _get_boon_templates(self):
        """Fetch all ConditionTemplates referenced by ResonanceAlignmentBoonTier rows."""
        from world.conditions.models import ConditionTemplate
        from world.magic.models.resonance_environment import ResonanceAlignmentBoonTier

        boon_template_ids = set(
            ResonanceAlignmentBoonTier.objects.values_list("condition_template_id", flat=True)
        )
        return list(ConditionTemplate.objects.filter(pk__in=boon_template_ids))

    def test_at_least_two_boon_condition_templates_exist(self) -> None:
        """At least 2 boon ConditionTemplates are seeded."""
        templates = self._get_boon_templates()
        self.assertGreaterEqual(
            len(templates),
            2,
            f"Expected ≥2 boon ConditionTemplates; got {len(templates)}.",
        )

    def test_boon_templates_are_in_magical_boon_category(self) -> None:
        """All boon ConditionTemplates belong to the 'Magical Boon' category."""
        templates = self._get_boon_templates()
        for tpl in templates:
            self.assertEqual(
                tpl.category.name,
                "Magical Boon",
                f"Boon template '{tpl.name}' has category "
                f"'{tpl.category.name}', expected 'Magical Boon'.",
            )

    def test_boon_templates_category_is_positive(self) -> None:
        """Boon ConditionTemplates must be in a POSITIVE category (is_negative=False)."""
        templates = self._get_boon_templates()
        for tpl in templates:
            self.assertFalse(
                tpl.category.is_negative,
                f"Boon template '{tpl.name}' is in a negative category "
                f"'{tpl.category.name}' — boons must be positive.",
            )

    def test_magical_boon_category_exists_and_is_positive(self) -> None:
        """The 'Magical Boon' ConditionCategory exists with is_negative=False."""
        from world.conditions.models import ConditionCategory

        cat = ConditionCategory.objects.get(name="Magical Boon")
        self.assertFalse(
            cat.is_negative,
            "ConditionCategory 'Magical Boon' must have is_negative=False.",
        )

    def test_injury_templates_remain_in_negative_magical_category(self) -> None:
        """Reaction/injury templates (Singed, Hallowed Burn) remain in the negative 'Magical'
        category — the boon fix must not regress injury categorization."""
        from world.conditions.models import ConditionTemplate

        for injury_name in ("Singed", "Hallowed Burn"):
            tpl = ConditionTemplate.objects.get(name=injury_name)
            self.assertEqual(
                tpl.category.name,
                "Magical",
                f"Injury template '{injury_name}' moved out of 'Magical' category.",
            )
            self.assertTrue(
                tpl.category.is_negative,
                f"Injury template '{injury_name}' is no longer in a negative category.",
            )

    def test_boon_templates_have_distinct_names(self) -> None:
        """Boon ConditionTemplates must have distinct names (different per band)."""
        templates = self._get_boon_templates()
        names = [t.name for t in templates]
        self.assertEqual(
            len(names),
            len(set(names)),
            f"Boon template names are not distinct: {names}",
        )

    def test_boon_templates_have_non_empty_description(self) -> None:
        """Every boon ConditionTemplate has authored description text."""
        templates = self._get_boon_templates()
        for tpl in templates:
            self.assertTrue(
                tpl.description.strip(),
                f"Boon template '{tpl.name}' has empty description.",
            )

    def test_boon_templates_have_non_empty_player_description(self) -> None:
        """Every boon ConditionTemplate has authored player_description text."""
        templates = self._get_boon_templates()
        for tpl in templates:
            self.assertTrue(
                tpl.player_description.strip(),
                f"Boon template '{tpl.name}' has empty player_description.",
            )

    def test_boon_templates_have_non_empty_observer_description(self) -> None:
        """Every boon ConditionTemplate has authored observer_description text."""
        templates = self._get_boon_templates()
        for tpl in templates:
            self.assertTrue(
                tpl.observer_description.strip(),
                f"Boon template '{tpl.name}' has empty observer_description.",
            )


class ResonanceAlignmentBoonTierTests(ResonanceCacheIsolationMixin, TestCase):
    """After master seed: ResonanceAlignmentBoonTier rows exist for Abyssal/Abyssal pair."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_starter_magic_story()

    def setUp(self) -> None:
        super().setUp()

    def _get_pair5(self):
        """Fetch AffinityInteraction pair #5: Abyssal source → Abyssal environment (ALIGNED)."""
        from world.magic.models.affinity import Affinity
        from world.magic.models.resonance_environment import AffinityInteraction

        abyssal = Affinity.objects.get(name="Abyssal")
        return AffinityInteraction.objects.get(
            source_affinity=abyssal,
            environment_affinity=abyssal,
        )

    def _get_pair5_tiers(self):
        """Return boon tiers for pair #5 in ascending min_magnitude order."""
        from world.magic.models.resonance_environment import ResonanceAlignmentBoonTier

        pair5 = self._get_pair5()
        return list(
            ResonanceAlignmentBoonTier.objects.filter(
                affinity_interaction=pair5,
            ).order_by("min_magnitude")
        )

    def test_pair5_interaction_is_aligned(self) -> None:
        """Pair #5 (Abyssal→Abyssal) has ALIGNED valence."""
        pair5 = self._get_pair5()
        self.assertEqual(pair5.valence, ResonanceValence.ALIGNED)

    def test_at_least_two_boon_tiers_for_pair5(self) -> None:
        """At least 2 ResonanceAlignmentBoonTier rows exist for pair #5."""
        tiers = self._get_pair5_tiers()
        self.assertGreaterEqual(
            len(tiers),
            2,
            f"Expected ≥2 boon tiers for Abyssal/Abyssal pair; got {len(tiers)}.",
        )

    def test_tiers_have_ascending_min_magnitude(self) -> None:
        """Tiers are in strictly ascending min_magnitude order."""
        tiers = self._get_pair5_tiers()
        magnitudes = [t.min_magnitude for t in tiers]
        self.assertEqual(
            magnitudes,
            sorted(magnitudes),
            f"Expected ascending min_magnitude; got {magnitudes}.",
        )
        # Must be strictly ascending (no duplicate thresholds — enforced by unique constraint)
        self.assertEqual(
            len(magnitudes),
            len(set(magnitudes)),
            f"Duplicate min_magnitude values found: {magnitudes}.",
        )

    def test_low_and_high_tiers_reference_different_templates(self) -> None:
        """The lowest-threshold tier and highest-threshold tier reference different
        ConditionTemplates, with names indicating their band ('Minor' vs 'Deep')."""
        tiers = self._get_pair5_tiers()
        low_tier = tiers[0]
        high_tier = tiers[-1]
        self.assertNotEqual(
            low_tier.condition_template_id,
            high_tier.condition_template_id,
            "Low and high boon tiers must reference different ConditionTemplates.",
        )
        self.assertIn(
            "Minor",
            low_tier.condition_template.name,
            f"Low-band template name should contain 'Minor'; "
            f"got '{low_tier.condition_template.name}'.",
        )
        self.assertIn(
            "Deep",
            high_tier.condition_template.name,
            f"High-band template name should contain 'Deep'; "
            f"got '{high_tier.condition_template.name}'.",
        )

    def test_tier_affinity_interaction_is_aligned(self) -> None:
        """All tiers reference the ALIGNED pair (full_clean passed at creation)."""
        tiers = self._get_pair5_tiers()
        for tier in tiers:
            self.assertEqual(
                tier.affinity_interaction.valence,
                ResonanceValence.ALIGNED,
                f"Tier {tier.pk} references non-ALIGNED interaction.",
            )

    def test_low_band_tier_has_min_magnitude_1(self) -> None:
        """The low-band tier threshold is 1 (any positive magnitude qualifies)."""
        tiers = self._get_pair5_tiers()
        low_tier = tiers[0]
        self.assertEqual(
            low_tier.min_magnitude,
            1,
            f"Expected low-band min_magnitude=1; got {low_tier.min_magnitude}.",
        )

    def test_high_band_tier_has_min_magnitude_at_least_40(self) -> None:
        """The high-band tier threshold is ≥40 so it is reachable by the seeded
        Abyssal Sanctum room (magnitude=60) but not by a low-magnitude room."""
        tiers = self._get_pair5_tiers()
        high_tier = tiers[-1]
        self.assertGreaterEqual(
            high_tier.min_magnitude,
            40,
            f"Expected high-band min_magnitude ≥ 40; got {high_tier.min_magnitude}.",
        )


class ResonanceAlignmentBandSelectionTests(ResonanceCacheIsolationMixin, TestCase):
    """Band-selection logic matches the service's max(t if t.min_magnitude <= magnitude) rule."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_starter_magic_story()

    def setUp(self) -> None:
        super().setUp()

    def _get_pair5_interaction(self):
        from world.magic.models.affinity import Affinity
        from world.magic.models.resonance_environment import AffinityInteraction

        abyssal = Affinity.objects.get(name="Abyssal")
        return AffinityInteraction.objects.get(
            source_affinity=abyssal,
            environment_affinity=abyssal,
        )

    def _select_tier(self, interaction, magnitude: int):
        """Mirror the service's band-selection: highest tier with min_magnitude <= magnitude."""
        tiers = interaction.cached_alignment_boon_tiers  # already ascending
        matching = [t for t in tiers if t.min_magnitude <= magnitude]
        if not matching:
            return None
        return max(matching, key=lambda t: t.min_magnitude)

    def test_high_magnitude_selects_greater_buff(self) -> None:
        """Magnitude 60 (the seeded Abyssal Sanctum level) selects the high-band tier."""
        interaction = self._get_pair5_interaction()
        tiers = sorted(
            interaction.cached_alignment_boon_tiers,
            key=lambda t: t.min_magnitude,
        )
        high_tier = tiers[-1]
        selected = self._select_tier(interaction, magnitude=60)
        self.assertIsNotNone(selected, "Should select a tier at magnitude=60.")
        self.assertEqual(
            selected.pk,
            high_tier.pk,
            f"At magnitude=60, expected high-band tier (min_magnitude={high_tier.min_magnitude}); "
            f"got tier with min_magnitude={selected.min_magnitude}.",
        )

    def test_low_magnitude_selects_lesser_buff(self) -> None:
        """Magnitude 5 (well below the high band) selects only the low-band tier."""
        interaction = self._get_pair5_interaction()
        tiers = sorted(
            interaction.cached_alignment_boon_tiers,
            key=lambda t: t.min_magnitude,
        )
        low_tier = tiers[0]
        high_tier = tiers[-1]
        selected = self._select_tier(interaction, magnitude=5)
        # 5 is above the low threshold (1) but below the high threshold (≥40)
        if low_tier.min_magnitude <= 5 < high_tier.min_magnitude:
            self.assertEqual(
                selected.pk,
                low_tier.pk,
                f"At magnitude=5, expected low-band tier; got {selected}.",
            )
        else:
            # If the seeded thresholds differ, still assert we got a band (not None).
            self.assertIsNotNone(
                selected,
                "Should select at least the low-band tier at magnitude=5.",
            )

    def test_magnitude_zero_selects_no_tier(self) -> None:
        """Magnitude 0 (no resonance effect) selects no tier (service returns early)."""
        interaction = self._get_pair5_interaction()
        selected = self._select_tier(interaction, magnitude=0)
        # All tiers have min_magnitude >= 1, so none qualify at magnitude=0
        self.assertIsNone(
            selected,
            "Magnitude 0 must select no tier; all tiers should have min_magnitude >= 1.",
        )


class ResonanceAlignmentBoonIdempotencyTests(ResonanceCacheIsolationMixin, TestCase):
    """Running _seed_resonance_alignment_boons() twice creates no duplicate rows."""

    def setUp(self) -> None:
        super().setUp()

    def test_idempotent_double_run(self) -> None:
        """Running the helper twice produces identical row counts
        (no duplicate category/template/tier)."""
        from world.conditions.models import ConditionCategory, ConditionTemplate
        from world.magic.models.resonance_environment import ResonanceAlignmentBoonTier

        seed_starter_magic_story()
        category_count_1 = ConditionCategory.objects.count()
        template_count_1 = ConditionTemplate.objects.count()
        tier_count_1 = ResonanceAlignmentBoonTier.objects.count()

        # Clear manager caches so the second run re-fetches from DB
        from world.magic.models.resonance_environment import AffinityInteraction

        AffinityInteraction.objects.clear_cache()
        ResonanceAlignmentBoonTier.objects.clear_cache()

        _seed_resonance_alignment_boons()

        category_count_2 = ConditionCategory.objects.count()
        template_count_2 = ConditionTemplate.objects.count()
        tier_count_2 = ResonanceAlignmentBoonTier.objects.count()

        self.assertEqual(
            category_count_2,
            category_count_1,
            f"ConditionCategory count changed on second run: "
            f"{category_count_1} → {category_count_2}",
        )
        self.assertEqual(
            template_count_2,
            template_count_1,
            f"ConditionTemplate count changed on second run: "
            f"{template_count_1} → {template_count_2}",
        )
        self.assertEqual(
            tier_count_2,
            tier_count_1,
            f"ResonanceAlignmentBoonTier count changed on second run: "
            f"{tier_count_1} → {tier_count_2}",
        )


class ResonanceAlignmentBoonFullCleanGuardTests(ResonanceCacheIsolationMixin, TestCase):
    """full_clean() is exercised and rejects non-ALIGNED interactions."""

    def setUp(self) -> None:
        super().setUp()

    def test_tier_against_opposed_interaction_raises_validation_error(self) -> None:
        """Constructing a tier against an OPPOSED interaction and calling full_clean()
        raises ValidationError — proving the carry-forward guard is active."""
        from world.conditions.factories import ConditionTemplateFactory
        from world.magic.factories import AffinityInteractionFactory
        from world.magic.models.resonance_environment import ResonanceAlignmentBoonTier

        opposed_interaction = AffinityInteractionFactory(
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REJECT,
        )
        template = ConditionTemplateFactory()
        tier = ResonanceAlignmentBoonTier(
            affinity_interaction=opposed_interaction,
            min_magnitude=10,
            condition_template=template,
        )
        with self.assertRaises(ValidationError):
            tier.full_clean()
