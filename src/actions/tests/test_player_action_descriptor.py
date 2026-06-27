from django.test import TestCase

from actions.constants import ActionBackend, TargetKind
from actions.types import (
    ActionRef,
    AnchorOption,
    FuryTierOption,
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


def _base_player_action() -> PlayerAction:
    return PlayerAction(
        backend=ActionBackend.COMBAT,
        display_name="Cast",
        ref=ActionRef(backend=ActionBackend.COMBAT, technique_id=1),
    )


class TestPlayerActionFurySoulfrayDefaults(TestCase):
    def test_soulfray_warning_defaults_none(self) -> None:
        assert _base_player_action().soulfray_warning is None

    def test_available_fury_tiers_defaults_empty(self) -> None:
        assert _base_player_action().available_fury_tiers == ()

    def test_eligible_fury_anchors_defaults_empty(self) -> None:
        assert _base_player_action().eligible_fury_anchors == ()

    def test_fury_tier_option_is_frozen(self) -> None:
        opt = FuryTierOption(
            id=1,
            name="Unleashed",
            depth=2,
            control_penalty=4,
            intensity_bonus=5,
            berserk_severity=3,
        )
        assert opt.depth == 2
        try:
            opt.depth = 9  # type: ignore[misc]
        except AttributeError:
            return
        self.fail("FuryTierOption must be frozen")

    def test_anchor_option_fields(self) -> None:
        opt = AnchorOption(id=7, name="Rival", provocation_cap=3)
        assert opt.provocation_cap == 3
