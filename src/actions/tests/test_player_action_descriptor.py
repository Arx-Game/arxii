from django.test import TestCase

from actions.constants import ActionBackend, TargetKind
from actions.types import (
    ActionRef,
    PlayerAction,
    StrainAvailability,
    TargetFilters,
    TargetSpec,
    TargetType,
)


class PlayerActionDescriptorTests(TestCase):
    def _minimal_ref(self) -> ActionRef:
        return ActionRef(backend=ActionBackend.REGISTRY, registry_key="say")

    def test_target_spec_defaults_to_none(self) -> None:
        action = PlayerAction(
            backend=ActionBackend.REGISTRY,
            display_name="Say",
            ref=self._minimal_ref(),
        )
        self.assertIsNone(action.target_spec)

    def test_enhancements_default_to_empty_tuple(self) -> None:
        action = PlayerAction(
            backend=ActionBackend.REGISTRY,
            display_name="Say",
            ref=self._minimal_ref(),
        )
        self.assertEqual(action.enhancements, ())

    def test_strain_defaults_to_none(self) -> None:
        action = PlayerAction(
            backend=ActionBackend.REGISTRY,
            display_name="Say",
            ref=self._minimal_ref(),
        )
        self.assertIsNone(action.strain)

    def test_full_targeted_action_with_strain(self) -> None:
        action = PlayerAction(
            backend=ActionBackend.CHALLENGE,
            display_name="Intimidate",
            ref=self._minimal_ref(),
            target_spec=TargetSpec(
                kind=TargetKind.PERSONA,
                cardinality=TargetType.SINGLE,
                filters=TargetFilters(in_same_scene=True, exclude_self=True),
            ),
            strain=StrainAvailability(cap=14),
        )
        self.assertEqual(action.target_spec.kind, TargetKind.PERSONA)
        self.assertEqual(action.strain.cap, 14)
