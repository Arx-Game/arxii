"""Delivery routing on scene action requests (#903)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from actions.factories import ActionTemplateFactory
from world.scenes.action_constants import ActionDelivery
from world.scenes.action_services import create_action_request, resolve_delivery
from world.scenes.factories import (
    PersonaFactory,
    SceneActionRequestFactory,
    SceneFactory,
)


class SceneActionRequestDeliveryFieldTests(TestCase):
    def test_delivery_defaults_to_empty_meaning_template_default(self) -> None:
        request = SceneActionRequestFactory()
        assert request.delivery == ""
        assert list(request.delivery_receivers.all()) == []

    def test_delivery_accepts_choices(self) -> None:
        request = SceneActionRequestFactory(delivery=ActionDelivery.WHISPER)
        assert request.delivery == ActionDelivery.WHISPER


class ResolveDeliveryTests(TestCase):
    def test_explicit_override_wins(self) -> None:
        template = ActionTemplateFactory(default_delivery=ActionDelivery.TABLE_TALK)
        assert (
            resolve_delivery(requested=ActionDelivery.WHISPER, template=template)
            == ActionDelivery.WHISPER
        )

    def test_template_default_when_no_override(self) -> None:
        template = ActionTemplateFactory(default_delivery=ActionDelivery.WHISPER)
        assert resolve_delivery(requested="", template=template) == ActionDelivery.WHISPER

    def test_pose_fallback(self) -> None:
        assert resolve_delivery(requested="", template=None) == ActionDelivery.POSE


class CreateActionRequestDeliveryTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()

    def test_request_stores_explicit_delivery(self) -> None:
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="seduce",
            delivery=ActionDelivery.WHISPER,
        )
        assert request.delivery == ActionDelivery.WHISPER

    def test_table_talk_requires_initiator_at_place(self) -> None:
        with self.assertRaises(ValidationError):
            create_action_request(
                scene=self.scene,
                initiator_persona=self.initiator,
                target_persona=self.target,
                action_key="gossip",
                delivery=ActionDelivery.TABLE_TALK,
            )

    def test_delivery_receivers_set_when_provided(self) -> None:
        extra = PersonaFactory()
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="seduce",
            delivery=ActionDelivery.WHISPER,
            delivery_receivers=[self.target, extra],
        )
        assert set(request.delivery_receivers.all()) == {self.target, extra}
