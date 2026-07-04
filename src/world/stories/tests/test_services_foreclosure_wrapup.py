"""Tests for resolve_foreclosed_progress + notify_foreclosed_resolved.

Wrapping up a FORECLOSED thread stamps resolved_at/resolved_by and fans out
an honest closure message — without reclassifying it as COMPLETED.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory
from world.narrative.models import NarrativeMessage, NarrativeMessageDelivery
from world.stories.constants import ProgressStatus, StoryScope
from world.stories.factories import (
    GlobalStoryProgressFactory,
    GroupStoryProgressFactory,
    StoryFactory,
    StoryProgressFactory,
)
from world.stories.services.completion import complete_story, resolve_foreclosed_progress
from world.stories.types import StoryStatus


class ResolveForeclosedProgressTests(TestCase):
    def _gm(self):
        return GMProfileFactory()

    def test_resolves_foreclosed_character_progress(self):
        sheet = CharacterSheetFactory()
        story = StoryFactory(
            status=StoryStatus.ACTIVE, scope=StoryScope.CHARACTER, character_sheet=sheet
        )
        progress = StoryProgressFactory(
            story=story, character_sheet=sheet, status=ProgressStatus.ACTIVE, is_active=True
        )
        complete_story(story=story)
        gm = self._gm()
        resolve_foreclosed_progress(progress=progress, resolved_by=gm)
        progress.refresh_from_db()
        self.assertEqual(progress.status, ProgressStatus.FORECLOSED)
        self.assertFalse(progress.is_active)
        self.assertIsNotNone(progress.resolved_at)
        self.assertEqual(progress.resolved_by_id, gm.pk)
        # The closure message was fanned out.
        self.assertTrue(
            NarrativeMessage.objects.filter(related_story=story, category="story").exists()
        )

    def test_idempotent_already_resolved_is_noop(self):
        story = StoryFactory(status=StoryStatus.ACTIVE, scope=StoryScope.GROUP)
        progress = GroupStoryProgressFactory(
            story=story, status=ProgressStatus.ACTIVE, is_active=True
        )
        complete_story(story=story)
        gm = self._gm()
        resolve_foreclosed_progress(progress=progress, resolved_by=gm)
        progress.refresh_from_db()
        first_at = progress.resolved_at
        first_msg_count = NarrativeMessage.objects.filter(related_story=story).count()
        # Second call is a no-op — no re-notify.
        resolve_foreclosed_progress(progress=progress, resolved_by=gm)
        progress.refresh_from_db()
        self.assertEqual(progress.resolved_at, first_at)
        self.assertEqual(
            NarrativeMessage.objects.filter(related_story=story).count(), first_msg_count
        )

    def test_non_foreclosed_raises_value_error(self):
        sheet = CharacterSheetFactory()
        story = StoryFactory(
            status=StoryStatus.ACTIVE, scope=StoryScope.CHARACTER, character_sheet=sheet
        )
        progress = StoryProgressFactory(
            story=story, character_sheet=sheet, status=ProgressStatus.ACTIVE, is_active=True
        )
        with self.assertRaises(ValueError):
            resolve_foreclosed_progress(progress=progress, resolved_by=self._gm())

    def test_resolves_global_progress(self):
        story = StoryFactory(status=StoryStatus.ACTIVE, scope=StoryScope.GLOBAL)
        progress = GlobalStoryProgressFactory(
            story=story, status=ProgressStatus.ACTIVE, is_active=True
        )
        complete_story(story=story)
        resolve_foreclosed_progress(progress=progress, resolved_by=self._gm())
        progress.refresh_from_db()
        self.assertIsNotNone(progress.resolved_at)


class NotifyForeclosedResolvedTests(TestCase):
    def test_fans_out_honest_closure_message(self):
        sheet = CharacterSheetFactory()
        story = StoryFactory(
            status=StoryStatus.ACTIVE, scope=StoryScope.CHARACTER, character_sheet=sheet
        )
        progress = StoryProgressFactory(
            story=story, character_sheet=sheet, status=ProgressStatus.ACTIVE, is_active=True
        )
        complete_story(story=story)
        gm = GMProfileFactory()
        resolve_foreclosed_progress(progress=progress, resolved_by=gm)
        msg = NarrativeMessage.objects.get(related_story=story)
        self.assertEqual(msg.category, "story")
        # Honest: never claims completion.
        self.assertNotIn("completed", msg.body.lower())
        self.assertEqual(msg.sender_account_id, gm.account_id)
        self.assertTrue(NarrativeMessageDelivery.objects.filter(message=msg).exists())
