"""Tests for complete_story: conclude a story + honestly foreclose in-flight progress."""

from django.test import TestCase

from world.stories.constants import ProgressStatus, StoryScope
from world.stories.factories import (
    GlobalStoryProgressFactory,
    GroupStoryProgressFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.services.completion import complete_story
from world.stories.types import StoryStatus


class CompleteStoryTests(TestCase):
    def test_sets_completed_status_and_timestamp(self):
        story = StoryFactory(status=StoryStatus.ACTIVE)
        complete_story(story=story)
        story.refresh_from_db()
        self.assertEqual(story.status, StoryStatus.COMPLETED)
        self.assertIsNotNone(story.completed_at)

    def test_idempotent(self):
        story = StoryFactory(status=StoryStatus.ACTIVE)
        complete_story(story=story)
        story.refresh_from_db()
        first_ts = story.completed_at
        complete_story(story=story)
        story.refresh_from_db()
        self.assertEqual(story.completed_at, first_ts)

    def test_in_flight_group_progress_foreclosed(self):
        story = StoryFactory(status=StoryStatus.ACTIVE, scope=StoryScope.GROUP)
        progress = GroupStoryProgressFactory(
            story=story, status=ProgressStatus.ACTIVE, is_active=True
        )
        complete_story(story=story)
        progress.refresh_from_db()
        self.assertEqual(progress.status, ProgressStatus.FORECLOSED)
        self.assertFalse(progress.is_active)

    def test_in_flight_character_progress_foreclosed(self):
        story = StoryFactory(status=StoryStatus.ACTIVE, scope=StoryScope.CHARACTER)
        progress = StoryProgressFactory(story=story, status=ProgressStatus.RESTING, is_active=True)
        complete_story(story=story)
        progress.refresh_from_db()
        self.assertEqual(progress.status, ProgressStatus.FORECLOSED)
        self.assertFalse(progress.is_active)

    def test_in_flight_global_progress_foreclosed(self):
        story = StoryFactory(status=StoryStatus.ACTIVE, scope=StoryScope.GLOBAL)
        progress = GlobalStoryProgressFactory(
            story=story, status=ProgressStatus.ACTIVE, is_active=True
        )
        complete_story(story=story)
        progress.refresh_from_db()
        self.assertEqual(progress.status, ProgressStatus.FORECLOSED)
        self.assertFalse(progress.is_active)

    def test_already_completed_progress_preserved(self):
        story = StoryFactory(status=StoryStatus.ACTIVE, scope=StoryScope.GROUP)
        progress = GroupStoryProgressFactory(
            story=story, status=ProgressStatus.COMPLETED, is_active=False
        )
        complete_story(story=story)
        progress.refresh_from_db()
        self.assertEqual(progress.status, ProgressStatus.COMPLETED)


class CompleteStoryCampaignDissolutionTests(TestCase):
    """Phase B (#759): completing a story dissolves its linked CAMPAIGN covenants."""

    def _campaign_covenant(self, story):
        from world.character_sheets.factories import CharacterSheetFactory
        from world.covenants.constants import BattleBinding, CovenantType
        from world.covenants.factories import CovenantRoleFactory
        from world.covenants.services import create_covenant
        from world.covenants.types import CovenantFounder

        role = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
        founders = [
            CovenantFounder(character_sheet=CharacterSheetFactory(), role=role),
            CovenantFounder(character_sheet=CharacterSheetFactory(), role=role),
        ]
        return create_covenant(
            name="The Crusade",
            covenant_type=CovenantType.BATTLE,
            sworn_objective="x",
            founders=founders,
            battle_binding=BattleBinding.CAMPAIGN,
            campaign_story=story,
        )

    def test_completion_dissolves_linked_campaign_and_clears_engagement(self):
        story = StoryFactory(status=StoryStatus.ACTIVE)
        covenant = self._campaign_covenant(story)
        membership = covenant.memberships.filter(left_at__isnull=True).first()
        membership.engaged = True
        membership.save(update_fields=["engaged"])

        complete_story(story=story)

        covenant.refresh_from_db()
        membership.refresh_from_db()
        self.assertIsNotNone(covenant.dissolved_at)
        self.assertFalse(membership.engaged)
        self.assertIsNotNone(membership.left_at)

    def test_completion_leaves_standing_covenant(self):
        from world.covenants.constants import BattleBinding, CovenantType
        from world.covenants.models import Covenant

        story = StoryFactory(status=StoryStatus.ACTIVE)
        covenant = Covenant.objects.create(
            name="The Banner",
            covenant_type=CovenantType.BATTLE,
            sworn_objective="x",
            battle_binding=BattleBinding.STANDING,
        )
        # STANDING references the story only informationally (Story.covenant), never
        # via campaign_story — so completion must not dissolve it.
        story.covenant = covenant
        story.save(update_fields=["covenant"])

        complete_story(story=story)

        covenant.refresh_from_db()
        self.assertIsNone(covenant.dissolved_at)

    def test_completion_ignores_unlinked_campaign(self):
        from world.covenants.constants import BattleBinding, CovenantType
        from world.covenants.models import Covenant

        story = StoryFactory(status=StoryStatus.ACTIVE)
        other_campaign = Covenant.objects.create(
            name="Different War",
            covenant_type=CovenantType.BATTLE,
            sworn_objective="x",
            battle_binding=BattleBinding.CAMPAIGN,
        )  # no campaign_story link to this story

        complete_story(story=story)

        other_campaign.refresh_from_db()
        self.assertIsNone(other_campaign.dissolved_at)
