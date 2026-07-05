"""MissionInstanceSerializer field-surface tests (#1899) — is_paused visibility."""

from django.test import TestCase

from world.missions.factories import MissionInstanceFactory
from world.missions.serializers import MissionInstanceSerializer


class MissionInstanceSerializerTests(TestCase):
    def test_serializer_includes_is_paused_field(self) -> None:
        instance = MissionInstanceFactory(is_paused=True)
        data = MissionInstanceSerializer(instance).data
        assert data["is_paused"] is True
