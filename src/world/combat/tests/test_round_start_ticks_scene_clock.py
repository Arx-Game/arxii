"""A combat round start ticks the running beat's scene clock (#3567)."""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from world.combat.factories import CombatEncounterFactory, CombatOpponentFactory
from world.combat.services import begin_declaration_phase
from world.scenes.clock_services import open_clock_for_beat, start_scene_clock
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneFactory
from world.stories.factories import BeatFactory


class RoundStartTicksClockTests(TestCase):
    def test_round_start_ticks_once(self) -> None:
        beat = BeatFactory(clock_size=3)
        scene = SceneFactory(running_beat=beat)
        start_scene_clock(scene, beat)
        encounter = CombatEncounterFactory(scene=scene, status=RoundStatus.BETWEEN_ROUNDS)
        CombatOpponentFactory(encounter=encounter)
        begin_declaration_phase(encounter)
        self.assertEqual(open_clock_for_beat(beat).filled, 1)

    def test_encounter_story_beat_resolves_when_scene_has_no_running_beat(self) -> None:
        beat = BeatFactory(clock_size=3)
        scene = SceneFactory(running_beat=None)
        start_scene_clock(scene, beat)
        encounter = CombatEncounterFactory(
            scene=scene, story_beat=beat, status=RoundStatus.BETWEEN_ROUNDS
        )
        CombatOpponentFactory(encounter=encounter)
        begin_declaration_phase(encounter)
        self.assertEqual(open_clock_for_beat(beat).filled, 1)

    def test_no_clock_is_a_noop(self) -> None:
        scene = SceneFactory(running_beat=BeatFactory(clock_size=0))
        encounter = CombatEncounterFactory(scene=scene, status=RoundStatus.BETWEEN_ROUNDS)
        CombatOpponentFactory(encounter=encounter)
        begin_declaration_phase(encounter)
        self.assertEqual(encounter.round_number, 1)

    def test_filling_round_completes_after_the_round_commits(self) -> None:
        beat = BeatFactory(clock_size=1)
        scene = SceneFactory(running_beat=beat)
        start_scene_clock(scene, beat)
        encounter = CombatEncounterFactory(scene=scene, status=RoundStatus.BETWEEN_ROUNDS)
        CombatOpponentFactory(encounter=encounter)
        with (
            mock.patch("world.scenes.clock_services.complete_beat_expired") as done,
            self.captureOnCommitCallbacks(execute=True),
        ):
            begin_declaration_phase(encounter)
            done.assert_not_called()
        done.assert_called_once()
