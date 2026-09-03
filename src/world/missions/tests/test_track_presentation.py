"""Track progress on the beat payloads (#3568): the party sees counts only.

``beat_for``/``group_beat`` populate ``BeatView.track``/``GroupBeatView.track``
via ``services.play._track_view``: None off a track node, else the run's
``MissionTrackProgress`` counter (0/0 when the run hasn't logged a deed here
yet) paired with the node's authored thresholds. Serializer coverage confirms
the four ints round-trip (and stay null off a track node) through the DRF
read-only mirrors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.missions.constants import ConflictMode, OptionKind, OptionSource
from world.missions.factories import (
    MissionNodeFactory,
    MissionOptionFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionTrackProgress
from world.missions.serializers import BeatViewSerializer, GroupBeatViewSerializer
from world.missions.services.play import beat_for, group_beat
from world.missions.services.run import staff_assign_mission
from world.missions.types import TrackView

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.missions.models import MissionInstance, MissionNode, MissionTemplate


def _pc() -> ObjectDB:
    """A playable character with a sheet, no location."""
    character = CharacterFactory()
    CharacterSheetFactory(character=character)
    return character


def _track_template(name: str) -> tuple[MissionTemplate, MissionNode]:
    """A single-node template whose entry is a track node (2 successes / 2 failures)."""
    template = MissionTemplateFactory(name=name)
    track = MissionNodeFactory(
        template=template,
        key="track",
        is_entry=True,
        conflict_mode=ConflictMode.GROUP_VOTE,
        track_successes=2,
        track_failures=2,
    )
    MissionOptionFactory(
        node=track,
        order=0,
        option_kind=OptionKind.BRANCH,
        source_kind=OptionSource.AUTHORED,
        authored_ic_framing="Push on.",
        branch_target=None,
    )
    return template, track


def _plain_template(name: str) -> tuple[MissionTemplate, MissionNode]:
    """A single-node template whose entry is NOT a track node."""
    template = MissionTemplateFactory(name=name)
    entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
    MissionOptionFactory(
        node=entry,
        order=0,
        option_kind=OptionKind.BRANCH,
        source_kind=OptionSource.AUTHORED,
        authored_ic_framing="Go.",
        branch_target=None,
    )
    return template, entry


def _bump_progress(
    instance: MissionInstance, node: MissionNode, *, successes: int, failures: int
) -> None:
    """Set the run's track counter via instance.save(), not a bulk update.

    A bulk ``.update()`` on the queryset would leave the idmapper's already-
    cached row stale (the same pk gets fetched back unchanged).
    """
    progress = MissionTrackProgress.objects.get(instance=instance, node=node)
    progress.successes = successes
    progress.failures = failures
    progress.save()


class BeatForTrackViewTests(TestCase):
    def test_beat_for_returns_track_progress(self) -> None:
        character = _pc()
        template, track = _track_template("beat-track")
        instance = staff_assign_mission(template, character)
        _bump_progress(instance, track, successes=1, failures=0)

        beat = beat_for(instance, character)

        self.assertEqual(beat.track, TrackView(successes=1, needed=2, failures=0, allowed=2))

    def test_beat_for_track_is_none_off_a_track_node(self) -> None:
        character = _pc()
        template, _entry = _plain_template("beat-no-track")
        instance = staff_assign_mission(template, character)

        beat = beat_for(instance, character)

        self.assertIsNone(beat.track)

    def test_beat_view_serializer_carries_the_four_ints(self) -> None:
        character = _pc()
        template, track = _track_template("beat-track-serializer")
        instance = staff_assign_mission(template, character)
        _bump_progress(instance, track, successes=1, failures=0)

        beat = beat_for(instance, character)
        data = BeatViewSerializer(beat).data

        self.assertEqual(data["track"], {"successes": 1, "needed": 2, "failures": 0, "allowed": 2})

    def test_beat_view_serializer_track_is_null_off_a_track_node(self) -> None:
        character = _pc()
        template, _entry = _plain_template("beat-no-track-serializer")
        instance = staff_assign_mission(template, character)

        beat = beat_for(instance, character)
        data = BeatViewSerializer(beat).data

        self.assertIsNone(data["track"])


class GroupBeatTrackViewTests(TestCase):
    def test_group_beat_returns_track_progress(self) -> None:
        character = _pc()
        template, track = _track_template("group-beat-track")
        instance = staff_assign_mission(template, character)
        _bump_progress(instance, track, successes=1, failures=0)

        result = group_beat(instance, character)

        self.assertIsNotNone(result.group_beat)
        self.assertEqual(
            result.group_beat.track, TrackView(successes=1, needed=2, failures=0, allowed=2)
        )

    def test_group_beat_track_is_none_off_a_track_node(self) -> None:
        character = _pc()
        template, _entry = _plain_template("group-beat-no-track")
        instance = staff_assign_mission(template, character)

        result = group_beat(instance, character)

        self.assertIsNotNone(result.group_beat)
        self.assertIsNone(result.group_beat.track)

    def test_group_beat_view_serializer_carries_the_four_ints(self) -> None:
        character = _pc()
        template, track = _track_template("group-beat-track-serializer")
        instance = staff_assign_mission(template, character)
        _bump_progress(instance, track, successes=1, failures=0)

        result = group_beat(instance, character)
        data = GroupBeatViewSerializer(result.group_beat).data

        self.assertEqual(data["track"], {"successes": 1, "needed": 2, "failures": 0, "allowed": 2})
