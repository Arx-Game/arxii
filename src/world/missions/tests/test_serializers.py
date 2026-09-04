"""Mission serializer field-surface tests (#1899, #888, #3568)."""

from django.test import TestCase
from rest_framework.serializers import ValidationError as DRFValidationError

from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.missions.constants import NodeLocationMode, OptionKind, OptionSource
from world.missions.factories import (
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionOptionFactory,
)
from world.missions.serializers import (
    MissionInstanceSerializer,
    MissionNodeSerializer,
    MissionOptionSerializer,
)
from world.stories.constants import BeatOutcome


class MissionInstanceSerializerTests(TestCase):
    def test_serializer_includes_is_paused_field(self) -> None:
        instance = MissionInstanceFactory(is_paused=True)
        data = MissionInstanceSerializer(instance).data
        assert data["is_paused"] is True


class MissionNodeSerializerTests(TestCase):
    def test_area_mode_with_target_area_is_valid(self) -> None:
        area = AreaFactory()
        node = MissionNodeFactory(location_mode=NodeLocationMode.AREA, target_area=area)
        data = MissionNodeSerializer(node).data
        assert data["location_mode"] == NodeLocationMode.AREA
        assert data["target_area"] == area.pk

    def test_target_area_rejected_without_area_mode(self) -> None:
        area = AreaFactory()
        node = MissionNodeFactory(location_mode=NodeLocationMode.ANYWHERE)
        serializer = MissionNodeSerializer(
            node,
            data={"location_mode": NodeLocationMode.ANYWHERE, "target_area": area.pk},
            partial=True,
        )
        assert serializer.is_valid() is False
        assert "target_area" in serializer.errors

    def test_area_mode_without_target_area_rejected(self) -> None:
        node = MissionNodeFactory(location_mode=NodeLocationMode.ANYWHERE)
        serializer = MissionNodeSerializer(
            node,
            data={"location_mode": NodeLocationMode.AREA},
            partial=True,
        )
        with self.assertRaises(DRFValidationError):
            serializer.is_valid(raise_exception=True)

    def test_track_fields_round_trip(self) -> None:
        target = MissionNodeFactory()
        node = MissionNodeFactory(
            track_successes=3,
            track_failures=2,
            track_success_target=target,
            track_success_beat_outcome=BeatOutcome.SUCCESS,
        )
        data = MissionNodeSerializer(node).data
        assert data["track_successes"] == 3
        assert data["track_failures"] == 2
        assert data["track_success_target"] == target.pk
        assert data["track_failure_target"] is None
        assert data["track_success_beat_outcome"] == BeatOutcome.SUCCESS
        assert data["track_failure_beat_outcome"] == ""

    def test_track_threshold_mismatch_rejected_as_400(self) -> None:
        """#3568 ruling 12: MissionNode.clean() now reaches the API via validate()."""
        node = MissionNodeFactory()
        serializer = MissionNodeSerializer(
            node,
            data={"track_successes": 3, "track_failures": 0},
            partial=True,
        )
        assert serializer.is_valid() is False
        assert "track_failures" in serializer.errors


class MissionOptionSerializerTests(TestCase):
    def test_opposition_fields_round_trip(self) -> None:
        sheet = CharacterSheetFactory()
        check_type = CheckTypeFactory()
        option = MissionOptionFactory(
            option_kind=OptionKind.CONTEST,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=check_type,
            opposition_sheet=sheet,
            opposition_check_type=check_type,
        )
        data = MissionOptionSerializer(option).data
        assert data["opposition_sheet"] == sheet.pk
        assert data["opposition_check_type"] == check_type.pk

    def test_contest_missing_opposition_sheet_rejected_as_400(self) -> None:
        """#3568 ruling 12: MissionOption.clean() now reaches the API via validate()."""
        node = MissionNodeFactory()
        check_type = CheckTypeFactory()
        serializer = MissionOptionSerializer(
            data={
                "node": node.pk,
                "order": 1,
                "option_kind": OptionKind.CONTEST,
                "source_kind": OptionSource.AUTHORED,
                "authored_check_type": check_type.pk,
                "opposition_check_type": check_type.pk,
            }
        )
        assert serializer.is_valid() is False
        assert "opposition_sheet" in serializer.errors
