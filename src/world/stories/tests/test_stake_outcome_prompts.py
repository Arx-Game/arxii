from unittest import mock

from django.db import DatabaseError
from django.test import TestCase

from world.gm.constants import GMPromptGroup, GMPromptKind
from world.gm.factories import GMPromptFilterFactory, GMTableFactory
from world.gm.models import GMPrompt
from world.stories.constants import StakeOutcomeMethod, StakeResolutionColumn
from world.stories.factories import StakeFactory, StakeResolutionFactory
from world.stories.services.stake_resolution import _fire_branch_and_record


class StakeOutcomePromptTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.table = GMTableFactory()

    def _stake(self):
        stake = StakeFactory()
        story = stake.beat.episode.chapter.story
        story.primary_table = self.table
        story.save(update_fields=["primary_table"])
        return stake

    def _fire(self, stake, resolution):
        return _fire_branch_and_record(
            stake=stake,
            resolution=resolution,
            column=StakeResolutionColumn.LOSS,
            method=StakeOutcomeMethod.MACHINE,
            activation=None,
            progress=None,
            scope=stake.beat.episode.chapter.story.scope,
            participants=[],
        )

    def test_story_line_goes_to_the_story_gm(self):  # spec scenario 5
        stake = self._stake()
        resolution = StakeResolutionFactory(stake=stake, narrative_summary="It goes badly.")
        outcome = self._fire(stake, resolution)
        prompt = GMPrompt.objects.get(kind=GMPromptKind.STAKE_OUTCOME)
        self.assertEqual(prompt.addressed_to, self.table.gm.account)
        self.assertEqual(prompt.room_text, "It goes badly.")
        self.assertEqual(prompt.stake_outcome, outcome)
        self.assertIsNone(prompt.scene)

    def test_blank_narrative_summary_still_prompts(self):  # ruling R8-2
        """A blank narrative_summary is still a 'this stake resolved' notice --
        the prompt goes out to the Lead GM with an empty room_text, not withheld."""
        stake = self._stake()
        resolution = StakeResolutionFactory(stake=stake, narrative_summary="")
        outcome = self._fire(stake, resolution)
        prompt = GMPrompt.objects.get(kind=GMPromptKind.STAKE_OUTCOME)
        self.assertEqual(prompt.addressed_to, self.table.gm.account)
        self.assertEqual(prompt.room_text, "")
        self.assertEqual(prompt.stake_outcome, outcome)

    def test_orphaned_story_prompts_no_one(self):
        stake = StakeFactory()
        self._fire(stake, StakeResolutionFactory(stake=stake))
        self.assertFalse(GMPrompt.objects.exists())

    def test_muted_story_gm_not_prompted(self):
        GMPromptFilterFactory(
            account=self.table.gm.account, group=GMPromptGroup.STAKE_OUTCOME, enabled=False
        )
        stake = self._stake()
        self._fire(stake, StakeResolutionFactory(stake=stake))
        self.assertFalse(GMPrompt.objects.exists())

    def test_routing_database_error_does_not_crash_resolution(self):
        """``GMPrompt.objects.create`` raises for the Lead GM's own single prompt.

        The outer ``_fire_branch_and_record`` must still return the outcome row
        it already claimed, with no orphan GMPrompt and no live notify. With
        the try/except shape reverted, this raises out of
        ``_fire_branch_and_record`` instead of returning.
        """
        stake = self._stake()
        resolution = StakeResolutionFactory(stake=stake, narrative_summary="It goes badly.")

        with (
            mock.patch.object(GMPrompt.objects, "create", side_effect=DatabaseError("boom")),
            mock.patch("world.gm.prompt_services.notify_gm_prompt") as notify,
            self.captureOnCommitCallbacks(execute=True),
        ):
            outcome = self._fire(stake, resolution)

        notify.assert_not_called()
        self.assertFalse(GMPrompt.objects.exists())
        self.assertIsNotNone(outcome.pk)
