"""Tests for relationships models."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.mechanics.factories import ModifierTargetFactory
from world.relationships.constants import TrackSign
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipConditionFactory,
    RelationshipTierFactory,
    RelationshipTrackFactory,
    RelationshipTrackProgressFactory,
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
        modifier1 = ModifierTargetFactory(name="Allure")
        modifier2 = ModifierTargetFactory(name="Intimidation")

        condition.gates_modifiers.add(modifier1, modifier2)

        self.assertEqual(condition.gates_modifiers.count(), 2)
        self.assertIn(modifier1, condition.gates_modifiers.all())
        self.assertIn(modifier2, condition.gates_modifiers.all())

    def test_gates_modifiers_reverse_relationship(self):
        """Test the reverse relationship gated_by_conditions."""
        condition = RelationshipConditionFactory(name="ReverseTestCondition")
        modifier = ModifierTargetFactory(name="ReverseModifier")

        condition.gates_modifiers.add(modifier)

        self.assertIn(condition, modifier.gated_by_conditions.all())


class CharacterRelationshipTests(TestCase):
    """Test CharacterRelationship model."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data for all tests."""
        cls.sheet1 = CharacterSheetFactory()
        cls.sheet2 = CharacterSheetFactory()

    def test_relationship_str(self):
        """Test __str__ returns source -> target format."""
        relationship = CharacterRelationshipFactory(source=self.sheet1, target=self.sheet2)
        expected = f"{self.sheet1} -> {self.sheet2}"
        self.assertEqual(str(relationship), expected)

    def test_unique_together_constraint(self):
        """Test that source/target pairs must be unique."""
        CharacterRelationshipFactory(source=self.sheet1, target=self.sheet2)
        with self.assertRaises(IntegrityError):
            CharacterRelationship.objects.create(source=self.sheet1, target=self.sheet2)

    def test_same_source_different_targets_allowed(self):
        """Test that the same source can have relationships to multiple targets."""
        sheet3 = CharacterSheetFactory()
        rel1 = CharacterRelationshipFactory(source=self.sheet1, target=self.sheet2)
        rel2 = CharacterRelationshipFactory(source=self.sheet1, target=sheet3)
        self.assertIsNotNone(rel1.id)
        self.assertIsNotNone(rel2.id)

    def test_defaults(self):
        """Test default field values on a new relationship."""
        relationship = CharacterRelationship.objects.create(source=self.sheet1, target=self.sheet2)
        self.assertTrue(relationship.is_active)
        self.assertTrue(relationship.is_pending)
        self.assertFalse(relationship.is_deceitful)
        self.assertEqual(relationship.updates_this_week, 0)
        self.assertEqual(relationship.changes_this_week, 0)

    def test_clean_prevents_self_relationship(self):
        """Test that clean() prevents a character from relating to themselves."""
        relationship = CharacterRelationship(source=self.sheet1, target=self.sheet1)
        with self.assertRaises(ValidationError):
            relationship.clean()

    def test_conditions_m2m(self):
        """Test that conditions M2M relationship works."""
        relationship = CharacterRelationshipFactory(source=self.sheet1, target=self.sheet2)
        cond1 = RelationshipConditionFactory(name="Trusts")
        cond2 = RelationshipConditionFactory(name="Respects")

        relationship.conditions.add(cond1, cond2)

        self.assertEqual(relationship.conditions.count(), 2)
        self.assertIn(cond1, relationship.conditions.all())
        self.assertIn(cond2, relationship.conditions.all())

    def test_conditions_reverse_relationship(self):
        """Test the reverse relationship character_relationships."""
        relationship = CharacterRelationshipFactory(source=self.sheet1, target=self.sheet2)
        condition = RelationshipConditionFactory(name="ReverseRelCondition")

        relationship.conditions.add(condition)

        self.assertIn(relationship, condition.character_relationships.all())

    def test_created_at_auto_set(self):
        """Test that created_at is automatically set."""
        relationship = CharacterRelationshipFactory(source=self.sheet1, target=self.sheet2)
        self.assertIsNotNone(relationship.created_at)

    def test_updated_at_auto_set(self):
        """Test that updated_at is automatically set."""
        relationship = CharacterRelationshipFactory(source=self.sheet1, target=self.sheet2)
        self.assertIsNotNone(relationship.updated_at)

    def test_absolute_value(self):
        """Test absolute_value property sums all track points."""
        relationship = CharacterRelationshipFactory(source=self.sheet1, target=self.sheet2)
        track1 = RelationshipTrackFactory(name="Trust", sign=TrackSign.POSITIVE)
        track2 = RelationshipTrackFactory(name="Fear", sign=TrackSign.NEGATIVE)
        RelationshipTrackProgressFactory(relationship=relationship, track=track1, points=30)
        RelationshipTrackProgressFactory(relationship=relationship, track=track2, points=20)

        self.assertEqual(relationship.absolute_value, 50)

    def test_affection(self):
        """Test affection property: positive tracks add, negative subtract."""
        relationship = CharacterRelationshipFactory(source=self.sheet1, target=self.sheet2)
        track1 = RelationshipTrackFactory(name="Respect", sign=TrackSign.POSITIVE)
        track2 = RelationshipTrackFactory(name="Hatred", sign=TrackSign.NEGATIVE)
        RelationshipTrackProgressFactory(relationship=relationship, track=track1, points=30)
        RelationshipTrackProgressFactory(relationship=relationship, track=track2, points=20)

        self.assertEqual(relationship.affection, 10)

    def test_factory_creates_valid_instance(self):
        """Test CharacterRelationshipFactory creates valid instance."""
        relationship = CharacterRelationshipFactory()
        self.assertIsNotNone(relationship.source)
        self.assertIsNotNone(relationship.target)


class RelationshipTrackProgressTests(TestCase):
    """Test RelationshipTrackProgress model."""

    def test_current_tier_returns_highest_qualifying(self):
        """Test current_tier returns the highest tier where threshold <= points."""
        track = RelationshipTrackFactory(name="TierTestTrack")
        RelationshipTierFactory(track=track, name="Low", tier_number=0, point_threshold=0)
        tier1 = RelationshipTierFactory(track=track, name="Mid", tier_number=1, point_threshold=10)
        RelationshipTierFactory(track=track, name="High", tier_number=2, point_threshold=50)

        progress = RelationshipTrackProgressFactory(track=track, points=25)
        self.assertEqual(progress.current_tier, tier1)

    def test_current_tier_returns_none_below_all_thresholds(self):
        """Test current_tier returns None when below all thresholds."""
        track = RelationshipTrackFactory(name="NoneTestTrack")
        RelationshipTierFactory(track=track, name="First", tier_number=1, point_threshold=10)

        progress = RelationshipTrackProgressFactory(track=track, points=5)
        self.assertIsNone(progress.current_tier)
