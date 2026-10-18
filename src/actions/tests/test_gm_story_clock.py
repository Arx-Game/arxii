"""The scene clock filled by combat round starts (#3567).

Every GM path of the clock is typed or dispatched in
``integration_tests/test_sharing_a_story_journeys.py`` (``PacingABeatByItsClock``):
``run_beat`` opening a clock of the authored size or none, reusing it on a rerun, one
scene running a beat at a time, the runnable list carrying each clock size, ``story
clock [n]`` advancing and filling it, a bad count, a full clock, a player and a stranger
GM refused. What stays here is the combat leg: two encounter round starts ticking the
clock before the GM's advance fills it, which belongs with the combat ledger.
"""

from __future__ import annotations

from actions.definitions.gm_story import AdvanceClockAction, RunBeatAction
from actions.tests.test_gm_story_run_beat import RunBeatActionTestBase
from world.combat.factories import CombatEncounterFactory, CombatOpponentFactory
from world.combat.services import begin_declaration_phase
from world.scenes.clock_services import open_clock_for_beat
from world.scenes.constants import RoundStatus, SceneClockClosedReason
from world.scenes.models import SceneClock
from world.stories.constants import BeatKind, BeatOutcome
from world.stories.factories import BeatFactory
from world.stories.models import BeatCompletion


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
