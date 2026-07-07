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
