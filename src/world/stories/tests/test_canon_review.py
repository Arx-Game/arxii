"""Canon-impact review: impact tiers + staff review for world-touching content (#2003)."""

from django.test import TestCase

from world.stories.constants import ImpactTier
from world.stories.models import Story


class ImpactTierFieldTests(TestCase):
    def test_story_defaults_to_table_tier(self) -> None:
        story = Story.objects.create(title="T", description="")
        self.assertEqual(story.impact_tier, ImpactTier.TABLE)

    def test_impact_tier_choices_round_trip(self) -> None:
        for tier in (ImpactTier.TABLE, ImpactTier.REGIONAL, ImpactTier.WORLD):
            story = Story.objects.create(title=f"Story {tier}", description="", impact_tier=tier)
            story.refresh_from_db()
            self.assertEqual(story.impact_tier, tier)
