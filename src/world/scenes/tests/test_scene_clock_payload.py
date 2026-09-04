"""SceneDetailSerializer.clock (#3567): every viewer sees size and fill, never the beat."""

from __future__ import annotations

from django.test import TestCase

from world.scenes.clock_services import start_scene_clock, tick_scene_clock
from world.scenes.factories import SceneFactory
from world.scenes.serializers import SceneDetailSerializer
from world.stories.factories import BeatFactory


class SceneClockPayloadTests(TestCase):
    def test_no_running_beat_is_null(self) -> None:
        data = SceneDetailSerializer(SceneFactory(running_beat=None)).data
        self.assertIsNone(data["clock"])

    def test_beat_without_clock_is_null(self) -> None:
        data = SceneDetailSerializer(SceneFactory(running_beat=BeatFactory(clock_size=0))).data
        self.assertIsNone(data["clock"])

    def test_open_clock_carries_size_and_filled_only(self) -> None:
        beat = BeatFactory(clock_size=4)
        scene = SceneFactory(running_beat=beat)
        start_scene_clock(scene, beat)
        tick_scene_clock(scene)
        data = SceneDetailSerializer(scene).data
        self.assertEqual(dict(data["clock"]), {"size": 4, "filled": 1})
        # The exact-dict equality above already proves no beat id rides the payload
        # (SceneClockSerializer.Meta.fields is size/filled only); a substring check
        # against str(beat.pk) is flaky here since a fresh test DB can hand out a
        # beat pk of 1, coincidentally equal to filled=1 regardless of any leak.
        self.assertNotIn("id", dict(data["clock"]))

    def test_battle_scene_running_the_same_beat_reads_the_same_clock(self) -> None:
        beat = BeatFactory(clock_size=4)
        scene = SceneFactory(running_beat=beat)
        start_scene_clock(scene, beat)
        other = SceneFactory(running_beat=beat)
        self.assertEqual(dict(SceneDetailSerializer(other).data["clock"]), {"size": 4, "filled": 0})
