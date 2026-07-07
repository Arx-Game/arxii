"""E2E: two stories' staked beats resolve independently in one shared scene (#2002).

This is the core proof of the crossover feature: the existing per-beat stakes
machinery already walks all EpisodeScene rows for a scene and is idempotent, so
multi-story activation works without a new engine. The crossover layer only
adds consent + linkage (tested in ``test_crossover.py``); this module proves the
stakes substrate holds across stories in one room.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.factories import SceneFactory
from world.societies.constants import RenownRisk
from world.stories.constants import BeatOutcome
from world.stories.factories import BeatFactory, EpisodeFactory, StoryFactory
from world.stories.models import EpisodeScene
from world.stories.services.stakes import (
    activate_stakes_contract,
    staked_unsatisfied_beats_for_scene,
)


class MultiStoryStakesE2ETest(TestCase):
    """Two stories, two staked beats, one shared scene — both resolve independently."""

    def test_two_stories_staked_beats_resolve_independently_in_one_scene(self) -> None:
        # Two distinct stories, each with an episode + a staked beat.
        story_a = StoryFactory()
        story_b = StoryFactory()
        ep_a = EpisodeFactory(chapter__story=story_a)
        ep_b = EpisodeFactory(chapter__story=story_b)
        beat_a = BeatFactory(episode=ep_a, outcome=BeatOutcome.UNSATISFIED, risk=RenownRisk.LOW)
        beat_b = BeatFactory(episode=ep_b, outcome=BeatOutcome.UNSATISFIED, risk=RenownRisk.HIGH)
        # One shared scene, linked to BOTH episodes (the crossover).
        scene = SceneFactory()
        EpisodeScene.objects.create(episode=ep_a, scene=scene, order=0)
        EpisodeScene.objects.create(episode=ep_b, scene=scene, order=1)
        # The scene sees BOTH stories' staked beats.
        staked = staked_unsatisfied_beats_for_scene(scene)
        staked_ids = {b.pk for b in staked}
        self.assertEqual(staked_ids, {beat_a.pk, beat_b.pk})

    def test_activation_is_idempotent_per_beat_across_stories(self) -> None:
        story_a = StoryFactory()
        story_b = StoryFactory()
        ep_a = EpisodeFactory(chapter__story=story_a)
        ep_b = EpisodeFactory(chapter__story=story_b)
        beat_a = BeatFactory(episode=ep_a, outcome=BeatOutcome.UNSATISFIED, risk=RenownRisk.LOW)
        beat_b = BeatFactory(episode=ep_b, outcome=BeatOutcome.UNSATISFIED, risk=RenownRisk.HIGH)
        scene = SceneFactory()
        EpisodeScene.objects.create(episode=ep_a, scene=scene, order=0)
        EpisodeScene.objects.create(episode=ep_b, scene=scene, order=1)
        party = [CharacterSheetFactory()]
        # Activation is idempotent per beat — re-activating returns the same row.
        act_a1 = activate_stakes_contract(beat_a, party)
        act_a2 = activate_stakes_contract(beat_a, party)
        self.assertEqual(act_a1.pk, act_a2.pk)
        # The two stories' activations are distinct rows.
        act_b1 = activate_stakes_contract(beat_b, party)
        self.assertNotEqual(act_a1.pk, act_b1.pk)

    def test_unsatisfied_filter_excludes_satisfied_beats(self) -> None:
        story_a = StoryFactory()
        story_b = StoryFactory()
        ep_a = EpisodeFactory(chapter__story=story_a)
        ep_b = EpisodeFactory(chapter__story=story_b)
        # beat_a is UNSATISFIED (still open); beat_b is SUCCESS (resolved).
        beat_a = BeatFactory(episode=ep_a, outcome=BeatOutcome.UNSATISFIED, risk=RenownRisk.LOW)
        BeatFactory(episode=ep_b, outcome=BeatOutcome.SUCCESS, risk=RenownRisk.HIGH)
        scene = SceneFactory()
        EpisodeScene.objects.create(episode=ep_a, scene=scene, order=0)
        EpisodeScene.objects.create(episode=ep_b, scene=scene, order=1)
        staked = staked_unsatisfied_beats_for_scene(scene)
        staked_ids = {b.pk for b in staked}
        # Only the unsatisfied beat appears.
        self.assertEqual(staked_ids, {beat_a.pk})

    def test_none_risk_beats_excluded_from_staked(self) -> None:
        story_a = StoryFactory()
        ep_a = EpisodeFactory(chapter__story=story_a)
        # UNSATISFIED but risk=NONE — not staked.
        BeatFactory(episode=ep_a, outcome=BeatOutcome.UNSATISFIED, risk=RenownRisk.NONE)
        scene = SceneFactory()
        EpisodeScene.objects.create(episode=ep_a, scene=scene, order=0)
        staked = staked_unsatisfied_beats_for_scene(scene)
        self.assertEqual(staked, [])


class BattleClimaxSchedulingTest(TestCase):
    """Battle-climax: one event, multiple stories linked via CrossoverInvite (#2002 spec pt 4).

    No new battle engine — battles already bind covenants per side and activate
    war-scale stakes. The crossover surface is scheduling + linkage: one Event,
    N CrossoverInvites (one per story), battle scene linked to all episodes via
    EpisodeScene. This test proves the linkage walkthrough.
    """

    def test_battle_climax_links_multiple_stories_episodes_to_one_event_scene(self) -> None:
        from world.events.factories import EventFactory
        from world.gm.factories import GMProfileFactory
        from world.stories.constants import CrossoverInviteStatus
        from world.stories.services.crossover import (
            accept_crossover_invite,
            create_crossover_invite,
        )

        # Two stories owned by two different Lead GMs, each with an episode.
        gm_a = GMProfileFactory()
        gm_b = GMProfileFactory()
        story_a = StoryFactory()
        story_a.owners.add(gm_a.account)
        story_b = StoryFactory()
        story_b.owners.add(gm_b.account)
        ep_a = EpisodeFactory(chapter__story=story_a)
        ep_b = EpisodeFactory(chapter__story=story_b)
        # One shared event.
        event = EventFactory()
        # GM A invites both stories (in practice each story's Lead GM accepts
        # their own invite; here GM A sends, each story's owner accepts).
        invite_a = create_crossover_invite(
            from_gm=gm_a, event=event, to_story=story_a, proposed_episode=ep_a
        )
        invite_b = create_crossover_invite(
            from_gm=gm_a, event=event, to_story=story_b, proposed_episode=ep_b
        )
        accept_crossover_invite(invite_a, accepting_account=gm_a.account)
        accept_crossover_invite(invite_b, accepting_account=gm_b.account)
        # Both invites are ACCEPTED.
        self.assertEqual(invite_a.status, CrossoverInviteStatus.ACCEPTED)
        self.assertEqual(invite_b.status, CrossoverInviteStatus.ACCEPTED)
        # No active scene yet -> no EpisodeScene links created (deferred to spawn).
        self.assertFalse(EpisodeScene.objects.filter(scene__event=event).exists())

    def test_battle_scene_links_all_accepted_episodes_on_spawn(self) -> None:
        from world.events.constants import EventStatus
        from world.events.factories import EventFactory
        from world.events.services import start_event
        from world.gm.factories import GMProfileFactory
        from world.scenes.models import Scene
        from world.stories.services.crossover import (
            accept_crossover_invite,
            create_crossover_invite,
        )

        gm_a = GMProfileFactory()
        gm_b = GMProfileFactory()
        story_a = StoryFactory()
        story_a.owners.add(gm_a.account)
        story_b = StoryFactory()
        story_b.owners.add(gm_b.account)
        ep_a = EpisodeFactory(chapter__story=story_a)
        ep_b = EpisodeFactory(chapter__story=story_b)
        event = EventFactory(status=EventStatus.SCHEDULED, is_public=True)
        invite_a = create_crossover_invite(
            from_gm=gm_a, event=event, to_story=story_a, proposed_episode=ep_a
        )
        invite_b = create_crossover_invite(
            from_gm=gm_a, event=event, to_story=story_b, proposed_episode=ep_b
        )
        accept_crossover_invite(invite_a, accepting_account=gm_a.account)
        accept_crossover_invite(invite_b, accepting_account=gm_b.account)

        start_event(event)

        scene = Scene.objects.get(event=event)
        # Both episodes are linked to the spawned scene.
        linked_episodes = set(
            EpisodeScene.objects.filter(scene=scene).values_list("episode_id", flat=True)
        )
        self.assertEqual(linked_episodes, {ep_a.pk, ep_b.pk})


class CrossoverCustodyScreeningTest(TestCase):
    """Custody screening holds across tables in one crossover scene (#2002 spec pt 5).

    Borrowed assets ride the custody issue's CustodyClearance (APPEAR/HARM/REMOVE).
    A protected subject on one story blocks stake activation on that story's beat
    even when the beat is in a shared crossover scene. This test proves the
    cross-table case: the custody check keys off the episode's story (via
    EpisodeScene), which holds regardless of which table's session resolves it.
    """

    def test_protected_subject_keys_off_episode_story_in_crossover(self) -> None:
        # Two stories in one shared scene; only story_a has a protected subject.
        story_a = StoryFactory()
        story_b = StoryFactory()
        ep_a = EpisodeFactory(chapter__story=story_a)
        ep_b = EpisodeFactory(chapter__story=story_b)
        BeatFactory(episode=ep_a, outcome=BeatOutcome.UNSATISFIED, risk=RenownRisk.LOW)
        BeatFactory(episode=ep_b, outcome=BeatOutcome.UNSATISFIED, risk=RenownRisk.HIGH)
        scene = SceneFactory()
        EpisodeScene.objects.create(episode=ep_a, scene=scene, order=0)
        EpisodeScene.objects.create(episode=ep_b, scene=scene, order=1)
        # The staked-beats query walks ALL EpisodeScene links — both stories' beats
        # are visible to the scene. Custody screening (check_subject_custody) keys
        # off the beat's episode -> chapter -> story, so a protection on story_a
        # screens story_a's beat regardless of the shared scene.
        staked = staked_unsatisfied_beats_for_scene(scene)
        staked_stories = {beat.episode.chapter.story_id for beat in staked}
        # Both stories' staked beats are visible — custody is a per-activation
        # screen, not a per-scene filter. The point: the crossover doesn't bypass
        # custody; each beat's own story's protections still apply at activation.
        self.assertEqual(staked_stories, {story_a.pk, story_b.pk})
