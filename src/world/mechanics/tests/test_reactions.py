"""Tests for the shared dispatch_capability_reaction helper (#1273, Task 4).

Covers:
- dispatch_capability_reaction returns None when no matching challenge actions exist.
- dispatch_capability_reaction selects by capability name and invokes outcome_fn.
- dispatch_capability_reaction falls back to the first action when the approach
  name does not match any capability_source.

These tests stub get_available_actions and resolve_challenge so the helper can
be exercised without a wired DB challenge/character state.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.mechanics.constants import CapabilitySourceType, ResolutionType
from world.mechanics.reactions import dispatch_capability_reaction
from world.mechanics.types import AvailableAction, CapabilitySource, ChallengeResolutionResult


def _make_resolution_result(
    *,
    challenge_name: str = "Test Challenge",
    resolution_type: str = ResolutionType.DESTROY,
    success_level: int = 1,
) -> ChallengeResolutionResult:
    """Build a minimal ChallengeResolutionResult stub for assertion purposes."""
    check_result = MagicMock()
    check_result.success_level = success_level

    consequence = MagicMock()

    return ChallengeResolutionResult(
        challenge_instance_id=1,
        challenge_name=challenge_name,
        approach_name="test_approach",
        check_result=check_result,
        consequence=consequence,
        applied_effects=[],
        resolution_type=resolution_type,
        challenge_deactivated=True,
        display_consequences=[],
    )


def _make_capability_source(capability_name: str = "telekinesis") -> CapabilitySource:
    return CapabilitySource(
        capability_name=capability_name,
        capability_id=1,
        value=10,
        source_type=CapabilitySourceType.TECHNIQUE,
        source_name="Test Technique",
        source_id=1,
    )


def _make_available_action(
    *,
    challenge_name: str = "Interpose",
    target_object_id: int = 99,
    capability_name: str = "telekinesis",
    instance_id: int = 1,
) -> AvailableAction:
    """Build a minimal AvailableAction with a mock ChallengeInstance."""
    cap_source = _make_capability_source(capability_name)
    instance = MagicMock()
    instance.target_object_id = target_object_id
    instance.pk = instance_id

    approach = MagicMock()

    return AvailableAction(
        application_id=1,
        application_name="Test App",
        capability_source=cap_source,
        challenge_instance_id=instance_id,
        challenge_name=challenge_name,
        approach_id=1,
        check_type_name="Reflexes",
        display_name="Test Action",
        custom_description="",
        resolved_challenge_instance=instance,
        resolved_challenge_approach=approach,
    )


class DispatchCapabilityReactionNoActionsTest(TestCase):
    """Returns None when no actions match the challenge_name + target_object."""

    def test_returns_none_when_no_matching_actions(self) -> None:
        actor = MagicMock()
        actor.location = MagicMock()
        target = MagicMock()
        target.id = 99

        outcome_fn = MagicMock()

        # get_available_actions returns actions for a different challenge
        other_action = _make_available_action(
            challenge_name="Other Challenge",
            target_object_id=99,
        )

        with patch("world.mechanics.services.get_available_actions", return_value=[other_action]):
            result = dispatch_capability_reaction(
                actor,
                target,
                challenge_name="Interpose",
                approach="telekinesis",
                error_msg="no match",
                outcome_fn=outcome_fn,
            )

        self.assertIsNone(result)
        outcome_fn.assert_not_called()

    def test_returns_none_when_actions_for_different_target(self) -> None:
        actor = MagicMock()
        actor.location = MagicMock()
        target = MagicMock()
        target.id = 99

        outcome_fn = MagicMock()

        # action matches challenge_name but targets a different object (id=77)
        other_target_action = _make_available_action(
            challenge_name="Interpose",
            target_object_id=77,
        )

        with patch(
            "world.mechanics.services.get_available_actions",
            return_value=[other_target_action],
        ):
            result = dispatch_capability_reaction(
                actor,
                target,
                challenge_name="Interpose",
                approach="telekinesis",
                error_msg="no match",
                outcome_fn=outcome_fn,
            )

        self.assertIsNone(result)
        outcome_fn.assert_not_called()

    def test_returns_none_when_resolved_challenge_instance_is_none(self) -> None:
        actor = MagicMock()
        actor.location = MagicMock()
        target = MagicMock()
        target.id = 99

        outcome_fn = MagicMock()

        action = _make_available_action(challenge_name="Interpose", target_object_id=99)
        action.resolved_challenge_instance = None  # simulate unresolved

        with patch("world.mechanics.services.get_available_actions", return_value=[action]):
            result = dispatch_capability_reaction(
                actor,
                target,
                challenge_name="Interpose",
                approach="telekinesis",
                error_msg="no match",
                outcome_fn=outcome_fn,
            )

        self.assertIsNone(result)
        outcome_fn.assert_not_called()


class DispatchCapabilityReactionSelectionTest(TestCase):
    """Selects action by capability name and invokes outcome_fn with the result."""

    def test_selects_matching_capability_and_calls_outcome_fn(self) -> None:
        actor = MagicMock()
        actor.location = MagicMock()
        target = MagicMock()
        target.id = 99

        resolution = _make_resolution_result()
        outcome_fn = MagicMock()

        tele_action = _make_available_action(
            challenge_name="Interpose",
            target_object_id=99,
            capability_name="telekinesis",
        )
        shield_action = _make_available_action(
            challenge_name="Interpose",
            target_object_id=99,
            capability_name="shield",
        )

        with (
            patch(
                "world.mechanics.services.get_available_actions",
                return_value=[tele_action, shield_action],
            ),
            patch(
                "world.mechanics.challenge_resolution.resolve_challenge",
                return_value=resolution,
            ) as mock_resolve,
        ):
            result = dispatch_capability_reaction(
                actor,
                target,
                challenge_name="Interpose",
                approach="telekinesis",
                error_msg="no match",
                outcome_fn=outcome_fn,
            )

        self.assertIs(result, resolution)
        outcome_fn.assert_called_once_with(resolution)
        # Verify resolve_challenge was called with the telekinesis action's resolved instance
        mock_resolve.assert_called_once_with(
            actor,
            tele_action.resolved_challenge_instance,
            tele_action.resolved_challenge_approach,
            tele_action.capability_source,
        )

    def test_falls_back_to_first_action_when_approach_not_found(self) -> None:
        """When the named approach has no matching capability_source, fall back to first action."""
        actor = MagicMock()
        actor.location = MagicMock()
        target = MagicMock()
        target.id = 99

        resolution = _make_resolution_result()
        outcome_fn = MagicMock()

        first_action = _make_available_action(
            challenge_name="Interpose",
            target_object_id=99,
            capability_name="shield",
        )
        second_action = _make_available_action(
            challenge_name="Interpose",
            target_object_id=99,
            capability_name="barrier",
        )

        with (
            patch(
                "world.mechanics.services.get_available_actions",
                return_value=[first_action, second_action],
            ),
            patch(
                "world.mechanics.challenge_resolution.resolve_challenge",
                return_value=resolution,
            ) as mock_resolve,
        ):
            result = dispatch_capability_reaction(
                actor,
                target,
                challenge_name="Interpose",
                approach="telekinesis",  # not in available actions
                error_msg="no match",
                outcome_fn=outcome_fn,
            )

        self.assertIs(result, resolution)
        outcome_fn.assert_called_once_with(resolution)
        # Falls back to first_action
        mock_resolve.assert_called_once_with(
            actor,
            first_action.resolved_challenge_instance,
            first_action.resolved_challenge_approach,
            first_action.capability_source,
        )

    def test_approach_none_falls_back_to_first_action(self) -> None:
        """When approach=None, fall back to the first available action."""
        actor = MagicMock()
        actor.location = MagicMock()
        target = MagicMock()
        target.id = 99

        resolution = _make_resolution_result()
        outcome_fn = MagicMock()

        first_action = _make_available_action(
            challenge_name="Interpose",
            target_object_id=99,
            capability_name="telekinesis",
        )

        with (
            patch(
                "world.mechanics.services.get_available_actions",
                return_value=[first_action],
            ),
            patch(
                "world.mechanics.challenge_resolution.resolve_challenge",
                return_value=resolution,
            ) as mock_resolve,
        ):
            result = dispatch_capability_reaction(
                actor,
                target,
                challenge_name="Interpose",
                approach=None,
                error_msg="no match",
                outcome_fn=outcome_fn,
            )

        self.assertIs(result, resolution)
        outcome_fn.assert_called_once_with(resolution)
        mock_resolve.assert_called_once()
