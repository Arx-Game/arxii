"""Tests for resonance-environment model surfaces added in T2.

Covers:
- AffinityInteraction.consequence_pool nullable FK to ConsequencePool
- ResonanceAlignmentBoonTier model:
  - Valid row against an ALIGNED interaction saves
  - clean() raises ValidationError when interaction valence is not ALIGNED
  - UniqueConstraint on (affinity_interaction, min_magnitude) raises IntegrityError
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.utils import IntegrityError
from django.test import TestCase

from actions.factories import ConsequencePoolFactory
from world.conditions.factories import ConditionTemplateFactory
from world.magic.constants import AffinityInteractionKind, ResonanceValence
from world.magic.factories import AffinityInteractionFactory
from world.magic.models.resonance_environment import (
    AffinityInteraction,
    ResonanceAlignmentBoonTier,
)


class AffinityInteractionConsequencePoolTests(TestCase):
    """consequence_pool nullable FK on AffinityInteraction."""

    def test_consequence_pool_defaults_to_null(self) -> None:
        row = AffinityInteractionFactory()
        self.assertIsNone(row.consequence_pool_id)

    def test_consequence_pool_can_be_set_to_a_pool(self) -> None:
        pool = ConsequencePoolFactory()
        row = AffinityInteractionFactory(consequence_pool=pool)
        row.refresh_from_db()
        self.assertEqual(row.consequence_pool_id, pool.pk)

    def test_consequence_pool_related_name_reaches_interaction(self) -> None:
        pool = ConsequencePoolFactory()
        row = AffinityInteractionFactory(consequence_pool=pool)
        self.assertIn(row, pool.resonance_interactions.all())


class ResonanceAlignmentBoonTierSaveTests(TestCase):
    """Valid ResonanceAlignmentBoonTier rows save without error."""

    def test_boon_tier_against_aligned_interaction_saves(self) -> None:
        interaction = AffinityInteractionFactory(valence=ResonanceValence.ALIGNED)
        template = ConditionTemplateFactory()
        tier = ResonanceAlignmentBoonTier(
            affinity_interaction=interaction,
            min_magnitude=10,
            condition_template=template,
        )
        tier.full_clean()
        tier.save()
        self.assertIsNotNone(tier.pk)

    def test_boon_tier_str_contains_min_magnitude(self) -> None:
        interaction = AffinityInteractionFactory(valence=ResonanceValence.ALIGNED)
        template = ConditionTemplateFactory()
        tier = ResonanceAlignmentBoonTier(
            affinity_interaction=interaction,
            min_magnitude=42,
            condition_template=template,
        )
        tier.save()
        self.assertIn("42", str(tier))


class ResonanceAlignmentBoonTierCleanTests(TestCase):
    """clean() enforces ALIGNED valence on the parent interaction."""

    def test_clean_raises_on_opposed_interaction(self) -> None:
        interaction = AffinityInteractionFactory(
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REJECT,
        )
        template = ConditionTemplateFactory()
        tier = ResonanceAlignmentBoonTier(
            affinity_interaction=interaction,
            min_magnitude=10,
            condition_template=template,
        )
        with self.assertRaises(ValidationError):
            tier.full_clean()

    def test_clean_raises_on_corrupt_kind_opposed_interaction(self) -> None:
        """clean() must reject CORRUPT-kind interactions (OPPOSED valence) — a
        meaningfully distinct assertion from the REJECT-kind test above."""
        interaction = AffinityInteractionFactory(
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.CORRUPT,
        )
        template = ConditionTemplateFactory()
        tier = ResonanceAlignmentBoonTier(
            affinity_interaction=interaction,
            min_magnitude=20,
            condition_template=template,
        )
        with self.assertRaises(ValidationError):
            tier.full_clean()


class ResonanceAlignmentBoonTierUniqueConstraintTests(TestCase):
    """UniqueConstraint on (affinity_interaction, min_magnitude)."""

    def test_duplicate_threshold_raises_integrity_error(self) -> None:
        interaction = AffinityInteractionFactory(valence=ResonanceValence.ALIGNED)
        template_a = ConditionTemplateFactory()
        template_b = ConditionTemplateFactory()
        ResonanceAlignmentBoonTier.objects.create(
            affinity_interaction=interaction,
            min_magnitude=10,
            condition_template=template_a,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ResonanceAlignmentBoonTier.objects.create(
                    affinity_interaction=interaction,
                    min_magnitude=10,
                    condition_template=template_b,
                )

    def test_same_threshold_different_interaction_is_allowed(self) -> None:
        interaction_a = AffinityInteractionFactory(valence=ResonanceValence.ALIGNED)
        interaction_b = AffinityInteractionFactory(valence=ResonanceValence.ALIGNED)
        template = ConditionTemplateFactory()
        tier_a = ResonanceAlignmentBoonTier.objects.create(
            affinity_interaction=interaction_a,
            min_magnitude=10,
            condition_template=template,
        )
        tier_b = ResonanceAlignmentBoonTier.objects.create(
            affinity_interaction=interaction_b,
            min_magnitude=10,
            condition_template=template,
        )
        self.assertNotEqual(tier_a.pk, tier_b.pk)


# ---------------------------------------------------------------------------
# T3: cached accessors
# ---------------------------------------------------------------------------


class AffinityInteractionManagerInteractionForTests(TestCase):
    """AffinityInteraction.objects.interaction_for() cached lookup."""

    def setUp(self) -> None:
        AffinityInteraction.objects.clear_cache()

    def test_returns_correct_row_for_known_pair(self) -> None:
        row = AffinityInteractionFactory(valence=ResonanceValence.ALIGNED)
        result = AffinityInteraction.objects.interaction_for(
            row.source_affinity, row.environment_affinity
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, row.pk)

    def test_returns_none_for_unknown_pair(self) -> None:
        from world.magic.factories import AffinityFactory

        src = AffinityFactory()
        env = AffinityFactory()
        # No row created — should return None
        result = AffinityInteraction.objects.interaction_for(src, env)
        self.assertIsNone(result)

    def test_second_call_issues_zero_queries(self) -> None:
        row = AffinityInteractionFactory(valence=ResonanceValence.ALIGNED)
        # Warm-up: populate cache
        AffinityInteraction.objects.interaction_for(row.source_affinity, row.environment_affinity)
        # Second call must be zero queries
        with self.assertNumQueries(0):
            result = AffinityInteraction.objects.interaction_for(
                row.source_affinity, row.environment_affinity
            )
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, row.pk)

    def test_none_result_is_also_cached(self) -> None:
        from world.magic.factories import AffinityFactory

        src = AffinityFactory()
        env = AffinityFactory()
        # Warm-up on a missing pair
        AffinityInteraction.objects.interaction_for(src, env)
        with self.assertNumQueries(0):
            result = AffinityInteraction.objects.interaction_for(src, env)
        self.assertIsNone(result)

    def test_clear_cache_makes_new_row_visible(self) -> None:
        """Documents the test-isolation mechanism: clear → seed → visible."""
        row = AffinityInteractionFactory(valence=ResonanceValence.ALIGNED)
        # Populate cache with miss for this pair
        AffinityInteraction.objects.clear_cache()
        AffinityInteraction.objects.interaction_for(row.source_affinity, row.environment_affinity)
        # Clear and rebuild
        AffinityInteraction.objects.clear_cache()
        result = AffinityInteraction.objects.interaction_for(
            row.source_affinity, row.environment_affinity
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, row.pk)


class AffinityInteractionCachedAlignmentBoonTiersTests(TestCase):
    """AffinityInteraction.cached_alignment_boon_tiers cached_property."""

    def test_returns_list_of_tiers(self) -> None:
        interaction = AffinityInteractionFactory(valence=ResonanceValence.ALIGNED)
        template = ConditionTemplateFactory()
        ResonanceAlignmentBoonTier.objects.create(
            affinity_interaction=interaction,
            min_magnitude=10,
            condition_template=template,
        )
        tiers = interaction.cached_alignment_boon_tiers
        self.assertIsInstance(tiers, list)
        self.assertEqual(len(tiers), 1)
        self.assertEqual(tiers[0].affinity_interaction_id, interaction.pk)

    def test_second_access_issues_zero_queries(self) -> None:
        interaction = AffinityInteractionFactory(valence=ResonanceValence.ALIGNED)
        template = ConditionTemplateFactory()
        ResonanceAlignmentBoonTier.objects.create(
            affinity_interaction=interaction,
            min_magnitude=10,
            condition_template=template,
        )
        # Warm-up
        _ = interaction.cached_alignment_boon_tiers
        with self.assertNumQueries(0):
            tiers = interaction.cached_alignment_boon_tiers
        self.assertEqual(len(tiers), 1)

    def test_empty_list_when_no_tiers(self) -> None:
        interaction = AffinityInteractionFactory(valence=ResonanceValence.ALIGNED)
        tiers = interaction.cached_alignment_boon_tiers
        self.assertIsInstance(tiers, list)
        self.assertEqual(len(tiers), 0)

    def test_tiers_ordered_by_min_magnitude_ascending(self) -> None:
        """cached_alignment_boon_tiers returns tiers in ascending min_magnitude order.

        Rows are inserted out of order (30, 10, 20) so the test fails if the
        queryset is unordered (i.e. returns insertion/PK order).
        """
        interaction = AffinityInteractionFactory(valence=ResonanceValence.ALIGNED)
        template_a = ConditionTemplateFactory()
        template_b = ConditionTemplateFactory()
        template_c = ConditionTemplateFactory()
        # Insert deliberately out of ascending order
        ResonanceAlignmentBoonTier.objects.create(
            affinity_interaction=interaction,
            min_magnitude=30,
            condition_template=template_a,
        )
        ResonanceAlignmentBoonTier.objects.create(
            affinity_interaction=interaction,
            min_magnitude=10,
            condition_template=template_b,
        )
        ResonanceAlignmentBoonTier.objects.create(
            affinity_interaction=interaction,
            min_magnitude=20,
            condition_template=template_c,
        )
        tiers = interaction.cached_alignment_boon_tiers
        self.assertEqual(len(tiers), 3)
        self.assertEqual(
            [t.min_magnitude for t in tiers],
            [10, 20, 30],
            "cached_alignment_boon_tiers must be ordered ascending by min_magnitude",
        )


class ResonanceAlignmentBoonTierManagerBoonConditionTemplatesTests(TestCase):
    """ResonanceAlignmentBoonTier.objects.boon_condition_templates() cached set."""

    def setUp(self) -> None:
        ResonanceAlignmentBoonTier.objects.clear_cache()

    def test_returns_set_of_distinct_condition_templates(self) -> None:
        interaction = AffinityInteractionFactory(valence=ResonanceValence.ALIGNED)
        template_a = ConditionTemplateFactory()
        template_b = ConditionTemplateFactory()
        ResonanceAlignmentBoonTier.objects.create(
            affinity_interaction=interaction,
            min_magnitude=10,
            condition_template=template_a,
        )
        ResonanceAlignmentBoonTier.objects.create(
            affinity_interaction=interaction,
            min_magnitude=20,
            condition_template=template_b,
        )
        templates = ResonanceAlignmentBoonTier.objects.boon_condition_templates()
        self.assertIn(template_a, templates)
        self.assertIn(template_b, templates)

    def test_same_template_referenced_twice_appears_once(self) -> None:
        interaction_a = AffinityInteractionFactory(valence=ResonanceValence.ALIGNED)
        interaction_b = AffinityInteractionFactory(valence=ResonanceValence.ALIGNED)
        template = ConditionTemplateFactory()
        ResonanceAlignmentBoonTier.objects.create(
            affinity_interaction=interaction_a,
            min_magnitude=10,
            condition_template=template,
        )
        ResonanceAlignmentBoonTier.objects.create(
            affinity_interaction=interaction_b,
            min_magnitude=10,
            condition_template=template,
        )
        templates = ResonanceAlignmentBoonTier.objects.boon_condition_templates()
        # frozenset/set — template appears exactly once
        self.assertEqual(len([t for t in templates if t.pk == template.pk]), 1)

    def test_second_call_issues_zero_queries(self) -> None:
        interaction = AffinityInteractionFactory(valence=ResonanceValence.ALIGNED)
        template = ConditionTemplateFactory()
        ResonanceAlignmentBoonTier.objects.create(
            affinity_interaction=interaction,
            min_magnitude=10,
            condition_template=template,
        )
        # Warm-up
        ResonanceAlignmentBoonTier.objects.boon_condition_templates()
        with self.assertNumQueries(0):
            ResonanceAlignmentBoonTier.objects.boon_condition_templates()

    def test_empty_set_when_no_tiers(self) -> None:
        templates = ResonanceAlignmentBoonTier.objects.boon_condition_templates()
        self.assertEqual(len(templates), 0)

    def test_clear_cache_makes_new_template_visible(self) -> None:
        """Documents the test-isolation mechanism: clear → seed → visible."""
        # First populate cache while empty
        ResonanceAlignmentBoonTier.objects.boon_condition_templates()
        # Now add a tier after cache was primed
        interaction = AffinityInteractionFactory(valence=ResonanceValence.ALIGNED)
        template = ConditionTemplateFactory()
        ResonanceAlignmentBoonTier.objects.create(
            affinity_interaction=interaction,
            min_magnitude=10,
            condition_template=template,
        )
        # Without clearing, would still see empty set; after clear, sees the new row
        ResonanceAlignmentBoonTier.objects.clear_cache()
        templates = ResonanceAlignmentBoonTier.objects.boon_condition_templates()
        self.assertIn(template, templates)
