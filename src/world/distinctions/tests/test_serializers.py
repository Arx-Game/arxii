"""Tests for distinctions serializers."""

from django.test import TestCase

from world.codex.factories import CodexEntryFactory
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.distinctions.serializers import (
    DistinctionDetailSerializer,
    DistinctionEffectSerializer,
)
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory


class DistinctionEffectSerializerTest(TestCase):
    """Tests for DistinctionEffectSerializer."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.modifier_target = ModifierTargetFactory(name="Allure")
        cls.distinction = DistinctionFactory(name="Attractive")

    def test_serializer_includes_all_expected_fields(self):
        """Serializer includes all expected fields (no codex_entry_id — removed in #2477)."""
        effect = DistinctionEffectFactory(
            distinction=self.distinction,
            target=self.modifier_target,
            value_per_rank=3,
            description="Increases Allure",
        )

        serializer = DistinctionEffectSerializer(effect)
        data = serializer.data

        self.assertIn("id", data)
        self.assertIn("target", data)
        self.assertIn("target_name", data)
        self.assertIn("category", data)
        self.assertIn("value_per_rank", data)
        self.assertIn("scaling_values", data)
        self.assertIn("description", data)
        self.assertNotIn("codex_entry_id", data)
        self.assertEqual(data["target_name"], "Allure")


class DistinctionDetailSerializerTest(TestCase):
    """Tests for DistinctionDetailSerializer."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.modifier_target = ModifierTargetFactory(name="Charm")
        cls.distinction = DistinctionFactory(name="Charming")

    def test_effects_no_longer_include_codex_entry_id(self):
        """DistinctionEffectSerializer no longer includes codex_entry_id.

        Per-effect codex was removed in #2477; distinction-level lore now
        comes from DistinctionCodexGrant via codex_entry_ids on the list
        serializer.
        """
        DistinctionEffectFactory(
            distinction=self.distinction,
            target=self.modifier_target,
        )

        serializer = DistinctionDetailSerializer(self.distinction)
        data = serializer.data

        self.assertEqual(len(data["effects"]), 1)
        self.assertNotIn("codex_entry_id", data["effects"][0])

    def test_detail_includes_codex_entry_ids_from_grant_table(self):
        """DistinctionDetailSerializer surfaces codex_entry_ids via DistinctionCodexGrant."""
        from world.codex.models import DistinctionCodexGrant

        entry = CodexEntryFactory(name="Distinction Lore")
        DistinctionCodexGrant.objects.create(distinction=self.distinction, entry=entry)
        self.distinction.cached_codex_grants  # noqa: B018

        serializer = DistinctionDetailSerializer(self.distinction)
        data = serializer.data

        self.assertIn("codex_entry_ids", data)
        self.assertEqual(data["codex_entry_ids"], [entry.id])


class EffectsSummaryTextTests(TestCase):
    """Test dynamic effect text generation in DistinctionListSerializer."""

    @classmethod
    def setUpTestData(cls):
        cls.stat_category = ModifierCategoryFactory(name="stat")
        cls.resonance_category = ModifierCategoryFactory(name="resonance")
        cls.goal_pct_category = ModifierCategoryFactory(name="goal_percent")
        cls.action_category = ModifierCategoryFactory(name="action_points")

    def _get_effect_text(self, effect):
        """Helper to get the generated text for an effect."""
        from world.distinctions.serializers import (
            DistinctionListSerializer,
        )

        serializer = DistinctionListSerializer(effect.distinction)
        summary = serializer.get_effects_summary(effect.distinction)
        return summary[0]["text"] if summary else None

    def test_stat_effect_divides_by_10(self):
        """Stat effects should divide value_per_rank by 10."""
        target = ModifierTargetFactory(name="Strength", category=self.stat_category)
        effect = DistinctionEffectFactory(target=target, value_per_rank=10, description="")
        text = self._get_effect_text(effect)
        assert text == "+1 Strength"

    def test_negative_stat_effect(self):
        """Negative stat effects should show minus sign."""
        target = ModifierTargetFactory(name="Willpower", category=self.stat_category)
        effect = DistinctionEffectFactory(target=target, value_per_rank=-10, description="")
        text = self._get_effect_text(effect)
        assert text == "-1 Willpower"

    def test_resonance_effect_raw_value(self):
        """Resonance effects should use raw value."""
        target = ModifierTargetFactory(name="Praedari", category=self.resonance_category)
        effect = DistinctionEffectFactory(target=target, value_per_rank=5, description="")
        text = self._get_effect_text(effect)
        assert text == "+5 Praedari"

    def test_percentage_effect(self):
        """Percentage category effects should append %."""
        target = ModifierTargetFactory(name="all", category=self.goal_pct_category)
        effect = DistinctionEffectFactory(target=target, value_per_rank=50, description="")
        text = self._get_effect_text(effect)
        assert text == "+50% all"

    def test_multi_rank_does_not_append_per_rank(self):
        """Multi-rank distinctions should NOT append 'per rank' — UI shows concrete values."""
        target = ModifierTargetFactory(name="Praedari", category=self.resonance_category)
        distinction = DistinctionFactory(max_rank=3)
        effect = DistinctionEffectFactory(
            distinction=distinction,
            target=target,
            value_per_rank=5,
            description="",
        )
        text = self._get_effect_text(effect)
        assert text == "+5 Praedari"

    def test_scaling_values_slash_separated(self):
        """Non-linear scaling should show slash-separated values."""
        target = ModifierTargetFactory(name="needs", category=self.goal_pct_category)
        distinction = DistinctionFactory(max_rank=3)
        effect = DistinctionEffectFactory(
            distinction=distinction,
            target=target,
            value_per_rank=None,
            scaling_values=[100, 200, 300],
            description="",
        )
        text = self._get_effect_text(effect)
        assert text == "+100/200/300% needs"

    def test_scaling_values_with_floats_display_as_ints(self):
        """Scaling values stored as floats in JSON should display as integers."""
        target = ModifierTargetFactory(name="Strength", category=self.stat_category)
        distinction = DistinctionFactory(max_rank=3)
        effect = DistinctionEffectFactory(
            distinction=distinction,
            target=target,
            value_per_rank=None,
            scaling_values=[10.0, 20.0, 30.0],
            description="",
        )
        text = self._get_effect_text(effect)
        assert text == "+1/2/3 Strength"

    def test_non_stat_scaling_values_with_floats_display_as_ints(self):
        """Non-stat scaling values stored as floats should display as integers."""
        target = ModifierTargetFactory(name="Praedari", category=self.resonance_category)
        distinction = DistinctionFactory(max_rank=3)
        effect = DistinctionEffectFactory(
            distinction=distinction,
            target=target,
            value_per_rank=None,
            scaling_values=[5.0, 10.0, 15.0],
            description="",
        )
        text = self._get_effect_text(effect)
        assert text == "+5/10/15 Praedari"

    def test_description_override(self):
        """Manual description should override auto-generation."""
        target = ModifierTargetFactory(name="Strength", category=self.stat_category)
        effect = DistinctionEffectFactory(
            target=target,
            value_per_rank=10,
            description="Grants superhuman strength",
        )
        text = self._get_effect_text(effect)
        assert text == "Grants superhuman strength"
