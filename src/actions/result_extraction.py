"""Shared extraction logic for DispatchResult detail → (message, data).

This module provides a single source of truth for the REST and WebSocket
dispatch paths so they produce byte-identical output.  Deferred handling
is intentionally left to each caller (the serializer and the inputfunc
short-circuit before reaching this function in the same way).
"""

from __future__ import annotations

from typing import Any


def extract_dispatch_message_data(
    detail: object,
) -> tuple[str | None, dict[str, Any] | None]:
    """Derive ``(message, data)`` from a ``DispatchResult.detail`` object.

    Handles the three cases that can reach this function (deferred results
    never arrive here — both callers short-circuit before calling this):

    - ``ChallengeResolutionResult`` → ``(challenge_name, {challenge_instance_id,
      resolution_type, challenge_deactivated})``.
    - ``ActionResult`` → ``(message, data or None)``.
    - ``None`` / unknown → ``(None, None)``.

    Imports are deferred via runtime ``isinstance`` checks so this module can
    be imported from both ``actions/serializers.py`` (Django app boot) and
    ``server/conf/inputfuncs.py`` (Evennia conf, which defers all app imports).
    """
    from actions.types import ActionResult  # noqa: PLC0415
    from world.mechanics.types import ChallengeResolutionResult  # noqa: PLC0415

    if isinstance(detail, ChallengeResolutionResult):
        return detail.challenge_name, {
            "challenge_instance_id": detail.challenge_instance_id,
            "resolution_type": detail.resolution_type,
            "challenge_deactivated": detail.challenge_deactivated,
        }

    if isinstance(detail, ActionResult):
        return detail.message, detail.data or None

    return None, None
