"""Canon-impact review: impact tiers + staff review for world-touching content (#2003)."""

from django.db import IntegrityError
from django.test import TestCase

from world.stories.constants import CanonReviewStatus, ImpactTier
from world.stories.models import CanonReview, Story


class ImpactTierFieldTests(TestCase):
    def test_story_defaults_to_table_tier(self) -> None:
        story = Story.objects.create(title="T", description="")
        self.assertEqual(story.impact_tier, ImpactTier.TABLE)

    def test_impact_tier_choices_round_trip(self) -> None:
        for tier in (ImpactTier.TABLE, ImpactTier.REGIONAL, ImpactTier.WORLD):
            story = Story.objects.create(title=f"Story {tier}", description="", impact_tier=tier)
            story.refresh_from_db()
            self.assertEqual(story.impact_tier, tier)


class CanonReviewModelTests(TestCase):
    def test_defaults_to_pending(self) -> None:
        story = Story.objects.create(title="T", description="", impact_tier=ImpactTier.WORLD)
        review = CanonReview.objects.create(story=story, tier=ImpactTier.WORLD)
        self.assertEqual(review.status, CanonReviewStatus.PENDING)
        self.assertIsNone(review.resolved_at)
        self.assertEqual(review.tier, ImpactTier.WORLD)

    def test_only_one_pending_review_per_story(self) -> None:
        story = Story.objects.create(title="T", description="", impact_tier=ImpactTier.WORLD)
        CanonReview.objects.create(story=story, tier=ImpactTier.WORLD)
        with self.assertRaises(IntegrityError):
            CanonReview.objects.create(story=story, tier=ImpactTier.WORLD)

    def test_cleared_review_allows_new_pending(self) -> None:
        story = Story.objects.create(title="T", description="", impact_tier=ImpactTier.WORLD)
        old = CanonReview.objects.create(story=story, tier=ImpactTier.WORLD)
        old.status = CanonReviewStatus.CLEARED
        old.save()
        # A new PENDING review is now allowed
        CanonReview.objects.create(story=story, tier=ImpactTier.WORLD)
        self.assertEqual(CanonReview.objects.filter(story=story).count(), 2)
