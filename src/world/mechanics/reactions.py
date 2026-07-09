"""Shared capability-reaction dispatch helper (#1273).

A "capability reaction" is the pattern where a character responds to an event
(a falling ally, an incoming blow) by locating an active :class:`ChallengeInstance`
bound to a target object, selecting the right approach from their available
actions, resolving the challenge, and applying an outcome function.

This module extracts that pattern from ``plummet.dispatch_catch`` so both the
catch and interpose resolution paths share one spine.  Converging
``dispatch_catch`` itself onto this helper is deferred to a follow-up task (Task
9) to avoid destabilising the already-merged plummet work.

Public surface:

- :func:`dispatch_capability_reaction` — the shared spine.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.mechanics.types import AvailableAction, ChallengeResolutionResult


def _select_reaction_action(
    actions: list[AvailableAction],
    approach: str | None,
) -> AvailableAction:
    """Pick the :class:`~world.mechanics.types.AvailableAction` matching *approach*.

    Iterates *actions* looking for one whose ``capability_source.capability_name``
    equals *approach*.  Falls back to ``actions[0]`` when:

    - *approach* is ``None``;
    - no action's capability name matches (e.g. the approach is condition-sourced
      and carries an empty ``capability_name``).

    Mirrors ``_select_catch_action`` in ``plummet.py`` but is parameterised on the
    approach name rather than hard-coding the catch capability.
    """
    if approach is not None:
        for action in actions:
            source = action.capability_source
            if source is not None and source.capability_name == approach:
                return action
    # No match — fall back to the first available reaction action.
    return actions[0]


def dispatch_capability_reaction(  # noqa: PLR0913
    actor: ObjectDB,  # noqa: OBJECTDB_PARAM
    target_object: ObjectDB,  # noqa: OBJECTDB_PARAM
    *,
    challenge_name: str,
    approach: str | None,
    error_msg: str,  # noqa: ARG001 — reserved for callers that raise on no-match
    outcome_fn: Callable[[ChallengeResolutionResult], None],
    extra_modifiers: int = 0,
) -> ChallengeResolutionResult | None:
    """Resolve *actor*'s capability reaction against *target_object* and apply the outcome.

    Shared spine for catch-a-faller and interpose-a-blow (and any future reactive
    capability resolution):

    1. :func:`~world.mechanics.services.get_available_actions` surfaces only the
       reaction approaches *actor*'s capabilities qualify for at their current
       location.
    2. The available actions are filtered to those matching *challenge_name* and
       bound to *target_object* via
       ``resolved_challenge_instance.target_object_id``.
    3. If none match, returns ``None`` (interpose policy: "no challenge — skip").
       Callers that prefer a ``LookupError`` on absence should inspect the result
       and raise themselves.
    4. :func:`_select_reaction_action` picks the action matching *approach*
       (falls back to the first action when *approach* is absent or has no
       exact match).
    5. :func:`~world.mechanics.challenge_resolution.resolve_challenge` resolves
       the chosen approach against the bound instance — the same synchronous
       immediate-challenge path a DANGER round drives.
    6. *outcome_fn* receives the :class:`~world.mechanics.types.ChallengeResolutionResult`
       and applies whatever state change the caller needs.
    7. Returns the result.

    Returns ``None`` when no reaction action is available for this
    *challenge_name* + *target_object* combination.
    """
    from world.mechanics.challenge_resolution import resolve_challenge  # noqa: PLC0415
    from world.mechanics.services import get_available_actions  # noqa: PLC0415

    location = actor.location
    available = get_available_actions(actor, location)

    reaction_actions = [
        action
        for action in available
        if action.challenge_name == challenge_name
        and action.resolved_challenge_instance is not None
        and action.resolved_challenge_instance.target_object_id == target_object.id
    ]

    if not reaction_actions:
        return None

    chosen = _select_reaction_action(reaction_actions, approach)

    result = resolve_challenge(
        actor,
        chosen.resolved_challenge_instance,  # type: ignore[arg-type] — filtered non-None above
        chosen.resolved_challenge_approach,  # type: ignore[arg-type] — set whenever instance is
        chosen.capability_source,
        extra_modifiers=extra_modifiers,
    )
    outcome_fn(result)
    return result
