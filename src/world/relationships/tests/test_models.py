"""Tests for relationships models."""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.mechanics.factories import ModifierTargetFactory
from world.relationships.constants import DECAY_DAYS, ReferenceMode, TrackSign
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipConditionFactory,
    RelationshipTierFactory,
    RelationshipTrackFactory,
    RelationshipTrackProgressFactory,
    RelationshipUpdateFactory,
)
from world.relationships.models import (
    CharacterRelationship,
    RelationshipCondition,
    RelationshipUpdate,
)
from world.scenes.factories import InteractionFactory


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
        self.assertEqual(relationship.developments_this_week, 0)
        self.assertEqual(relationship.changes_this_week, 0)

    def test_clean_prevents_self_relationship(self):
        """Test that clean() prevents a character from relating to themselves."""
        relationship = CharacterRelationship(source=self.sheet1, target=self.sheet1)
        with self.assertRaises(ValidationError):
            relationship.clean()

    def test_clean_validates_displayed_tier_belongs_to_displayed_track(self):
        """Test that displayed_tier must belong to displayed_track."""
        track_a = RelationshipTrackFactory(name="DisplayTrackA")
        track_b = RelationshipTrackFactory(name="DisplayTrackB")
        tier_b = RelationshipTierFactory(
            track=track_b, name="TierB", tier_number=0, point_threshold=0
        )

        relationship = CharacterRelationshipFactory(source=self.sheet1, target=self.sheet2)
        relationship.displayed_track = track_a
        relationship.displayed_tier = tier_b  # Tier belongs to track_b, not track_a
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

    def test_developed_absolute_value(self):
        """Test developed_absolute_value sums only developed points."""
        relationship = CharacterRelationshipFactory(source=self.sheet1, target=self.sheet2)
        track1 = RelationshipTrackFactory(name="Trust", sign=TrackSign.POSITIVE)
        track2 = RelationshipTrackFactory(name="Fear", sign=TrackSign.NEGATIVE)
        RelationshipTrackProgressFactory(
            relationship=relationship, track=track1, capacity=50, developed_points=30
        )
        RelationshipTrackProgressFactory(
            relationship=relationship, track=track2, capacity=40, developed_points=20
        )

        self.assertEqual(relationship.developed_absolute_value, 50)

    def test_affection_uses_total_points(self):
        """Test affection uses developed points (positive add, negative subtract)."""
        relationship = CharacterRelationshipFactory(source=self.sheet1, target=self.sheet2)
        track1 = RelationshipTrackFactory(name="Respect", sign=TrackSign.POSITIVE)
        track2 = RelationshipTrackFactory(name="Hatred", sign=TrackSign.NEGATIVE)
        RelationshipTrackProgressFactory(
            relationship=relationship, track=track1, capacity=50, developed_points=30
        )
        RelationshipTrackProgressFactory(
            relationship=relationship, track=track2, capacity=40, developed_points=20
        )

        # Affection = 30 (positive) - 20 (negative) = 10
        self.assertEqual(relationship.affection, 10)

    def test_mechanical_bonus_cube_root(self):
        """Test mechanical_bonus returns cube root of developed absolute value."""
        relationship = CharacterRelationshipFactory(source=self.sheet1, target=self.sheet2)
        track = RelationshipTrackFactory(name="BonusTrack", sign=TrackSign.POSITIVE)
        RelationshipTrackProgressFactory(
            relationship=relationship, track=track, capacity=1000, developed_points=1000
        )

        # Cube root of 1000 = 10.0
        self.assertEqual(relationship.mechanical_bonus, 10.0)

    def test_factory_creates_valid_instance(self):
        """Test CharacterRelationshipFactory creates valid instance."""
        relationship = CharacterRelationshipFactory()
        self.assertIsNotNone(relationship.source)
        self.assertIsNotNone(relationship.target)


class RelationshipTrackProgressTests(TestCase):
    """Test RelationshipTrackProgress model."""

    def test_current_tier_uses_developed_points(self):
        """Test current_tier uses developed_points, not total."""
        track = RelationshipTrackFactory(name="TierTestTrack")
        RelationshipTierFactory(track=track, name="Low", tier_number=0, point_threshold=0)
        tier1 = RelationshipTierFactory(track=track, name="Mid", tier_number=1, point_threshold=10)
        RelationshipTierFactory(track=track, name="High", tier_number=2, point_threshold=50)

        progress = RelationshipTrackProgressFactory(track=track, capacity=100, developed_points=25)
        self.assertEqual(progress.current_tier, tier1)

    def test_current_tier_returns_none_below_all_thresholds(self):
        """Test current_tier returns None when below all thresholds."""
        track = RelationshipTrackFactory(name="NoneTestTrack")
        RelationshipTierFactory(track=track, name="First", tier_number=1, point_threshold=10)

        progress = RelationshipTrackProgressFactory(track=track, capacity=100, developed_points=5)
        self.assertIsNone(progress.current_tier)

    def test_total_points_includes_temporary(self):
        """Test total_points = developed + temporary from updates."""
        relationship = CharacterRelationshipFactory()
        track = RelationshipTrackFactory(name="TempTrack")
        progress = RelationshipTrackProgressFactory(
            relationship=relationship, track=track, capacity=100, developed_points=30
        )
        # Create a fresh update — temporary points should be at full value
        RelationshipUpdateFactory(
            relationship=relationship, track=track, points_earned=50, author=relationship.source
        )

        # Total should be developed (30) + temporary (~50, just created)
        total = progress.total_points
        self.assertGreaterEqual(total, 79)  # Allow for sub-day decay
        self.assertLessEqual(total, 80)

    def test_str_representation(self):
        """Test __str__ shows developed/capacity format."""
        track = RelationshipTrackFactory(name="StrTrack")
        progress = RelationshipTrackProgressFactory(track=track, capacity=100, developed_points=50)
        self.assertIn("50/100", str(progress))


class RelationshipUpdateDecayTests(TestCase):
    """Test temporary point decay on RelationshipUpdate."""

    def test_fresh_update_full_value(self):
        """A just-created update has full temporary value."""
        update = RelationshipUpdateFactory(points_earned=100)
        # Use created_at as reference to avoid sub-second decay
        self.assertEqual(update.current_temporary_value(update.created_at), 100)

    def test_half_decay(self):
        """After 5 days, temporary value is ~50% of original."""
        update = RelationshipUpdateFactory(points_earned=100)
        future = update.created_at + timedelta(days=5)
        value = update.current_temporary_value(future)
        self.assertEqual(value, 50)

    def test_full_decay(self):
        """After DECAY_DAYS, temporary value is 0."""
        update = RelationshipUpdateFactory(points_earned=100)
        future = update.created_at + timedelta(days=DECAY_DAYS)
        self.assertEqual(update.current_temporary_value(future), 0)

    def test_beyond_decay_days(self):
        """After more than DECAY_DAYS, temporary value is still 0."""
        update = RelationshipUpdateFactory(points_earned=100)
        future = update.created_at + timedelta(days=DECAY_DAYS + 5)
        self.assertEqual(update.current_temporary_value(future), 0)

    def test_one_day_decay(self):
        """After 1 day, 10% has decayed (90 remaining from 100)."""
        update = RelationshipUpdateFactory(points_earned=100)
        future = update.created_at + timedelta(days=1)
        self.assertEqual(update.current_temporary_value(future), 90)

    def test_linear_decay_pattern(self):
        """Verify decay is linear: 10% of original per day."""
        update = RelationshipUpdateFactory(points_earned=200)
        for day in range(DECAY_DAYS + 1):
            future = update.created_at + timedelta(days=day)
            expected = max(0, 200 - (200 * day // DECAY_DAYS))
            self.assertEqual(
                update.current_temporary_value(future),
                expected,
                f"Day {day}: expected {expected}",
            )


class RelationshipUpdateColoringValidationTests(TestCase):
    """Test RelationshipUpdate.clean() coloring validation."""

    def test_first_impression_requires_coloring(self):
        """First impression updates must have an emotional coloring."""
        update = RelationshipUpdate(
            is_first_impression=True,
            coloring="",
        )
        with self.assertRaises(ValidationError):
            update.clean()

    def test_non_first_impression_rejects_coloring(self):
        """Normal updates must not have an emotional coloring."""
        update = RelationshipUpdate(
            is_first_impression=False,
            coloring="positive",
        )
        with self.assertRaises(ValidationError):
            update.clean()

    def test_first_impression_with_coloring_passes(self):
        """First impression with coloring passes clean()."""
        update = RelationshipUpdate(
            is_first_impression=True,
            coloring="positive",
        )
        # Should not raise
        update.clean()

    def test_normal_update_without_coloring_passes(self):
        """Normal update without coloring passes clean()."""
        update = RelationshipUpdate(
            is_first_impression=False,
            coloring="",
        )
        # Should not raise
        update.clean()


class RelationshipUpdateInteractionReferenceTests(TestCase):
    """Test RelationshipUpdate interaction reference fields."""

    def test_update_with_linked_interaction_and_reference_mode(self):
        """RelationshipUpdate can store a linked_interaction and reference_mode."""
        relationship = CharacterRelationshipFactory()
        interaction = InteractionFactory()
        track = RelationshipTrackFactory(name="RefTrack")

        update = RelationshipUpdateFactory(
            relationship=relationship,
            author=relationship.source,
            track=track,
            linked_interaction=interaction,
            reference_mode=ReferenceMode.SPECIFIC_INTERACTION,
        )

        update.refresh_from_db()
        self.assertEqual(update.linked_interaction_id, interaction.pk)
        self.assertEqual(update.reference_mode, ReferenceMode.SPECIFIC_INTERACTION)

    def test_default_reference_mode_is_all_weekly(self):
        """Default reference_mode is ALL_WEEKLY."""
        update = RelationshipUpdateFactory()
        self.assertEqual(update.reference_mode, ReferenceMode.ALL_WEEKLY)

    def test_linked_interaction_nullable(self):
        """linked_interaction can be null."""
        update = RelationshipUpdateFactory(linked_interaction=None)
        self.assertIsNone(update.linked_interaction)
