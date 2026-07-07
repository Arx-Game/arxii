"""Tests for the crossover invite lifecycle (#2002).

Covers create/accept/decline/withdraw + the deferred EpisodeScene link and
Lead-GM scene enrollment. The multi-story stakes E2E is in
``test_crossover_e2e.py``.
"""

from __future__ import annotations

from django.test import TestCase

from world.events.factories import EventFactory
from world.gm.factories import GMProfileFactory
from world.stories.constants import CrossoverInviteStatus
from world.stories.exceptions import CrossoverError
from world.stories.factories import EpisodeFactory, StoryFactory
from world.stories.models import EpisodeScene
from world.stories.services.crossover import (
    accept_crossover_invite,
    create_crossover_invite,
    decline_crossover_invite,
    link_accepted_episode_scene,
    withdraw_crossover_invite,
)


def _make_story_with_lead(account) -> object:
    """Create a Story owned by the given account."""
    story = StoryFactory()
    story.owners.add(account)
    return story


class CreateCrossoverInviteTests(TestCase):
    def test_pending_invite_created_for_event_and_story(self) -> None:
        gm = GMProfileFactory()
        story = _make_story_with_lead(gm.account)
        episode = EpisodeFactory(chapter__story=story)
        event = EventFactory()
        invite = create_crossover_invite(
            from_gm=gm, event=event, to_story=story, proposed_episode=episode
        )
        self.assertEqual(invite.status, CrossoverInviteStatus.PENDING)
        self.assertEqual(invite.event_id, event.pk)
        self.assertEqual(invite.to_story_id, story.pk)
        self.assertEqual(invite.proposed_episode_id, episode.pk)

    def test_duplicate_pending_invite_raises(self) -> None:
        gm = GMProfileFactory()
        story = _make_story_with_lead(gm.account)
        event = EventFactory()
        create_crossover_invite(from_gm=gm, event=event, to_story=story)
        with self.assertRaises(CrossoverError):
            create_crossover_invite(from_gm=gm, event=event, to_story=story)

    def test_proposed_episode_wrong_story_raises(self) -> None:
        gm = GMProfileFactory()
        story_a = _make_story_with_lead(gm.account)
        story_b = StoryFactory()
        episode_b = EpisodeFactory(chapter__story=story_b)
        event = EventFactory()
        with self.assertRaises(CrossoverError):
            create_crossover_invite(
                from_gm=gm, event=event, to_story=story_a, proposed_episode=episode_b
            )


class AcceptCrossoverInviteTests(TestCase):
    def test_accept_marks_accepted_and_sets_accepted_episode(self) -> None:
        gm = GMProfileFactory()
        story = _make_story_with_lead(gm.account)
        episode = EpisodeFactory(chapter__story=story)
        event = EventFactory()
        invite = create_crossover_invite(
            from_gm=gm, event=event, to_story=story, proposed_episode=episode
        )
        accept_crossover_invite(invite, accepting_account=gm.account)
        invite.refresh_from_db()
        self.assertEqual(invite.status, CrossoverInviteStatus.ACCEPTED)
        self.assertEqual(invite.accepted_episode_id, episode.pk)
        self.assertIsNotNone(invite.responded_at)

    def test_accept_without_scene_creates_no_episode_scene_yet(self) -> None:
        # No active scene on the event yet -> link deferred to scene spawn.
        gm = GMProfileFactory()
        story = _make_story_with_lead(gm.account)
        episode = EpisodeFactory(chapter__story=story)
        event = EventFactory()
        invite = create_crossover_invite(
            from_gm=gm, event=event, to_story=story, proposed_episode=episode
        )
        accept_crossover_invite(invite, accepting_account=gm.account)
        self.assertFalse(EpisodeScene.objects.filter(scene__event=event).exists())

    def test_accept_by_non_owner_raises(self) -> None:
        gm = GMProfileFactory()
        other = GMProfileFactory()
        story = _make_story_with_lead(gm.account)
        episode = EpisodeFactory(chapter__story=story)
        event = EventFactory()
        invite = create_crossover_invite(
            from_gm=gm, event=event, to_story=story, proposed_episode=episode
        )
        with self.assertRaises(CrossoverError):
            accept_crossover_invite(invite, accepting_account=other.account)

    def test_accept_non_pending_raises(self) -> None:
        gm = GMProfileFactory()
        story = _make_story_with_lead(gm.account)
        episode = EpisodeFactory(chapter__story=story)
        event = EventFactory()
        invite = create_crossover_invite(
            from_gm=gm, event=event, to_story=story, proposed_episode=episode
        )
        accept_crossover_invite(invite, accepting_account=gm.account)
        # Already accepted — second accept should fail.
        with self.assertRaises(CrossoverError):
            accept_crossover_invite(invite, accepting_account=gm.account)

    def test_accept_with_explicit_episode_overrides_proposed(self) -> None:
        gm = GMProfileFactory()
        story = _make_story_with_lead(gm.account)
        proposed = EpisodeFactory(chapter__story=story)
        chosen = EpisodeFactory(chapter__story=story)
        event = EventFactory()
        invite = create_crossover_invite(
            from_gm=gm, event=event, to_story=story, proposed_episode=proposed
        )
        accept_crossover_invite(invite, accepting_account=gm.account, accepted_episode=chosen)
        invite.refresh_from_db()
        self.assertEqual(invite.accepted_episode_id, chosen.pk)

    def test_accept_explicit_episode_wrong_story_raises(self) -> None:
        gm = GMProfileFactory()
        story = _make_story_with_lead(gm.account)
        other_story = StoryFactory()
        wrong_episode = EpisodeFactory(chapter__story=other_story)
        event = EventFactory()
        invite = create_crossover_invite(from_gm=gm, event=event, to_story=story)
        with self.assertRaises(CrossoverError):
            accept_crossover_invite(
                invite, accepting_account=gm.account, accepted_episode=wrong_episode
            )


class DeclineCrossoverInviteTests(TestCase):
    def test_decline_marks_declined(self) -> None:
        gm = GMProfileFactory()
        story = _make_story_with_lead(gm.account)
        event = EventFactory()
        invite = create_crossover_invite(from_gm=gm, event=event, to_story=story)
        decline_crossover_invite(invite, responding_account=gm.account)
        invite.refresh_from_db()
        self.assertEqual(invite.status, CrossoverInviteStatus.DECLINED)
        self.assertIsNotNone(invite.responded_at)

    def test_decline_by_non_owner_raises(self) -> None:
        gm = GMProfileFactory()
        other = GMProfileFactory()
        story = _make_story_with_lead(gm.account)
        event = EventFactory()
        invite = create_crossover_invite(from_gm=gm, event=event, to_story=story)
        with self.assertRaises(CrossoverError):
            decline_crossover_invite(invite, responding_account=other.account)


class WithdrawCrossoverInviteTests(TestCase):
    def test_withdraw_by_sender_marks_withdrawn(self) -> None:
        gm = GMProfileFactory()
        story = _make_story_with_lead(gm.account)
        event = EventFactory()
        invite = create_crossover_invite(from_gm=gm, event=event, to_story=story)
        withdraw_crossover_invite(invite, withdrawing_account=gm.account)
        invite.refresh_from_db()
        self.assertEqual(invite.status, CrossoverInviteStatus.WITHDRAWN)

    def test_withdraw_by_non_sender_raises(self) -> None:
        gm = GMProfileFactory()
        other = GMProfileFactory()
        story = _make_story_with_lead(gm.account)
        event = EventFactory()
        invite = create_crossover_invite(from_gm=gm, event=event, to_story=story)
        with self.assertRaises(CrossoverError):
            withdraw_crossover_invite(invite, withdrawing_account=other.account)


class DeferredEpisodeSceneLinkTests(TestCase):
    def test_link_accepted_invite_creates_episode_scene(self) -> None:
        from world.scenes.factories import SceneFactory

        gm = GMProfileFactory()
        story = _make_story_with_lead(gm.account)
        episode = EpisodeFactory(chapter__story=story)
        event = EventFactory()
        invite = create_crossover_invite(
            from_gm=gm, event=event, to_story=story, proposed_episode=episode
        )
        accept_crossover_invite(invite, accepting_account=gm.account)
        scene = SceneFactory()
        link_accepted_episode_scene(invite, scene)
        self.assertTrue(EpisodeScene.objects.filter(episode=episode, scene=scene).exists())

    def test_link_enrolls_lead_gm_as_scene_gm(self) -> None:
        from world.scenes.factories import SceneFactory
        from world.scenes.models import SceneParticipation

        gm = GMProfileFactory()
        story = _make_story_with_lead(gm.account)
        episode = EpisodeFactory(chapter__story=story)
        event = EventFactory()
        invite = create_crossover_invite(
            from_gm=gm, event=event, to_story=story, proposed_episode=episode
        )
        accept_crossover_invite(invite, accepting_account=gm.account)
        scene = SceneFactory()
        link_accepted_episode_scene(invite, scene)
        self.assertTrue(
            SceneParticipation.objects.filter(scene=scene, account=gm.account, is_gm=True).exists()
        )

    def test_link_non_accepted_invite_noops(self) -> None:
        from world.scenes.factories import SceneFactory

        gm = GMProfileFactory()
        story = _make_story_with_lead(gm.account)
        episode = EpisodeFactory(chapter__story=story)
        event = EventFactory()
        invite = create_crossover_invite(
            from_gm=gm, event=event, to_story=story, proposed_episode=episode
        )
        scene = SceneFactory()
        # Still PENDING — link should be a no-op.
        result = link_accepted_episode_scene(invite, scene)
        self.assertFalse(result)
        self.assertFalse(EpisodeScene.objects.filter(episode=episode, scene=scene).exists())

    def test_link_is_idempotent(self) -> None:
        from world.scenes.factories import SceneFactory

        gm = GMProfileFactory()
        story = _make_story_with_lead(gm.account)
        episode = EpisodeFactory(chapter__story=story)
        event = EventFactory()
        invite = create_crossover_invite(
            from_gm=gm, event=event, to_story=story, proposed_episode=episode
        )
        accept_crossover_invite(invite, accepting_account=gm.account)
        scene = SceneFactory()
        link_accepted_episode_scene(invite, scene)
        link_accepted_episode_scene(invite, scene)
        self.assertEqual(
            EpisodeScene.objects.filter(episode=episode, scene=scene).count(),
            1,
        )


class StartEventWiringTests(TestCase):
    """start_event links accepted crossover invites to the spawned scene (#2002)."""

    def test_start_event_links_accepted_invite_episode_scene(self) -> None:
        from world.events.constants import EventStatus
        from world.events.services import start_event
        from world.scenes.models import Scene, SceneParticipation

        gm = GMProfileFactory()
        story = _make_story_with_lead(gm.account)
        episode = EpisodeFactory(chapter__story=story)
        event = EventFactory(status=EventStatus.SCHEDULED, is_public=True)
        invite = create_crossover_invite(
            from_gm=gm, event=event, to_story=story, proposed_episode=episode
        )
        accept_crossover_invite(invite, accepting_account=gm.account)

        start_event(event)

        scene = Scene.objects.get(event=event)
        self.assertTrue(EpisodeScene.objects.filter(episode=episode, scene=scene).exists())
        # Invited Lead GM enrolled as a scene GM.
        self.assertTrue(
            SceneParticipation.objects.filter(scene=scene, account=gm.account, is_gm=True).exists()
        )

    def test_start_event_with_no_invites_creates_scene_only(self) -> None:
        from world.events.constants import EventStatus
        from world.events.services import start_event
        from world.scenes.models import Scene

        event = EventFactory(status=EventStatus.SCHEDULED, is_public=True)
        start_event(event)
        self.assertTrue(Scene.objects.filter(event=event).exists())
        # No crossover invites -> no EpisodeScene rows.
        self.assertEqual(EpisodeScene.objects.filter(scene__event=event).count(), 0)
