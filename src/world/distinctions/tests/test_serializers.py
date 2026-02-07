"""Tests for distinctions serializers."""

from django.test import TestCase

from world.codex.factories import CodexEntryFactory
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.distinctions.serializers import (
    DistinctionDetailSerializer,
    DistinctionEffectSerializer,
)
from world.mechanics.factories import ModifierCategoryFactory, ModifierTypeFactory


class DistinctionEffectSerializerTest(TestCase):
    """Tests for DistinctionEffectSerializer."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.modifier_type = ModifierTypeFactory(name="Allure")
        cls.distinction = DistinctionFactory(name="Attractive")

    def test_codex_entry_id_returns_id_when_linked(self):
        """codex_entry_id returns the entry ID when modifier type has a Codex entry."""
        # Create a codex entry linked to this modifier type
        codex_entry = CodexEntryFactory(
            name="Allure Codex Entry",
            modifier_type=self.modifier_type,
        )
        effect = DistinctionEffectFactory(
            distinction=self.distinction,
            target=self.modifier_type,
        )

        serializer = DistinctionEffectSerializer(effect)
        data = serializer.data

        self.assertEqual(data["codex_entry_id"], codex_entry.id)

    def test_codex_entry_id_returns_none_when_not_linked(self):
        """codex_entry_id returns None when modifier type has no Codex entry."""
        effect = DistinctionEffectFactory(
            distinction=self.distinction,
            target=self.modifier_type,
        )

        serializer = DistinctionEffectSerializer(effect)
        data = serializer.data

        self.assertIsNone(data["codex_entry_id"])

    def test_serializer_includes_all_expected_fields(self):
        """Serializer includes all expected fields."""
        effect = DistinctionEffectFactory(
            distinction=self.distinction,
            target=self.modifier_type,
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
        self.assertIn("codex_entry_id", data)
        self.assertEqual(data["target_name"], "Allure")


class DistinctionDetailSerializerTest(TestCase):
    """Tests for DistinctionDetailSerializer."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.modifier_type = ModifierTypeFactory(name="Charm")
        cls.distinction = DistinctionFactory(name="Charming")

    def test_effects_include_codex_entry_id(self):
        """Effects in detail serializer include codex_entry_id."""
        codex_entry = CodexEntryFactory(
            name="Charm Codex Entry",
            modifier_type=self.modifier_type,
        )
        DistinctionEffectFactory(
            distinction=self.distinction,
            target=self.modifier_type,
        )

        serializer = DistinctionDetailSerializer(self.distinction)
        data = serializer.data

        self.assertEqual(len(data["effects"]), 1)
        self.assertEqual(data["effects"][0]["codex_entry_id"], codex_entry.id)


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
        target = ModifierTypeFactory(name="Strength", category=self.stat_category)
        effect = DistinctionEffectFactory(target=target, value_per_rank=10, description="")
        text = self._get_effect_text(effect)
        assert text == "+1 Strength"

    def test_negative_stat_effect(self):
        """Negative stat effects should show minus sign."""
        target = ModifierTypeFactory(name="Willpower", category=self.stat_category)
        effect = DistinctionEffectFactory(target=target, value_per_rank=-10, description="")
        text = self._get_effect_text(effect)
        assert text == "-1 Willpower"

    def test_resonance_effect_raw_value(self):
        """Resonance effects should use raw value."""
        target = ModifierTypeFactory(name="Praedari", category=self.resonance_category)
        effect = DistinctionEffectFactory(target=target, value_per_rank=5, description="")
        text = self._get_effect_text(effect)
        assert text == "+5 Praedari"

    def test_percentage_effect(self):
        """Percentage category effects should append %."""
        target = ModifierTypeFactory(name="all", category=self.goal_pct_category)
        effect = DistinctionEffectFactory(target=target, value_per_rank=50, description="")
        text = self._get_effect_text(effect)
        assert text == "+50% all"

    def test_multi_rank_appends_per_rank(self):
        """Multi-rank distinctions should append 'per rank'."""
        target = ModifierTypeFactory(name="Praedari", category=self.resonance_category)
        distinction = DistinctionFactory(max_rank=3)
        effect = DistinctionEffectFactory(
            distinction=distinction,
            target=target,
            value_per_rank=5,
            description="",
        )
        text = self._get_effect_text(effect)
        assert text == "+5 Praedari per rank"

    def test_scaling_values_slash_separated(self):
        """Non-linear scaling should show slash-separated values."""
        target = ModifierTypeFactory(name="needs", category=self.goal_pct_category)
        distinction = DistinctionFactory(max_rank=3)
        effect = DistinctionEffectFactory(
            distinction=distinction,
            target=target,
            value_per_rank=None,
            scaling_values=[100, 200, 300],
            description="",
        )
        text = self._get_effect_text(effect)
        assert text == "+100/200/300% needs per rank"

    def test_scaling_values_with_floats_display_as_ints(self):
        """Scaling values stored as floats in JSON should display as integers."""
        target = ModifierTypeFactory(name="Strength", category=self.stat_category)
        distinction = DistinctionFactory(max_rank=3)
        effect = DistinctionEffectFactory(
            distinction=distinction,
            target=target,
            value_per_rank=None,
            scaling_values=[10.0, 20.0, 30.0],
            description="",
        )
        text = self._get_effect_text(effect)
        assert text == "+1/2/3 Strength per rank"

    def test_non_stat_scaling_values_with_floats_display_as_ints(self):
        """Non-stat scaling values stored as floats should display as integers."""
        target = ModifierTypeFactory(name="Praedari", category=self.resonance_category)
        distinction = DistinctionFactory(max_rank=3)
        effect = DistinctionEffectFactory(
            distinction=distinction,
            target=target,
            value_per_rank=None,
            scaling_values=[5.0, 10.0, 15.0],
            description="",
        )
        text = self._get_effect_text(effect)
        assert text == "+5/10/15 Praedari per rank"

    def test_description_override(self):
        """Manual description should override auto-generation."""
        target = ModifierTypeFactory(name="Strength", category=self.stat_category)
        effect = DistinctionEffectFactory(
            target=target,
            value_per_rank=10,
            description="Grants superhuman strength",
        )
        text = self._get_effect_text(effect)
        assert text == "Grants superhuman strength"
