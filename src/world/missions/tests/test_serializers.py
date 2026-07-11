"""Mission serializer field-surface tests (#1899, #888)."""

from django.test import TestCase
from rest_framework.serializers import ValidationError as DRFValidationError

from world.areas.factories import AreaFactory
from world.missions.constants import NodeLocationMode
from world.missions.factories import MissionInstanceFactory, MissionNodeFactory
from world.missions.serializers import MissionInstanceSerializer, MissionNodeSerializer


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
