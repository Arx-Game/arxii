"""Telnet tests for canon-review commands (#2003): ``story impact``/
``story review-status`` and the standalone ``canonreview`` staff command."""

from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from commands.canon_review import CmdCanonReview
from commands.story import CmdStory
from evennia_extensions.factories import AccountFactory
from world.stories.constants import CanonReviewStatus, ImpactTier
from world.stories.factories import StoryFactory
from world.stories.services.canon_review import (
    clear_canon_review,
    request_canon_review,
)


def _make_story_cmd(caller, args: str) -> CmdStory:
    cmd = CmdStory()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"story {args}".strip()
    return cmd


def _make_canon_cmd(caller, args: str) -> CmdCanonReview:
    cmd = CmdCanonReview()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"canonreview {args}".strip()
    return cmd


def _messages(caller: MagicMock) -> list[str]:
    return [str(c.args[0]) for c in caller.msg.call_args_list if c.args]


class StoryImpactCommandTests(TestCase):
    """``story impact <story-id>=<tier>`` — Lead-GM-gated tier setter (#2003)."""

    def setUp(self) -> None:
        self.owner = AccountFactory()
        self.caller = MagicMock()
        self.caller.msg = MagicMock()
        self.caller.account = self.owner
        self.story = StoryFactory(impact_tier=ImpactTier.TABLE, owners=[self.owner])

    def _run(self, args: str) -> list[str]:
        cmd = _make_story_cmd(self.caller, args)
        cmd.func()
        return _messages(self.caller)

    def test_owner_sets_world_tier(self) -> None:
        messages = self._run(f"impact {self.story.pk}=world")
        self.story.refresh_from_db()
        self.assertEqual(self.story.impact_tier, ImpactTier.WORLD)
        self.assertTrue(any("world" in m.lower() for m in messages))

    def test_non_owner_cannot_set_tier(self) -> None:
        non_owner = AccountFactory()
        self.caller.account = non_owner
        self._run(f"impact {self.story.pk}=world")
        self.story.refresh_from_db()
        self.assertEqual(self.story.impact_tier, ImpactTier.TABLE)

    def test_invalid_tier_shows_usage(self) -> None:
        messages = self._run(f"impact {self.story.pk}=galactic")
        self.assertTrue(any("usage" in m.lower() for m in messages))

    def test_frozen_after_clear(self) -> None:
        review = request_canon_review(self.story)
        clear_canon_review(review, AccountFactory(is_staff=True))
        messages = self._run(f"impact {self.story.pk}=world")
        self.story.refresh_from_db()
        self.assertEqual(self.story.impact_tier, ImpactTier.TABLE)
        self.assertTrue(any("frozen" in m.lower() for m in messages))


class StoryReviewStatusCommandTests(TestCase):
    """``story review-status <story-id>`` — the Lead GM's readout (#2003)."""

    def setUp(self) -> None:
        self.owner = AccountFactory()
        self.caller = MagicMock()
        self.caller.msg = MagicMock()
        self.caller.account = self.owner
        self.story = StoryFactory(impact_tier=ImpactTier.WORLD, owners=[self.owner])

    def _run(self, args: str) -> list[str]:
        cmd = _make_story_cmd(self.caller, args)
        cmd.func()
        return _messages(self.caller)

    def test_shows_tier_and_no_review(self) -> None:
        messages = self._run(f"review-status {self.story.pk}")
        joined = " ".join(messages).lower()
        self.assertIn("world", joined)
        self.assertIn("none requested", joined)

    def test_shows_pending_review(self) -> None:
        request_canon_review(self.story)
        messages = self._run(f"review-status {self.story.pk}")
        self.assertTrue(any("pending" in m.lower() for m in messages))

    def test_shows_cleared(self) -> None:
        review = request_canon_review(self.story)
        clear_canon_review(review, AccountFactory(is_staff=True))
        messages = self._run(f"review-status {self.story.pk}")
        self.assertTrue(any("cleared" in m.lower() for m in messages))


class CanonReviewCommandTests(TestCase):
    """``canonreview list|clear|changes`` — staff queue surface (#2003)."""

    def setUp(self) -> None:
        self.staff = AccountFactory(is_staff=True)
        self.caller = MagicMock()
        self.caller.msg = MagicMock()
        self.caller.account = self.staff
        self.story = StoryFactory(impact_tier=ImpactTier.WORLD)
        self.review = request_canon_review(self.story)

    def _run(self, args: str) -> list[str]:
        cmd = _make_canon_cmd(self.caller, args)
        cmd.func()
        return _messages(self.caller)

    def test_list_shows_pending(self) -> None:
        messages = self._run("list")
        self.assertTrue(any(self.story.title in m for m in messages))

    def test_list_empty_when_no_pending(self) -> None:
        clear_canon_review(self.review, self.staff)
        messages = self._run("list")
        self.assertTrue(any("no pending" in m.lower() for m in messages))

    def test_clear_approves(self) -> None:
        self._run(f"clear {self.review.pk} notes=ok")
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, CanonReviewStatus.CLEARED)
        self.assertEqual(self.review.reviewer, self.staff)

    def test_changes_requires_notes(self) -> None:
        self._run(f"changes {self.review.pk}")
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, CanonReviewStatus.PENDING)

    def test_changes_with_notes(self) -> None:
        self._run(f"changes {self.review.pk} notes=narrow the scope")
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, CanonReviewStatus.CHANGES_REQUESTED)
        self.assertIn("narrow the scope", self.review.notes)

    def test_nonexistent_review(self) -> None:
        messages = self._run("clear 99999")
        self.assertTrue(any("no canon review" in m.lower() for m in messages))
