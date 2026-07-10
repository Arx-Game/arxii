"""Tests for apply_interpose_outcome and dispatch_interpose (#1273, Task 4).

TDD: write failing tests first, then implement.

Covers:
- apply_interpose_outcome: clean block (DESTROY) → amount becomes 0.
- apply_interpose_outcome: clean block (success_level > 0) → amount becomes 0.
- apply_interpose_outcome: partial (success_level == 0, not DESTROY) → amount halved.
- apply_interpose_outcome: failure (success_level < 0) → amount unchanged.
- dispatch_interpose: thin wrapper delegates to dispatch_capability_reaction
  with INTERPOSE_CHALLENGE_NAME and a partial(apply_interpose_outcome, pre_payload).
- dispatch_interpose: returns None when dispatch_capability_reaction returns None.

apply_interpose_outcome tests use lightweight stub objects so they do not require
wired DB state — the outcome logic depends only on
result.resolution_type and result.check_result.success_level.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from flows.events.payloads import DamagePreApplyPayload, DamageSource
from world.combat.interpose_content import INTERPOSE_CHALLENGE_NAME
from world.combat.services import apply_interpose_outcome, dispatch_interpose
from world.mechanics.constants import ResolutionType
from world.mechanics.types import ChallengeResolutionResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pre_payload(amount: int) -> DamagePreApplyPayload:
    """Build a minimal DamagePreApplyPayload with the given amount."""
    target = MagicMock()
    source = DamageSource(type="character", ref=None)
    return DamagePreApplyPayload(target=target, amount=amount, damage_type=None, source=source)


def _make_result(
    *,
    resolution_type: str,
    success_level: int,
) -> ChallengeResolutionResult:
    """Build a stub ChallengeResolutionResult for apply_interpose_outcome tests."""
    check_result = MagicMock()
    check_result.success_level = success_level

    consequence = MagicMock()

    return ChallengeResolutionResult(
        challenge_instance_id=1,
        challenge_name=INTERPOSE_CHALLENGE_NAME,
        approach_name="telekinesis",
        check_result=check_result,
        consequence=consequence,
        applied_effects=[],
        resolution_type=resolution_type,
        challenge_deactivated=(resolution_type == ResolutionType.DESTROY),
        display_consequences=[],
    )


# ---------------------------------------------------------------------------
# apply_interpose_outcome — outcome map tests
# ---------------------------------------------------------------------------


class ApplyInterposeOutcomeCleanBlockByDestroyTest(TestCase):
    """A DESTROY resolution type is a clean block regardless of success_level."""

    def test_destroy_resolution_sets_amount_to_zero(self) -> None:
        pre_payload = _make_pre_payload(40)
        result = _make_result(resolution_type=ResolutionType.DESTROY, success_level=0)

        apply_interpose_outcome(pre_payload, result)

        self.assertEqual(pre_payload.amount, 0)

    def test_destroy_resolution_with_negative_sl_still_blocks(self) -> None:
        """DESTROY always blocks regardless of success_level (consistent with resolve_catch)."""
        pre_payload = _make_pre_payload(40)
        result = _make_result(resolution_type=ResolutionType.DESTROY, success_level=-1)

        apply_interpose_outcome(pre_payload, result)

        self.assertEqual(pre_payload.amount, 0)


class ApplyInterposeOutcomeCleanBlockBySuccessLevelTest(TestCase):
    """success_level > 0 with non-DESTROY resolution_type is also a clean block."""

    def test_personal_resolution_success_level_positive_sets_zero(self) -> None:
        pre_payload = _make_pre_payload(40)
        result = _make_result(resolution_type=ResolutionType.PERSONAL, success_level=1)

        apply_interpose_outcome(pre_payload, result)

        self.assertEqual(pre_payload.amount, 0)

    def test_temporary_resolution_success_level_two_sets_zero(self) -> None:
        pre_payload = _make_pre_payload(100)
        result = _make_result(resolution_type=ResolutionType.TEMPORARY, success_level=2)

        apply_interpose_outcome(pre_payload, result)

        self.assertEqual(pre_payload.amount, 0)


class ApplyInterposeOutcomePartialTest(TestCase):
    """success_level == 0 and not DESTROY → amount is halved (floor division)."""

    def test_partial_halves_even_amount(self) -> None:
        pre_payload = _make_pre_payload(40)
        result = _make_result(resolution_type=ResolutionType.PERSONAL, success_level=0)

        apply_interpose_outcome(pre_payload, result)

        self.assertEqual(pre_payload.amount, 20)

    def test_partial_halves_odd_amount_floors(self) -> None:
        pre_payload = _make_pre_payload(41)
        result = _make_result(resolution_type=ResolutionType.PERSONAL, success_level=0)

        apply_interpose_outcome(pre_payload, result)

        self.assertEqual(pre_payload.amount, 20)

    def test_partial_temporary_resolution(self) -> None:
        pre_payload = _make_pre_payload(80)
        result = _make_result(resolution_type=ResolutionType.TEMPORARY, success_level=0)

        apply_interpose_outcome(pre_payload, result)

        self.assertEqual(pre_payload.amount, 40)


class ApplyInterposeOutcomeFailureTest(TestCase):
    """success_level < 0 → no change to amount (plummet continues at full damage)."""

    def test_failure_does_not_change_amount(self) -> None:
        pre_payload = _make_pre_payload(40)
        result = _make_result(resolution_type=ResolutionType.PERSONAL, success_level=-1)

        apply_interpose_outcome(pre_payload, result)

        self.assertEqual(pre_payload.amount, 40)

    def test_failure_large_negative_sl_no_change(self) -> None:
        pre_payload = _make_pre_payload(100)
        result = _make_result(resolution_type=ResolutionType.PERSONAL, success_level=-3)

        apply_interpose_outcome(pre_payload, result)

        self.assertEqual(pre_payload.amount, 100)


# ---------------------------------------------------------------------------
# dispatch_interpose — thin wrapper tests
# ---------------------------------------------------------------------------


class DispatchInterposeDelegatesTest(TestCase):
    """dispatch_interpose delegates to dispatch_capability_reaction correctly."""

    def test_returns_result_from_dispatch_capability_reaction(self) -> None:
        interposer = MagicMock()
        protected = MagicMock()
        pre_payload = _make_pre_payload(40)

        expected_result = MagicMock(spec=ChallengeResolutionResult)

        with patch(
            "world.mechanics.reactions.dispatch_capability_reaction",
            return_value=expected_result,
        ) as mock_dispatch:
            result = dispatch_interpose(interposer, protected, pre_payload, approach="telekinesis")

        self.assertIs(result, expected_result)
        mock_dispatch.assert_called_once()
        call_kwargs = mock_dispatch.call_args
        self.assertEqual(call_kwargs.args[0], interposer)
        self.assertEqual(call_kwargs.args[1], protected)
        self.assertEqual(call_kwargs.kwargs["challenge_name"], INTERPOSE_CHALLENGE_NAME)
        self.assertEqual(call_kwargs.kwargs["approach"], "telekinesis")

    def test_returns_none_when_no_challenge_found(self) -> None:
        interposer = MagicMock()
        protected = MagicMock()
        pre_payload = _make_pre_payload(40)

        with patch(
            "world.mechanics.reactions.dispatch_capability_reaction",
            return_value=None,
        ):
            result = dispatch_interpose(interposer, protected, pre_payload, approach="telekinesis")

        self.assertIsNone(result)

    def test_outcome_fn_applies_interpose_outcome(self) -> None:
        """The outcome_fn passed to dispatch_capability_reaction must call
        apply_interpose_outcome so the payload is mutated correctly."""
        interposer = MagicMock()
        protected = MagicMock()
        pre_payload = _make_pre_payload(40)

        captured_outcome_fn = None

        def _capture_dispatch(  # noqa: PLR0913
            actor, target, *, challenge_name, approach, error_msg, outcome_fn, extra_modifiers=0
        ):
            nonlocal captured_outcome_fn
            captured_outcome_fn = outcome_fn
            # Call it as if resolution succeeded
            resolution_result = _make_result(
                resolution_type=ResolutionType.DESTROY, success_level=1
            )
            outcome_fn(resolution_result)
            return resolution_result

        with patch(
            "world.mechanics.reactions.dispatch_capability_reaction",
            side_effect=_capture_dispatch,
        ):
            dispatch_interpose(interposer, protected, pre_payload, approach="telekinesis")

        # The outcome_fn must have been called — it modifies pre_payload.amount to 0
        self.assertIsNotNone(captured_outcome_fn, "outcome_fn was never captured")
        self.assertEqual(pre_payload.amount, 0, "outcome_fn must apply the interpose outcome")
