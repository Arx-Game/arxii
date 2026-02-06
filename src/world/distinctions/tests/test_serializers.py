"""Tests for distinctions serializers."""

from django.test import TestCase

from world.codex.factories import CodexEntryFactory
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.distinctions.serializers import (
    DistinctionDetailSerializer,
    DistinctionEffectSerializer,
)
from world.mechanics.factories import ModifierTypeFactory


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
