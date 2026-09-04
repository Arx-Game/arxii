"""Scene clock services (#3567): open, tick, fill, close."""

from __future__ import annotations

from unittest import mock

from django.test import TestCase
from django.utils import timezone
from evennia.utils.test_resources import EvenniaTestCase

from world.scenes.clock_services import (
    close_open_clock_for_beat,
    close_scene_clocks,
    open_clock_for_beat,
    start_scene_clock,
    tick_scene_clock,
)
from world.scenes.constants import SceneClockClosedReason
from world.scenes.factories import SceneFactory
from world.scenes.models import SceneClock
from world.stories.factories import BeatFactory


class StartSceneClockTests(TestCase):
    def test_zero_size_opens_nothing(self) -> None:
        beat = BeatFactory(clock_size=0)
        scene = SceneFactory(running_beat=beat)
        self.assertIsNone(start_scene_clock(scene, beat))
        self.assertFalse(SceneClock.objects.filter(beat=beat).exists())

    def test_opens_clock_of_authored_size(self) -> None:
        beat = BeatFactory(clock_size=3)
        scene = SceneFactory(running_beat=beat)
        clock = start_scene_clock(scene, beat)
        assert clock is not None
        self.assertEqual((clock.size, clock.filled, clock.scene_id), (3, 0, scene.pk))

    def test_second_start_returns_the_open_clock(self) -> None:
        beat = BeatFactory(clock_size=3)
        scene = SceneFactory(running_beat=beat)
        first = start_scene_clock(scene, beat)
        second = start_scene_clock(scene, beat)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(SceneClock.objects.filter(beat=beat).count(), 1)

    def test_closed_clock_is_not_reused(self) -> None:
        beat = BeatFactory(clock_size=3)
        scene = SceneFactory(running_beat=beat)
        first = start_scene_clock(scene, beat)
        close_open_clock_for_beat(beat, SceneClockClosedReason.SCENE_ENDED)
        second = start_scene_clock(scene, beat)
        self.assertNotEqual(first.pk, second.pk)
        self.assertIsNone(second.closed_at)


class TickSceneClockTests(TestCase):
    def setUp(self) -> None:
        self.beat = BeatFactory(clock_size=3)
        self.scene = SceneFactory(running_beat=self.beat)
        self.clock = start_scene_clock(self.scene, self.beat)

    def test_no_running_beat_is_a_noop(self) -> None:
        scene = SceneFactory(running_beat=None)
        self.assertIsNone(tick_scene_clock(scene))

    def test_tick_fills_one(self) -> None:
        with mock.patch("world.scenes.clock_services.complete_beat_expired") as done:
            clock = tick_scene_clock(self.scene)
        assert clock is not None
        self.assertEqual(clock.filled, 1)
        self.assertIsNone(clock.closed_at)
        done.assert_not_called()

    def test_fill_closes_and_completes_after_commit(self) -> None:
        tick_scene_clock(self.scene, by=2)
        with (
            mock.patch("world.scenes.clock_services.complete_beat_expired") as done,
            self.captureOnCommitCallbacks(execute=True),
        ):
            clock = tick_scene_clock(self.scene)
            done.assert_not_called()
        assert clock is not None
        self.assertEqual(clock.filled, 3)
        self.assertEqual(clock.closed_reason, SceneClockClosedReason.FILLED)
        self.assertIsNotNone(clock.closed_at)
        done.assert_called_once()
        self.assertEqual(done.call_args.args[0].pk, self.beat.pk)

    def test_tick_never_passes_full(self) -> None:
        with (
            mock.patch("world.scenes.clock_services.complete_beat_expired"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            clock = tick_scene_clock(self.scene, by=10)
        self.assertEqual(clock.filled, 3)

    def test_tick_after_full_is_a_noop(self) -> None:
        with (
            mock.patch("world.scenes.clock_services.complete_beat_expired") as done,
            self.captureOnCommitCallbacks(execute=True),
        ):
            tick_scene_clock(self.scene, by=3)
            self.assertIsNone(tick_scene_clock(self.scene))
        done.assert_called_once()

    def test_fill_does_not_complete_an_already_resolved_beat(self) -> None:
        from world.stories.constants import BeatOutcome

        tick_scene_clock(self.scene, by=2)
        self.beat.outcome = BeatOutcome.SUCCESS
        self.beat.save(update_fields=["outcome"])
        with (
            mock.patch("world.scenes.clock_services.complete_beat_expired") as done,
            self.captureOnCommitCallbacks(execute=True),
        ):
            tick_scene_clock(self.scene)
        done.assert_not_called()

    def test_battle_scene_running_the_same_beat_ticks_the_same_clock(self) -> None:
        other_scene = SceneFactory(running_beat=self.beat)
        clock = tick_scene_clock(other_scene)
        self.assertEqual(clock.pk, self.clock.pk)
        self.assertEqual(clock.filled, 1)


class CloseTests(TestCase):
    def test_close_scene_clocks_only_touches_that_scene(self) -> None:
        beat_a = BeatFactory(clock_size=2)
        beat_b = BeatFactory(clock_size=2)
        scene = SceneFactory(running_beat=beat_a)
        other = SceneFactory(running_beat=beat_b)
        start_scene_clock(scene, beat_a)
        start_scene_clock(other, beat_b)
        self.assertEqual(close_scene_clocks(scene, SceneClockClosedReason.SCENE_ENDED), 1)
        self.assertIsNone(open_clock_for_beat(beat_a))
        self.assertIsNotNone(open_clock_for_beat(beat_b))

    def test_close_open_clock_for_beat_leaves_filled_alone(self) -> None:
        beat = BeatFactory(clock_size=1)
        scene = SceneFactory(running_beat=beat)
        with (
            mock.patch("world.scenes.clock_services.complete_beat_expired"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            start_scene_clock(scene, beat)
            tick_scene_clock(scene)
        self.assertIsNone(close_open_clock_for_beat(beat, SceneClockClosedReason.COMPLETED))
        clock = SceneClock.objects.get(beat=beat)
        self.assertEqual(clock.closed_reason, SceneClockClosedReason.FILLED)


class CompletionTailClosesClockTests(EvenniaTestCase):
    """Any completion routed through ``_create_completion_and_fire_pool`` closes
    an open clock COMPLETED, regardless of outcome. Driven here via
    ``complete_beat_expired`` (EXPIRED), using the same fixture helper
    ``test_services_expiry.py`` uses to build a beat with an active progress."""

    def test_completion_tail_closes_the_clock_completed(self) -> None:
        from world.stories.services.beats import complete_beat_expired
        from world.stories.tests.test_services_expiry import _character_beat

        _sheet, beat, _progress = _character_beat(clock_size=2)
        scene = SceneFactory(running_beat=beat)
        start_scene_clock(scene, beat)
        with self.captureOnCommitCallbacks(execute=True):
            complete_beat_expired(beat)
        clock = SceneClock.objects.get(beat=beat)
        self.assertEqual(clock.closed_reason, SceneClockClosedReason.COMPLETED)


class FinishSceneHookTests(TestCase):
    def test_finish_scene_closes_the_clock_scene_ended(self) -> None:
        from world.scenes.scene_admin_services import finish_scene_full

        beat = BeatFactory(clock_size=2)
        scene = SceneFactory(running_beat=beat)
        start_scene_clock(scene, beat)
        finish_scene_full(scene)
        clock = SceneClock.objects.get(beat=beat)
        self.assertEqual(clock.closed_reason, SceneClockClosedReason.SCENE_ENDED)
        scene.refresh_from_db()
        self.assertIsNone(scene.running_beat_id)
        self.assertLessEqual(clock.closed_at, timezone.now())
