"""Model tests for the ties shape (#3957): labels, depth, tiers, gauges."""

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.relationships.constants import LabelAwareness, TypeFamily, TypeValence
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipLabelFactory,
    RelationshipTierFactory,
    RelationshipTypeFactory,
)
from world.relationships.models import (
    CharacterRelationship,
    RelationshipGrowthConfig,
    RelationshipLabel,
    RelationshipTier,
    RelationshipType,
)


class RelationshipTypeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.mentor = RelationshipTypeFactory(name="Mentor", family=TypeFamily.TEACHING)
        cls.student = RelationshipTypeFactory(
            name="Student", family=TypeFamily.TEACHING, counterpart=cls.mentor
        )
        cls.mentor.counterpart = cls.student
        cls.mentor.save(update_fields=["counterpart"])
        cls.friend = RelationshipTypeFactory(name="Friend", valence=TypeValence.WARM)

    def test_counterpart_or_self_defaults_to_self(self):
        self.assertEqual(self.friend.counterpart_or_self.pk, self.friend.pk)
        self.assertEqual(self.mentor.counterpart_or_self.pk, self.student.pk)

    def test_natural_key_is_name(self):
        self.assertEqual(RelationshipType.objects.get_by_natural_key("Friend").pk, self.friend.pk)


class CharacterRelationshipDepthTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = CharacterSheetFactory()
        cls.b = CharacterSheetFactory()
        cls.ab = CharacterRelationshipFactory(
            source=cls.a, target=cls.b, scene_depth=48, invested_depth=184
        )
        cls.ba = CharacterRelationshipFactory(
            source=cls.b, target=cls.a, scene_depth=48, invested_depth=60
        )
        RelationshipTierFactory(tier_number=1, depth_threshold=25)
        RelationshipTierFactory(tier_number=2, depth_threshold=100)
        RelationshipTierFactory(tier_number=3, depth_threshold=500)

    def test_depth_is_this_sides_added_depth(self):
        self.assertEqual(self.ab.depth, 232)
        self.assertEqual(self.ba.depth, 108)

    def test_pair_depth_sums_both_sides(self):
        self.assertEqual(self.ab.pair_depth(), 340)
        self.assertEqual(self.ba.pair_depth(), 340)

    def test_reverse_row(self):
        self.assertEqual(self.ab.reverse.pk, self.ba.pk)
        lone = CharacterRelationshipFactory(source=self.a, target=CharacterSheetFactory())
        self.assertIsNone(lone.reverse)

    def test_next_tier_reads_the_ladder(self):
        self.ab.tier = 2
        self.assertEqual(self.ab.next_tier().tier_number, 3)
        self.ab.tier = 3
        self.assertIsNone(self.ab.next_tier())

    def test_self_relationship_rejected(self):
        with self.assertRaises(IntegrityError):
            CharacterRelationship.objects.create(source=self.a, target=self.a)


class RelationshipLabelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.side = CharacterRelationshipFactory()
        cls.lover = RelationshipTypeFactory(name="Lover", valence=TypeValence.WARM)

    def test_defaults_private_and_open(self):
        label = RelationshipLabelFactory(relationship=self.side, type=self.lover)
        self.assertEqual(label.awareness, LabelAwareness.PRIVATE)
        self.assertIsNone(label.ended_at)
        self.assertFalse(label.is_former)

    def test_one_open_label_per_type_per_side(self):
        RelationshipLabelFactory(relationship=self.side, type=self.lover)
        with self.assertRaises(IntegrityError):
            RelationshipLabel.objects.create(relationship=self.side, type=self.lover)

    def test_ended_label_frees_the_type(self):
        first = RelationshipLabelFactory(relationship=self.side, type=self.lover)
        first.ended_at = timezone.now()
        first.save(update_fields=["ended_at"])
        second = RelationshipLabelFactory(relationship=self.side, type=self.lover)
        self.assertTrue(first.is_former)
        self.assertEqual(list(self.side.open_labels()), [second])


class RelationshipTierTests(TestCase):
    def test_tier_number_unique(self):
        RelationshipTierFactory(tier_number=1, depth_threshold=25)
        with self.assertRaises(IntegrityError):
            RelationshipTier.objects.create(tier_number=1, name="Again", depth_threshold=30)


class GrowthConfigTests(TestCase):
    def test_defaults(self):
        cfg = RelationshipGrowthConfig.objects.create()
        self.assertEqual(cfg.depth_per_ap, 5)
        self.assertEqual(cfg.scene_base_gain, 10)
        self.assertEqual(cfg.xp_per_tier, 10)
        self.assertEqual(cfg.thread_min_tier, 2)

    def test_capstone_needs_entry_unless_ritual(self):
        from world.relationships.models import RelationshipCapstone

        side = CharacterRelationshipFactory()
        with self.assertRaises(IntegrityError):
            RelationshipCapstone.objects.create(relationship=side, tier_claimed=1)
