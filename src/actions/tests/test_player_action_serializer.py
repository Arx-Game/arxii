"""Tests for PlayerActionSerializer covering target_spec, enhancements, strain."""

from django.test import TestCase

from actions.constants import ActionBackend, TargetKind
from actions.serializers import PlayerActionSerializer
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
