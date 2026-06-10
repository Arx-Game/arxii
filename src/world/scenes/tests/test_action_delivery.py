"""Delivery routing on scene action requests (#903)."""

from unittest.mock import MagicMock

from django.core.exceptions import ValidationError
from django.test import TestCase

from actions.constants import ResolutionPhase
from actions.factories import ActionTemplateFactory
from actions.types import PendingActionResolution, StepResult
from world.scenes.action_constants import ActionDelivery
from world.scenes.action_services import (
    _create_result_interaction,
    create_action_request,
    resolve_delivery,
)
from world.scenes.constants import InteractionMode, ScenePrivacyMode
from world.scenes.factories import (
    PersonaFactory,
    PlaceFactory,
    PlacePresenceFactory,
    SceneActionRequestFactory,
    SceneFactory,
)
from world.scenes.interaction_services import can_view_interaction
from world.scenes.types import EnhancedSceneActionResult


def _make_enhanced_result(action_key: str = "persuade") -> EnhancedSceneActionResult:
    """Minimal result for routing tests — mirrors test_action_views' fixture."""
    check_result = MagicMock()
    check_result.outcome_name = "Success"
    check_result.success_level = 1
    main_result = StepResult(
        step_label="main",
        check_result=check_result,
        consequence_id=None,
    )
    action_resolution = PendingActionResolution(
        template_id=1,
        character_id=1,
        target_difficulty=45,
        resolution_context_data={"character_id": 1, "challenge_instance_id": None},
        current_phase=ResolutionPhase.COMPLETE,
        main_result=main_result,
    )
    return EnhancedSceneActionResult(
        action_resolution=action_resolution,
        action_key=action_key,
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


class ResultInteractionRoutingTests(TestCase):
    """The result interaction rides the audience plumbing #900 made private."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()
        cls.outsider = PersonaFactory()

    def _request(self, **kwargs):
        return SceneActionRequestFactory(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            **kwargs,
        )

    def test_whisper_delivery_creates_receiver_scoped_whisper(self) -> None:
        request = self._request(delivery=ActionDelivery.WHISPER)
        interaction = _create_result_interaction(
            action_request=request, result=_make_enhanced_result()
        )
        assert interaction.mode == InteractionMode.WHISPER
        assert can_view_interaction(interaction, self.target) is True
        assert can_view_interaction(interaction, self.initiator) is True
        assert can_view_interaction(interaction, self.outsider) is False

    def test_whisper_delivery_honors_explicit_receivers(self) -> None:
        confidant = PersonaFactory()
        request = self._request(delivery=ActionDelivery.WHISPER)
        request.delivery_receivers.set([self.target, confidant])
        interaction = _create_result_interaction(
            action_request=request, result=_make_enhanced_result()
        )
        assert can_view_interaction(interaction, confidant) is True
        assert can_view_interaction(interaction, self.outsider) is False

    def test_pose_delivery_unchanged_public(self) -> None:
        request = self._request(delivery=ActionDelivery.POSE)
        interaction = _create_result_interaction(
            action_request=request, result=_make_enhanced_result()
        )
        assert interaction.mode == InteractionMode.ACTION
        assert can_view_interaction(interaction, self.outsider) is True

    def test_blank_delivery_uses_template_default(self) -> None:
        template = ActionTemplateFactory(default_delivery=ActionDelivery.WHISPER)
        request = self._request(delivery="", action_template=template)
        interaction = _create_result_interaction(
            action_request=request, result=_make_enhanced_result()
        )
        assert interaction.mode == InteractionMode.WHISPER
        assert can_view_interaction(interaction, self.outsider) is False

    def test_table_talk_delivery_scopes_to_place(self) -> None:
        place = PlaceFactory()
        PlacePresenceFactory(place=place, persona=self.initiator)
        PlacePresenceFactory(place=place, persona=self.target)
        request = self._request(delivery=ActionDelivery.TABLE_TALK)
        interaction = _create_result_interaction(
            action_request=request, result=_make_enhanced_result()
        )
        assert interaction.place_id == place.pk
        assert can_view_interaction(interaction, self.target) is True
        assert can_view_interaction(interaction, self.outsider) is False

    def test_table_talk_without_place_falls_back_to_public(self) -> None:
        request = self._request(delivery=ActionDelivery.TABLE_TALK)
        interaction = _create_result_interaction(
            action_request=request, result=_make_enhanced_result()
        )
        assert interaction.place_id is None
        assert can_view_interaction(interaction, self.outsider) is True
