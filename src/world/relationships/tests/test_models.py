"""Tests for relationships models."""

from django.db import IntegrityError
from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.mechanics.factories import ModifierTypeFactory
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipConditionFactory,
)
from world.relationships.models import CharacterRelationship, RelationshipCondition


class RelationshipConditionTests(TestCase):
    """Test RelationshipCondition model."""

    def test_condition_str(self):
        """Test __str__ returns name."""
        condition = RelationshipConditionFactory(name="Attracted To")
        self.assertEqual(str(condition), "Attracted To")

    def test_condition_unique_name(self):
        """Test that condition names must be unique."""
        RelationshipConditionFactory(name="UniqueName")
        with self.assertRaises(IntegrityError):
            RelationshipCondition.objects.create(name="UniqueName", display_order=99)

    def test_condition_ordering(self):
        """Test conditions order by display_order then name."""
        cond_b = RelationshipConditionFactory(name="ConditionB", display_order=102)
        cond_a = RelationshipConditionFactory(name="ConditionA", display_order=101)
        conditions = list(
            RelationshipCondition.objects.filter(name__in=["ConditionA", "ConditionB"])
        )
        self.assertEqual(conditions, [cond_a, cond_b])

    def test_condition_ordering_by_name_when_same_display_order(self):
        """Test conditions order by name when display_order is the same."""
        cond_z = RelationshipConditionFactory(name="ZCondition", display_order=50)
        cond_a = RelationshipConditionFactory(name="ACondition", display_order=50)
        conditions = list(
            RelationshipCondition.objects.filter(name__in=["ZCondition", "ACondition"])
        )
        self.assertEqual(conditions, [cond_a, cond_z])

    def test_gates_modifiers_m2m(self):
        """Test that gates_modifiers M2M relationship works."""
        condition = RelationshipConditionFactory(name="TestGatesCondition")
        modifier1 = ModifierTypeFactory(name="Allure")
        modifier2 = ModifierTypeFactory(name="Intimidation")

        condition.gates_modifiers.add(modifier1, modifier2)

        self.assertEqual(condition.gates_modifiers.count(), 2)
        self.assertIn(modifier1, condition.gates_modifiers.all())
        self.assertIn(modifier2, condition.gates_modifiers.all())

    def test_gates_modifiers_reverse_relationship(self):
        """Test the reverse relationship gated_by_conditions."""
        condition = RelationshipConditionFactory(name="ReverseTestCondition")
        modifier = ModifierTypeFactory(name="ReverseModifier")

        condition.gates_modifiers.add(modifier)

        self.assertIn(condition, modifier.gated_by_conditions.all())


class CharacterRelationshipTests(TestCase):
    """Test CharacterRelationship model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all tests."""
        cls.character1 = CharacterFactory()
        cls.character2 = CharacterFactory()

    def test_relationship_str(self):
        """Test __str__ returns source -> target format."""
        relationship = CharacterRelationshipFactory(source=self.character1, target=self.character2)
        expected = f"{self.character1} -> {self.character2}"
        self.assertEqual(str(relationship), expected)

    def test_unique_together_constraint(self):
        """Test that source/target pairs must be unique."""
        CharacterRelationshipFactory(source=self.character1, target=self.character2)
        with self.assertRaises(IntegrityError):
            CharacterRelationship.objects.create(
                source=self.character1, target=self.character2, reputation=50
            )

    def test_same_source_different_targets_allowed(self):
        """Test that the same source can have relationships to multiple targets."""
        character3 = CharacterFactory()
        rel1 = CharacterRelationshipFactory(source=self.character1, target=self.character2)
        rel2 = CharacterRelationshipFactory(source=self.character1, target=character3)
        self.assertIsNotNone(rel1.id)
        self.assertIsNotNone(rel2.id)

    def test_reputation_default(self):
        """Test that reputation defaults to 0."""
        relationship = CharacterRelationship.objects.create(
            source=self.character1, target=self.character2
        )
        self.assertEqual(relationship.reputation, 0)

    def test_reputation_can_be_set(self):
        """Test that reputation can be set to various values."""
        relationship = CharacterRelationshipFactory(
            source=self.character1, target=self.character2, reputation=500
        )
        self.assertEqual(relationship.reputation, 500)

        # Test negative reputation
        character3 = CharacterFactory()
        negative_rel = CharacterRelationshipFactory(
            source=self.character1, target=character3, reputation=-500
        )
        self.assertEqual(negative_rel.reputation, -500)

    def test_conditions_m2m(self):
        """Test that conditions M2M relationship works."""
        relationship = CharacterRelationshipFactory(source=self.character1, target=self.character2)
        cond1 = RelationshipConditionFactory(name="Trusts")
        cond2 = RelationshipConditionFactory(name="Respects")

        relationship.conditions.add(cond1, cond2)

        self.assertEqual(relationship.conditions.count(), 2)
        self.assertIn(cond1, relationship.conditions.all())
        self.assertIn(cond2, relationship.conditions.all())

    def test_conditions_reverse_relationship(self):
        """Test the reverse relationship character_relationships."""
        relationship = CharacterRelationshipFactory(source=self.character1, target=self.character2)
        condition = RelationshipConditionFactory(name="ReverseRelCondition")

        relationship.conditions.add(condition)

        self.assertIn(relationship, condition.character_relationships.all())

    def test_created_at_auto_set(self):
        """Test that created_at is automatically set."""
        relationship = CharacterRelationshipFactory(source=self.character1, target=self.character2)
        self.assertIsNotNone(relationship.created_at)

    def test_updated_at_auto_set(self):
        """Test that updated_at is automatically set."""
        relationship = CharacterRelationshipFactory(source=self.character1, target=self.character2)
        self.assertIsNotNone(relationship.updated_at)

    def test_updated_at_changes_on_save(self):
        """Test that updated_at changes when model is saved."""
        relationship = CharacterRelationshipFactory(source=self.character1, target=self.character2)
        original_updated = relationship.updated_at

        relationship.reputation = 100
        relationship.save()
        relationship.refresh_from_db()

        self.assertGreater(relationship.updated_at, original_updated)

    def test_factory_creates_valid_instance(self):
        """Test CharacterRelationshipFactory creates valid instance."""
        relationship = CharacterRelationshipFactory()
        self.assertIsNotNone(relationship.source)
        self.assertIsNotNone(relationship.target)
        self.assertEqual(relationship.reputation, 0)
