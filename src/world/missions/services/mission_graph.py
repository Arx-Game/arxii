"""Service-level validation for the mission graph.

A thin post-save invariants wrapper around ``MissionOption.full_clean()``,
kept as the canonical "validate this option after building it" entry point
the future authoring API will call. The scalar invariants (kind/source
field consistency, CHALLENGE-source rules) live on the model in
``MissionOption.clean()``; this wrapper exists so callers have one stable
seam to ask "is this option well-formed?".
"""

from __future__ import annotations

from world.missions.models import MissionOption


def validate_mission_option(option: MissionOption) -> None:
    """Validate post-save invariants for ``option``.

    Runs ``full_clean()`` so every scalar field invariant on
    :class:`MissionOption` (including the CHALLENGE-source rules) is
    enforced. Raises ``ValidationError`` on violation.
    """
    option.full_clean()
