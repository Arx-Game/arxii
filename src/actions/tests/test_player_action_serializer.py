"""Tests for PlayerActionSerializer covering target_spec, enhancements, strain."""

from django.test import TestCase

from actions.constants import ActionBackend, ActionCategory, TargetKind
from actions.serializers import (
    ActionRefSerializer,
    DispatchActionSerializer,
    PlayerActionSerializer,
)
from actions.types import (
    ActionRef,
    PlayerAction,
    StrainAvailability,
    TargetFilters,
    TargetSpec,
    TargetType,
)


class PlayerActionSerializerTests(TestCase):
    def test_targeted_action_serialization(self) -> None:
        action = PlayerAction(
            backend=ActionBackend.CHALLENGE,
            display_name="Intimidate",
            ref=ActionRef(backend=ActionBackend.CHALLENGE, challenge_instance_id=1),
            target_spec=TargetSpec(
                kind=TargetKind.PERSONA,
                cardinality=TargetType.SINGLE,
                filters=TargetFilters(in_same_scene=True, exclude_self=True),
            ),
            strain=StrainAvailability(cap=10),
        )
        data = PlayerActionSerializer(action).data
        self.assertEqual(data["target_spec"]["kind"], "persona")
        self.assertEqual(data["target_spec"]["cardinality"], "single")
        self.assertTrue(data["target_spec"]["filters"]["in_same_scene"])
        self.assertEqual(data["strain"]["cap"], 10)
        self.assertEqual(list(data["enhancements"]), [])

    def test_self_action_has_null_target_spec(self) -> None:
        action = PlayerAction(
            backend=ActionBackend.REGISTRY,
            display_name="Look",
            ref=ActionRef(backend=ActionBackend.REGISTRY, registry_key="look"),
        )
        data = PlayerActionSerializer(action).data
        self.assertIsNone(data["target_spec"])
        self.assertIsNone(data["strain"])

    def test_action_category_serialized(self) -> None:
        action = PlayerAction(
            backend=ActionBackend.COMBAT,
            display_name="Psychic Lance",
            ref=ActionRef(backend=ActionBackend.COMBAT, technique_id=7),
            action_category=ActionCategory.MENTAL,
        )
        data = PlayerActionSerializer(action).data
        self.assertEqual(data["action_category"], "mental")

    def test_action_category_null_when_unset(self) -> None:
        action = PlayerAction(
            backend=ActionBackend.REGISTRY,
            display_name="Look",
            ref=ActionRef(backend=ActionBackend.REGISTRY, registry_key="look"),
        )
        data = PlayerActionSerializer(action).data
        self.assertIsNone(data["action_category"])


class ActionRefSerializerPositionIdTests(TestCase):
    """ActionRefSerializer includes position_id in output for a move ref."""

    def test_position_id_serialized_in_ref_output(self) -> None:
        """position_id is present and correct when serializing an ActionRef for a move."""
        ref = ActionRef(
            backend=ActionBackend.REGISTRY,
            registry_key="move_to_position",
            position_id=42,
        )
        data = ActionRefSerializer(ref).data
        self.assertEqual(data["position_id"], 42)

    def test_position_id_absent_when_none(self) -> None:
        """position_id is absent (or null) in output when not set on the ActionRef."""
        ref = ActionRef(backend=ActionBackend.REGISTRY, registry_key="look")
        data = ActionRefSerializer(ref).data
        # Field is optional; when null it may be absent or None — both are correct.
        self.assertIsNone(data.get("position_id"))


class DispatchActionSerializerPositionIdTests(TestCase):
    """DispatchActionSerializer round-trips position_id through to ActionRef."""

    def test_position_id_forwarded_to_action_ref(self) -> None:
        """Payload containing ref.position_id produces an ActionRef with that position_id set."""
        payload = {
            "ref": {
                "backend": "registry",
                "registry_key": "move_to_position",
                "position_id": 7,
            },
            "kwargs": {},
        }
        serializer = DispatchActionSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        ref = serializer.validated_data["ref"]
        self.assertIsInstance(ref, ActionRef)
        self.assertEqual(ref.position_id, 7)

    def test_position_id_defaults_to_none_when_absent(self) -> None:
        """When position_id is omitted from payload, ActionRef.position_id is None."""
        payload = {
            "ref": {
                "backend": "registry",
                "registry_key": "look",
            },
            "kwargs": {},
        }
        serializer = DispatchActionSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        ref = serializer.validated_data["ref"]
        self.assertIsNone(ref.position_id)
