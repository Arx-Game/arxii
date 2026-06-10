"""ActionTemplate.default_delivery (#903)."""

from django.test import TestCase

from actions.factories import ActionTemplateFactory
from actions.models.action_templates import ActionTemplate
from actions.serializers import ActionTemplateMinimalSerializer
from world.scenes.action_constants import ActionDelivery


class ActionTemplateDefaultDeliveryTests(TestCase):
    def test_default_delivery_defaults_to_pose(self) -> None:
        field = ActionTemplate._meta.get_field("default_delivery")
        assert field.default == ActionDelivery.POSE
        assert field.choices == ActionDelivery.choices

    def test_minimal_serializer_exposes_default_delivery(self) -> None:
        template = ActionTemplateFactory(default_delivery=ActionDelivery.WHISPER)
        data = ActionTemplateMinimalSerializer(template).data
        assert data["default_delivery"] == ActionDelivery.WHISPER
