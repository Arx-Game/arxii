"""Scene clock actions (#3567): RunBeat opens it, AdvanceClock fills it, only

one scene may run a beat.
"""

from __future__ import annotations

from unittest import mock

from actions.definitions.gm_story import (
    AdvanceClockAction,
    GMListRunnableBeatsAction,
    RunBeatAction,
)
from actions.tests.test_gm_story_run_beat import RunBeatActionTestBase
from world.combat.factories import CombatEncounterFactory, CombatOpponentFactory
from world.combat.services import begin_declaration_phase
from world.scenes.clock_services import open_clock_for_beat
from world.scenes.constants import RoundStatus, SceneClockClosedReason
from world.scenes.factories import SceneFactory
from world.scenes.models import SceneClock
from world.stories.constants import BeatKind, BeatOutcome
from world.stories.factories import BeatFactory
from world.stories.models import BeatCompletion


class RunBeatOpensClockTests(RunBeatActionTestBase):
    def _situation_beat(self, clock_size: int) -> object:
        return BeatFactory(episode=self.episode, kind=BeatKind.SITUATION, clock_size=clock_size)

    def test_run_beat_opens_a_clock_of_authored_size(self) -> None:
        beat = self._situation_beat(3)
        result = RunBeatAction().run(self.lead_gm_actor, beat_id=beat.pk)
        self.assertTrue(result.success, result.message)
        clock = open_clock_for_beat(beat)
        assert clock is not None
        self.assertEqual((clock.size, clock.filled), (3, 0))
        self.assertEqual(result.data["clock"], {"size": 3, "filled": 0})

    def test_run_beat_without_clock_size_opens_nothing(self) -> None:
        beat = self._situation_beat(0)
        result = RunBeatAction().run(self.lead_gm_actor, beat_id=beat.pk)
        self.assertTrue(result.success, result.message)
        self.assertIsNone(open_clock_for_beat(beat))
        self.assertNotIn("clock", result.data)

    def test_rerun_in_same_scene_reuses_the_open_clock(self) -> None:
        beat = self._situation_beat(3)
        RunBeatAction().run(self.lead_gm_actor, beat_id=beat.pk)
        first = open_clock_for_beat(beat)
        result = RunBeatAction().run(self.lead_gm_actor, beat_id=beat.pk)
        self.assertTrue(result.data["already_running"])
        self.assertEqual(open_clock_for_beat(beat).pk, first.pk)

    def test_second_active_scene_cannot_run_the_beat(self) -> None:
        beat = self._situation_beat(3)
        SceneFactory(running_beat=beat, is_active=True)
        result = RunBeatAction().run(self.lead_gm_actor, beat_id=beat.pk)
        self.assertFalse(result.success)
        self.assertEqual(result.message, "Another active scene is already running this beat.")

    def test_finished_scene_does_not_block(self) -> None:
        beat = self._situation_beat(3)
        SceneFactory(running_beat=beat, is_active=False)
        result = RunBeatAction().run(self.lead_gm_actor, beat_id=beat.pk)
        self.assertTrue(result.success, result.message)

    def test_runnable_rows_carry_clock_size(self) -> None:
        self._situation_beat(4)
        result = GMListRunnableBeatsAction().run(self.lead_gm_actor)
        sizes = {row["id"]: row["clock_size"] for row in result.data["beats"]}
        self.assertIn(4, sizes.values())


class AdvanceClockActionTests(RunBeatActionTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.beat = BeatFactory(episode=self.episode, kind=BeatKind.SITUATION, clock_size=2)
        RunBeatAction().run(self.lead_gm_actor, beat_id=self.beat.pk)

    def test_advance_fills_one(self) -> None:
        result = AdvanceClockAction().run(self.lead_gm_actor)
        self.assertTrue(result.success, result.message)
        self.assertEqual(result.data, {"size": 2, "filled": 1, "filled_now": False})

    def test_advance_by_two_fills_and_completes_expired_after_commit(self) -> None:
        with (
            mock.patch("world.scenes.clock_services.complete_beat_expired") as done,
            self.captureOnCommitCallbacks(execute=True),
        ):
            result = AdvanceClockAction().run(self.lead_gm_actor, by=2)
        self.assertEqual(result.data, {"size": 2, "filled": 2, "filled_now": True})
        done.assert_called_once()

    def test_advance_after_full_is_refused(self) -> None:
        with (
            mock.patch("world.scenes.clock_services.complete_beat_expired"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            AdvanceClockAction().run(self.lead_gm_actor, by=2)
        result = AdvanceClockAction().run(self.lead_gm_actor)
        self.assertFalse(result.success)
        self.assertEqual(result.message, "This scene has no clock to advance.")

    def test_bad_by_is_refused(self) -> None:
        for bad in (0, -1, "x"):
            result = AdvanceClockAction().run(self.lead_gm_actor, by=bad)
            self.assertFalse(result.success, bad)
            self.assertEqual(result.message, "by must be a whole number of at least 1.")

    def test_non_scene_gm_is_refused(self) -> None:
        result = AdvanceClockAction().run(self.player_actor)
        self.assertFalse(result.success)


class ClockFillsAndCompletesEndToEndTests(RunBeatActionTestBase):
    """The spec's headline scenario, unmocked: two combat round starts plus one
    GM advance fill a clock_size=3 clock, and the beat completes EXPIRED for
    real through the on_commit tail (no mock on ``complete_beat_expired``)."""

    def test_two_round_starts_and_an_advance_fill_the_clock_and_complete_expired(self) -> None:
        beat = BeatFactory(episode=self.episode, kind=BeatKind.SITUATION, clock_size=3)
        run_result = RunBeatAction().run(self.lead_gm_actor, beat_id=beat.pk)
        self.assertTrue(run_result.success, run_result.message)

        encounter = CombatEncounterFactory(scene=self.scene, status=RoundStatus.BETWEEN_ROUNDS)
        CombatOpponentFactory(encounter=encounter)

        begin_declaration_phase(encounter)
        encounter.status = RoundStatus.BETWEEN_ROUNDS
        encounter.save(update_fields=["status"])
        begin_declaration_phase(encounter)

        clock = open_clock_for_beat(beat)
        assert clock is not None
        self.assertEqual((clock.filled, clock.size), (2, 3))

        with self.captureOnCommitCallbacks(execute=True):
            advance_result = AdvanceClockAction().run(self.lead_gm_actor)
        self.assertTrue(advance_result.data["filled_now"])

        beat.refresh_from_db()
        self.assertEqual(beat.outcome, BeatOutcome.EXPIRED)
        self.assertTrue(
            BeatCompletion.objects.filter(beat=beat, outcome=BeatOutcome.EXPIRED).exists()
        )
        closed_clock = SceneClock.objects.get(beat=beat)
        self.assertEqual(closed_clock.closed_reason, SceneClockClosedReason.FILLED)
